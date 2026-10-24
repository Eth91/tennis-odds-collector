#!/usr/bin/env python3
"""NBA player-tracking stats per game — rebound chances, potential assists, touches.

For NBA_TRACKING_PREREG.md. The league's tracking box score (boxscoreplayertrackv3) carries
rebound chances but NOT potential assists; the season endpoint `leaguedashptstats` carries both,
and filtered to ONE date (DateFrom = DateTo) it returns every player's single game (GP = 1,
verified 2026-10-23: Trae Young 2024-01-15, 23 potential assists / 13 assists). So: one call per
game date per measure — ~170 dates a season, not ~1,230 games.

Stores nba_tracking.sqlite (gitignored):
  tracking  (date, player_id) -> potential_ast, ast_trk, passes, secondary_ast, ft_ast,
            reb_chances, oreb_chances, dreb_chances, reb_trk
  fetched   (date, measure) -> rows, fetched_at        — resumable: done dates are skipped

`--verify` is the prereg's INTEGRITY GATE: the tracking feed's own AST/REB must equal the box
score's (nba_gamelogs.sqlite logs_full) on >= 99% of joined player-games, and every box player-game
with minutes should have a tracking row. Exit 1 if not.

    python nba_tracking.py --fetch --seasons 2022-23 2023-24 2024-25
    python nba_tracking.py --fetch --seasons 2025-26 --current    # + this season's played dates
    python nba_tracking.py --verify

WHERE. stats.nba.com answers the Oracle VM with curl_cffi impersonation (verified 2026-10-23), so the
NBA engine's copy on the VM keeps its own nba_tracking.sqlite: 2025-26 backfilled, the current season
fetched daily (`--current`: game dates from nba_season_boxes.json, before today ET). That feeds the
OPPORTUNITY-CONFIRMED tracked cell (NBA_SPEED_PREREG.md amendment 9).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
import time
from pathlib import Path

from curl_cffi import requests as cr

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_tracking.sqlite"
LOGS = HERE / "nba_gamelogs.sqlite"
H = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com", "Accept": "application/json",
     "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}
URL = ("https://stats.nba.com/stats/leaguedashptstats?Season={season}&SeasonType=Regular%20Season"
       "&LeagueID=00&PerMode=Totals&PlayerOrTeam=Player&PtMeasureType={measure}&LastNGames=0&Month=0"
       "&OpponentTeamID=0&TeamID=0&DateFrom={d}&DateTo={d}&GameScope=&PlayerExperience="
       "&PlayerPosition=&StarterBench=&Outcome=&Location=&SeasonSegment=&VsConference=&VsDivision="
       "&College=&Conference=&Country=&Division=&DraftPick=&DraftYear=&Height=&Weight=")
COLS = {"Passing": {"POTENTIAL_AST": "potential_ast", "AST": "ast_trk", "PASSES_MADE": "passes",
                    "SECONDARY_AST": "secondary_ast", "FT_AST": "ft_ast"},
        "Rebounding": {"REB_CHANCES": "reb_chances", "OREB_CHANCES": "oreb_chances",
                       "DREB_CHANCES": "dreb_chances", "REB": "reb_trk"}}
DDL = """
CREATE TABLE IF NOT EXISTS tracking (
    date TEXT, player_id INTEGER, potential_ast REAL, ast_trk REAL, passes REAL,
    secondary_ast REAL, ft_ast REAL, reb_chances REAL, oreb_chances REAL, dreb_chances REAL,
    reb_trk REAL, PRIMARY KEY (date, player_id));
CREATE TABLE IF NOT EXISTS fetched (date TEXT, measure TEXT, rows INTEGER, fetched_at TEXT,
    PRIMARY KEY (date, measure));
