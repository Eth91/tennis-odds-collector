#!/usr/bin/env python3
"""Who guards whom, for the Matchup page: docs/matchups/{pid}.json — every defender who has guarded the player this
season and last, from stats.nba.com leagueseasonmatchups (NBA.com's player-tracking matchups: the possessions a
defender was the one guarding him, and what he did in them).

Fetched per offensive team (OffTeamID), 30 requests a season, so no response nears the 102,400-row cap; the totals
are cumulative, so a season's rows are replaced on each fetch. A past season is fetched once (kept in
nba_defmatch.sqlite), the current one every run.

File: {pid, s: {season: [[def_pid, def_name, gp, poss, pts, fgm, fga, fg3m, fg3a, ast, tov, fta, seconds]]}},
most possessions first, pairs under MIN_POSS possessions left out.

    python3 nba_defmatch.py --out /home/ubuntu/tennis-odds-collector/docs/matchups
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import time
from pathlib import Path

URL = ("https://stats.nba.com/stats/leagueseasonmatchups?DefPlayerID=&DefTeamID=&LeagueID=00&OffPlayerID="
       "&OffTeamID={team}&PerMode=Totals&Season={season}&SeasonType=Regular%20Season")
DB = Path(__file__).resolve().parent / "nba_defmatch.sqlite"
MIN_POSS = 3.0
PAUSE_S = 1.0
COLS = ("DEF_PLAYER_ID", "DEF_PLAYER_NAME", "GP", "PARTIAL_POSS", "PLAYER_PTS", "MATCHUP_FGM", "MATCHUP_FGA",
        "MATCHUP_FG3M", "MATCHUP_FG3A", "MATCHUP_AST", "MATCHUP_TOV", "MATCHUP_FTA", "MATCHUP_TIME_SEC")
DDL = """CREATE TABLE IF NOT EXISTS pairs (season TEXT, off_pid INTEGER, def_pid INTEGER, def_name TEXT, gp INTEGER,
    poss REAL, pts REAL, fgm REAL, fga REAL, fg3m REAL, fg3a REAL, ast REAL, tov REAL, fta REAL, secs REAL,
    PRIMARY KEY (season, off_pid, def_pid));
CREATE TABLE IF NOT EXISTS fetched (season TEXT, team_id INTEGER, at TEXT, rows INTEGER, PRIMARY KEY (season, team_id));"""


def store(con, season, j):
    """Replace the rows a response carries (one offensive team's). Returns how many."""
    rs = j["resultSets"][0] if isinstance(j["resultSets"], list) else j["resultSets"]
    ix = {h: k for k, h in enumerate(rs["headers"])}
    rows = [(season, r[ix["OFF_PLAYER_ID"]]) + tuple(r[ix[c]] for c in COLS) for r in rs["rowSet"]]
    con.executemany("INSERT OR REPLACE INTO pairs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def fetch(con, season, current, team_ids, get=None, pause=PAUSE_S):
    """Every offensive team's matchups for the season: a past season only for teams not fetched yet."""
    if get is None:
        import nba_shots as SH
        get = SH._get
    n = 0
    for tid in team_ids:
        if not current and con.execute("SELECT 1 FROM fetched WHERE season=? AND team_id=?", (season, tid)).fetchone():
            continue
        k = store(con, season, get(URL.format(team=tid, season=season)))
        con.execute("INSERT OR REPLACE INTO fetched VALUES (?,?,?,?)",
                    (season, tid, dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), k))
        con.commit()
        n += k
        time.sleep(pause)
    return n


def write(con, out, seasons):
    """docs/matchups/{pid}.json for every player with a pair in `seasons`. Returns how many were written."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    per = {}
    marks = ",".join("?" * len(seasons))
    for row in con.execute(f"SELECT season, off_pid, def_pid, def_name, gp, poss, pts, fgm, fga, fg3m, fg3a, ast, tov, fta, "
                           f"secs FROM pairs WHERE season IN ({marks}) AND poss >= ? ORDER BY poss DESC",
                           list(seasons) + [MIN_POSS]):
        season, off = row[0], row[1]
        per.setdefault(off, {}).setdefault(season, []).append([row[2], row[3], row[4]] + [round(v or 0, 1) for v in row[5:]])
    for pid, s in per.items():
        tmp = out / f".{pid}.json.tmp"
        tmp.write_text(json.dumps({"pid": pid, "s": s}, separators=(",", ":")))
        os.replace(tmp, out / f"{pid}.json")
    return len(per)


def main():
    import nba_research as R
    from nba_board import TEAM_ID
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/matchups)")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    con.executescript(DDL)
    cur = R.season_of(dt.datetime.now(R.ET).date().isoformat())
    teams = sorted(int(v) for v in TEAM_ID.values())
    for s in (cur, R.prev_season(cur)):
        print(f"nba_defmatch: {s} · {fetch(con, s, s == cur, teams)} pairs fetched")
    print(f"nba_defmatch: {write(con, a.out, (R.prev_season(cur), cur))} players -> {a.out}")


if __name__ == "__main__":
    main()
