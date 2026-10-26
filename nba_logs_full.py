#!/usr/bin/env python3
"""NBA game logs with EVERY column, plus player positions. MAC-ONLY (stats.nba.com).

WHY. `nba_gamelogs.sqlite.logs` keeps 5 stat columns of the 32 `leaguegamelog` returns. The
dropped ones include FGA/FTA/FG3A — and the WNBA pricing machinery cannot run without them:
its points decision is driven by shot volume, and its conviction gate passes an over only on a
minutes bump (> 2) OR an FGA bump (> 1), treating a missing FGA split as a FAIL. So the port
needs them. See NBA_PRICING_PREREG.md.

ADDITIVE ONLY. Writes two NEW tables into nba_gamelogs.sqlite and never touches `logs`, which
nba_wowy, nba_margin_refit, nba_coldstart_realline and nba_rosters all read:
  logs_full  one row per (game_id, player_id), all box columns
  positions  one row per player: the player index's position (G / F / C / G-F / F-C / ...)

`--verify` checks logs_full against logs: same rows, identical min/pts/reb/ast/fg3m.

    python nba_logs_full.py --fetch     # ~4 calls, one per season, + one index call
    python nba_logs_full.py --verify
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from curl_cffi import requests as cr

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_gamelogs.sqlite"
SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]
H = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com",
     "Accept": "application/json", "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}
COLS = ["season", "game_id", "date", "team", "player_id", "player", "min", "fgm", "fga",
        "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf",
        "pts", "plus_minus"]
SRC = {"game_id": "GAME_ID", "date": "GAME_DATE", "team": "TEAM_ABBREVIATION",
       "player_id": "PLAYER_ID", "player": "PLAYER_NAME", "min": "MIN", "fgm": "FGM",
       "fga": "FGA", "fg3m": "FG3M", "fg3a": "FG3A", "ftm": "FTM", "fta": "FTA", "oreb": "OREB",
       "dreb": "DREB", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK", "tov": "TOV",
       "pf": "PF", "pts": "PTS", "plus_minus": "PLUS_MINUS"}


def _get(url):
    r = cr.get(url, impersonate="chrome", timeout=90, headers=H)
    if r.status_code != 200:
        raise SystemExit(f"HTTP {r.status_code} for {url[:90]}")
    return r.json()["resultSets"][0]


def fetch():
    con = sqlite3.connect(DB)
    con.execute(f"""CREATE TABLE IF NOT EXISTS logs_full (
        {', '.join(c + (' INTEGER' if c == 'player_id' else ' REAL' if c not in
                        ('season', 'game_id', 'date', 'team', 'player') else ' TEXT')
                   for c in COLS)},
        PRIMARY KEY (game_id, player_id))""")
    for season in SEASONS:
        rs = _get("https://stats.nba.com/stats/leaguegamelog?Counter=1000&DateFrom=&DateTo="
                  f"&Direction=DESC&LeagueID=00&PlayerOrTeam=P&Season={season}"
                  "&SeasonType=Regular%20Season&Sorter=DATE")
        ix = {c: i for i, c in enumerate(rs["headers"])}
        missing = [v for v in SRC.values() if v not in ix]
        if missing:
            raise SystemExit(f"{season}: leaguegamelog no longer returns {missing}")
        rows = [(season, *[(r[ix[SRC[c]]] if r[ix[SRC[c]]] is not None else 0)
                           for c in COLS[1:]]) for r in rs["rowSet"]]
        con.executemany(f"INSERT OR REPLACE INTO logs_full VALUES ({','.join('?' * len(COLS))})",
                        rows)
        con.commit()
        print(f"{season}: {len(rows):,} player-game rows")
    rs = _get("https://stats.nba.com/stats/playerindex?LeagueID=00&Season=2026-27&Historical=1")
    ix = {c: i for i, c in enumerate(rs["headers"])}
    con.execute("CREATE TABLE IF NOT EXISTS positions (player_id INTEGER PRIMARY KEY, "
                "player TEXT, position TEXT)")
    pos = [(int(r[ix["PERSON_ID"]]),
            f"{r[ix['PLAYER_FIRST_NAME']]} {r[ix['PLAYER_LAST_NAME']]}".strip(),
            r[ix["POSITION"]] or "") for r in rs["rowSet"]]
    con.executemany("INSERT OR REPLACE INTO positions VALUES (?,?,?)", pos)
    con.commit()
    con.close()
    print(f"positions: {len(pos):,} players ({sum(1 for p in pos if p[2]):,} with a position)")


def verify():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bad = 0
    for season, n_old, n_new, n_both, n_diff in con.execute("""
        SELECT o.season, o.n, f.n, j.n, j.diff FROM
          (SELECT season, COUNT(*) n FROM logs GROUP BY season) o
          JOIN (SELECT season, COUNT(*) n FROM logs_full GROUP BY season) f USING (season)
          JOIN (SELECT l.season, COUNT(*) n,
                       SUM(l.min != f.min OR l.pts != f.pts OR l.reb != f.reb
                           OR l.ast != f.ast OR l.fg3m != f.fg3m) diff
                FROM logs l JOIN logs_full f USING (game_id, player_id)
                GROUP BY l.season) j USING (season)"""):
        # A row only in `logs` with ZERO minutes is a DNP entry the league has since dropped
        # from leaguegamelog (2022-23: Schröder 2022-11-06, 0 min) — a revision of a
        # non-appearance, reported, not a failure. A missing row WITH minutes is a failure.
        gone = con.execute("SELECT SUM(l.min > 0), SUM(l.min = 0) FROM logs l LEFT JOIN "
                           "logs_full f USING (game_id, player_id) WHERE l.season = ? AND "
                           "f.game_id IS NULL", (season,)).fetchone()
        played_gone, dnp_gone = gone[0] or 0, gone[1] or 0
        extra = n_new - n_both
        ok = played_gone == 0 and n_diff == 0
        bad += not ok
        print(f"{season}: logs {n_old:,} · logs_full {n_new:,} · joined {n_both:,} · "
              f"differing min/pts/reb/ast/fg3m {n_diff} · missing played rows {played_gone}"
              + (f" · dropped 0-min DNP rows {dnp_gone}" if dnp_gone else "")
              + (f" · new rows {extra}" if extra else "")
              + f" -> {'OK' if ok else 'MISMATCH'}")
    fga = con.execute("SELECT COUNT(*), SUM(fga > 0), AVG(fga) FROM logs_full WHERE min >= 20"
                      ).fetchone()
    print(f"FGA present: {fga[1]:,}/{fga[0]:,} 20+ min games have FGA > 0, mean {fga[2]:.1f}")
    pos = con.execute("SELECT COUNT(DISTINCT l.player_id), SUM(p.position != '') FROM "
                      "(SELECT DISTINCT player_id FROM logs_full) l LEFT JOIN positions p "
                      "USING (player_id)").fetchone()
    print(f"positions: {pos[1]:,} of {pos[0]:,} logged players have one")
    con.close()
    return bad == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.fetch:
        fetch()
    if a.verify or a.fetch:
        sys.exit(0 if verify() else 1)