"""
PAUSE_S = 1.0


def _get(url, tries=4):
    for k in range(tries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=60, headers=H)
            if r.status_code == 200:
                return r.json()["resultSets"][0]
            err = f"HTTP {r.status_code}"
        except Exception as e:                       # timeouts, resets
            err = type(e).__name__
        time.sleep(5 * (k + 1))                      # back off: 5, 10, 15 s
    raise RuntimeError(f"gave up after {tries} tries ({err})")


def game_dates(seasons):
    con = sqlite3.connect(f"file:{LOGS}?mode=ro", uri=True)
    q = f"SELECT DISTINCT date, season FROM logs_full WHERE season IN ({','.join('?' * len(seasons))})"
    out = sorted(con.execute(q, seasons).fetchall())
    con.close()
    return out


def season_of(d):
    """'2026-10-23' -> '2026-27' (the NBA season a date belongs to)."""
    y = int(d[:4])
    return f"{y}-{(y + 1) % 100:02d}" if int(d[5:7]) >= 8 else f"{y - 1}-{y % 100:02d}"


def current_dates(today_et=None):
    """This season's played dates from nba_rosters' box-score cache, strictly before today (ET)."""
    import json
    from zoneinfo import ZoneInfo
    today_et = today_et or dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    cache = HERE / "nba_season_boxes.json"
    if not cache.exists():
        return []
    dates = {g["date"] for g in json.loads(cache.read_text()).values() if g.get("date")}
    return sorted((d, season_of(d)) for d in dates if d < today_et)


def fetch(seasons, current=False):
    con = sqlite3.connect(DB)
    con.executescript(DDL)
    dates = (game_dates(seasons) if seasons else []) + (current_dates() if current else [])
    todo = [(d, s, m) for d, s in sorted(set(dates)) for m in COLS
            if not con.execute("SELECT 1 FROM fetched WHERE date=? AND measure=?", (d, m)).fetchone()]
    print(f"{len(todo)} (date, measure) calls to make", flush=True)
    t0 = time.time()
    for i, (d, season, measure) in enumerate(todo, 1):
        mmddyyyy = f"{d[5:7]}/{d[8:10]}/{d[:4]}"
        rs = _get(URL.format(season=season, measure=measure, d=mmddyyyy))
        ix = {h: k for k, h in enumerate(rs["headers"])}
        gp_bad = [r for r in rs["rowSet"] if r[ix["GP"]] not in (0, 1)]
        if gp_bad:                                   # one date must mean one game per player
            raise RuntimeError(f"{d} {measure}: {len(gp_bad)} rows with GP > 1 — the date filter failed")
        cols = COLS[measure]
        for r in rs["rowSet"]:
            con.execute("INSERT OR IGNORE INTO tracking (date, player_id) VALUES (?, ?)",
                        (d, int(r[ix["PLAYER_ID"]])))
            con.execute(f"UPDATE tracking SET {', '.join(f'{v}=?' for v in cols.values())} "
                        "WHERE date=? AND player_id=?",
                        (*[r[ix[c]] for c in cols], d, int(r[ix["PLAYER_ID"]])))
        con.execute("INSERT OR REPLACE INTO fetched VALUES (?,?,?,?)",
                    (d, measure, len(rs["rowSet"]), dt.datetime.now(dt.timezone.utc).isoformat()))
        con.commit()
        if i % 25 == 0 or i == len(todo):
            rate = (time.time() - t0) / i
            print(f"  {i}/{len(todo)} · {d} {measure} {len(rs['rowSet'])} rows · "
                  f"~{(len(todo) - i) * rate / 60:.0f} min left", flush=True)
        time.sleep(PAUSE_S)
    con.close()


def verify():
    """The prereg integrity gate. Agreement is measured where BOTH numbers exist (a SQL NULL
    compares as neither equal nor unequal — the first version counted every missing row as a
    disagreement and read 91% for a feed that agreed 100%). The Rebounding feed OMITS players with
    no rebound chances, so a missing rebounding row must be a zero-rebound game nearly always."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.execute(f"ATTACH DATABASE 'file:{LOGS}?mode=ro' AS g")
    ok = True
    for (season, n_box, n_row, n_ast, ast_eq, n_reb, reb_eq, n_noreb, noreb_zero) in con.execute("""
        SELECT l.season, COUNT(*), COUNT(t.player_id),
               COUNT(t.ast_trk), SUM(t.ast_trk = l.ast),
               COUNT(t.reb_trk), SUM(t.reb_trk = l.reb),
               SUM(t.player_id IS NOT NULL AND t.reb_trk IS NULL),
               SUM(t.player_id IS NOT NULL AND t.reb_trk IS NULL AND l.reb = 0)
        FROM g.logs_full l LEFT JOIN tracking t ON t.date = l.date AND t.player_id = l.player_id
        WHERE l.min > 0 AND l.date IN (SELECT date FROM fetched GROUP BY date HAVING COUNT(*) = 2)
        GROUP BY l.season"""):
        cov = n_row / n_box
        a = (ast_eq or 0) / max(1, n_ast)
        r = (reb_eq or 0) / max(1, n_reb)
        z = (noreb_zero or 0) / max(1, n_noreb) if n_noreb else 1.0
        good = cov >= 0.97 and a >= 0.99 and r >= 0.99 and z >= 0.90
        ok &= good
        print(f"{season}: box player-games {n_box:,} · tracked {n_row:,} ({100 * cov:.1f}%) · AST agrees "
              f"{100 * a:.2f}% of {n_ast:,} · REB agrees {100 * r:.2f}% of {n_reb:,} · no rebounding row "
              f"{n_noreb or 0} ({100 * z:.0f}% zero-rebound games) -> {'OK' if good else 'FAIL'}")
    d = con.execute("SELECT COUNT(DISTINCT date), SUM(rows) FROM fetched").fetchone()
    print(f"dates fetched: {d[0]} · rows returned: {d[1]:,}")
    return ok

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--seasons", nargs="+", default=None)
    ap.add_argument("--current", action="store_true", help="also this season's played dates (daily on the VM)")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.fetch:
        seasons = a.seasons if a.seasons is not None else ([] if a.current else ["2022-23", "2023-24", "2024-25"])
        fetch(seasons, current=a.current)
    if a.verify:
        sys.exit(0 if verify() else 1)
