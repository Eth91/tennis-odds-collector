#!/usr/bin/env python3
"""NHL stats substrate for prop backtesting — official NHL API → nhl_stats.sqlite.

Three resumable stages (re-run any time; each skips what it already has):
  1. games         one stats-API call per season -> every game id + date + teams + score
  2. skater/goalie per-game boxscores (~1,400 games/season) -> one row per player-game
  3. players       full names for every player id seen -- boxscores abbreviate to
                   "C. McDavid" while the odds archive uses "Connor McDavid", so prop
                   grading joins through this table, not the boxscore name

Storage: TOI stored as INTEGER seconds; goalie "saves/shotsAgainst" split into two INTs;
one row per player-game keyed (game_id, player_id). ~170K skater rows / 3 seasons ≈ 25 MB.

    python nhl_stats_pull.py                    # seasons 20232024 20242025 20252026
    python nhl_stats_pull.py --seasons 20252026
    python nhl_stats_pull.py --status
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import ssl
import time
import urllib.request
from pathlib import Path

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:                                   # pragma: no cover
    CTX = ssl.create_default_context()

HERE = Path(__file__).resolve().parent
DB = HERE / "nhl_stats.sqlite"
SEASONS = ["20232024", "20242025", "20252026"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
  game_id INTEGER PRIMARY KEY, season TEXT, game_type INTEGER, date TEXT,
  home TEXT, away TEXT, home_score INTEGER, away_score INTEGER);
CREATE TABLE IF NOT EXISTS skater_games (
  game_id INTEGER, player_id INTEGER, name TEXT, team TEXT, pos TEXT,
  goals INTEGER, assists INTEGER, points INTEGER, plus_minus INTEGER, pim INTEGER,
  sog INTEGER, hits INTEGER, blocks INTEGER, ppg INTEGER, giveaways INTEGER,
  takeaways INTEGER, shifts INTEGER, toi_sec INTEGER,
  PRIMARY KEY (game_id, player_id));
CREATE TABLE IF NOT EXISTS goalie_games (
  game_id INTEGER, player_id INTEGER, name TEXT, team TEXT,
  saves INTEGER, shots_against INTEGER, goals_against INTEGER,
  decision TEXT, starter INTEGER, toi_sec INTEGER,
  PRIMARY KEY (game_id, player_id));
CREATE TABLE IF NOT EXISTS players (
  player_id INTEGER PRIMARY KEY, full_name TEXT, pos TEXT);
CREATE INDEX IF NOT EXISTS ix_sk_pd ON skater_games(player_id, game_id);
CREATE INDEX IF NOT EXISTS ix_gl_pd ON goalie_games(player_id, game_id);
"""


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(req, context=CTX, timeout=30))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def toi_sec(s):
    try:
        m, sec = str(s or "0:0").split(":")
        return int(m) * 60 + int(sec)
    except ValueError:
        return None


def pull_games(con, season):
    j = get("https://api.nhle.com/stats/rest/en/game?cayenneExp=season=" + season)
    n = 0
    for g in j.get("data", []):
        if g.get("gameType") not in (2, 3):            # regular season + playoffs only
            continue
        con.execute("INSERT OR REPLACE INTO games VALUES (?,?,?,?,?,?,?,?)",
                    (g["id"], season, g["gameType"], (g.get("gameDate") or "")[:10],
                     None, None, g.get("homeScore"), g.get("visitingScore")))
        n += 1
    con.commit()
    return n


def pull_boxscores(con, season, sleep=0.15):
    done = {r[0] for r in con.execute(
        "SELECT DISTINCT game_id FROM skater_games")}
    todo = [r[0] for r in con.execute(
        "SELECT game_id FROM games WHERE season=? ORDER BY game_id", (season,))
        if r[0] not in done]
    print(f"  {season}: {len(todo)} boxscores to fetch")
    for i, gid in enumerate(todo, 1):
        try:
            j = get(f"https://api-web.nhle.com/v1/gamecenter/{gid}/boxscore")
        except Exception as e:
            print(f"    game {gid} failed: {str(e)[:60]}")
            continue
        # future / unplayed games have no player stats -- skip, they stay in todo
        pbg = j.get("playerByGameStats") or {}
        if not pbg:
            continue
        for side in ("homeTeam", "awayTeam"):
            team = ((j.get(side) or {}).get("abbrev")) or ""
            con.execute("UPDATE games SET %s=? WHERE game_id=?"
                        % ("home" if side == "homeTeam" else "away"), (team, gid))
            blk = pbg.get(side) or {}
            for grp in ("forwards", "defense"):
                for p in blk.get(grp) or []:
                    con.execute(
                        "INSERT OR REPLACE INTO skater_games VALUES "
                        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (gid, p.get("playerId"),
                         (p.get("name") or {}).get("default"),
                         team, p.get("position"),
                         p.get("goals"), p.get("assists"), p.get("points"),
                         p.get("plusMinus"), p.get("pim"), p.get("sog"),
                         p.get("hits"), p.get("blockedShots"),
                         p.get("powerPlayGoals"), p.get("giveaways"),
                         p.get("takeaways"), p.get("shifts"),
                         toi_sec(p.get("toi"))))
            for p in blk.get("goalies") or []:
                ssa = str(p.get("saveShotsAgainst") or "/")
                sv, sa = (ssa.split("/") + [None])[:2] if "/" in ssa else (None, None)
                con.execute(
                    "INSERT OR REPLACE INTO goalie_games VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (gid, p.get("playerId"),
                     (p.get("name") or {}).get("default"), team,
                     int(sv) if sv not in (None, "") else None,
                     int(sa) if sa not in (None, "") else None,
                     p.get("goalsAgainst"), p.get("decision"),
                     1 if p.get("starter") else 0, toi_sec(p.get("toi"))))
        con.commit()
        if i % 100 == 0:
            print(f"    {i}/{len(todo)}")
        time.sleep(sleep)


def pull_names(con, sleep=0.1):
    todo = [r[0] for r in con.execute("""
        SELECT DISTINCT player_id FROM (
          SELECT player_id FROM skater_games UNION SELECT player_id FROM goalie_games)
        WHERE player_id NOT IN (SELECT player_id FROM players)""")]
    print(f"  {len(todo)} player names to resolve")
    for i, pid in enumerate(todo, 1):
        try:
            j = get(f"https://api-web.nhle.com/v1/player/{pid}/landing")
            fn = (j.get("firstName") or {}).get("default", "")
            ln = (j.get("lastName") or {}).get("default", "")
            con.execute("INSERT OR REPLACE INTO players VALUES (?,?,?)",
                        (pid, f"{fn} {ln}".strip(), j.get("position")))
        except Exception as e:
            print(f"    player {pid} failed: {str(e)[:50]}")
        if i % 50 == 0:
            con.commit()
            print(f"    {i}/{len(todo)}")
        time.sleep(sleep)
    con.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="*", default=SEASONS)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    if a.status:
        for t in ("games", "skater_games", "goalie_games", "players"):
            print(f"  {t:<14}", con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        con.close()
        return
    for s in a.seasons:
        print(f"season {s}: {pull_games(con, s)} games listed")
    for s in a.seasons:
        pull_boxscores(con, s)
    pull_names(con)
    con.execute("VACUUM")
    con.close()
    print(f"done -> {DB.name} ({DB.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
