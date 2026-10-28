#!/usr/bin/env python3
"""How far from the hoop each player secures his rebounds, and each team's opponents against it, for the props page's
Matchup page: docs/rebd/{season}.json, from NBA.com's tracking (kept in nba_rebd.sqlite): playerdashptreb, one call a
player, and teamdashptreb with TeamID=0 and OpponentTeamID, one call a team (every team's rebounds against it, summed).

The players: those with a rebounds, P+R, R+A or PRA line on the board; the teams: all 30. Last season is fetched once;
this season again once he (or the team) has played a game since (and, while NBA.com's count still trails the games, at
most every 3 hours). Play-by-play has no spot for the rebound itself, and NBA.com publishes no miss-by-grab cross-tab:
these are totals.

File: {season, fetched_at, dist, shot, players: {pid: row}, teams: {tri: row}, avg}
  row        [g, reb, oreb, contested, dist x4, shot x4, miss3]; a team's: its opponents' rebounds against it ("allowed")
  dist       rebounds by where he secured them: 0-3, 3-6, 6-10, 10+ ft from the hoop
  shot       rebounds by the distance of the missed shot: 0-6, 7-13, 13-19, 19+ ft
  contested  rebounds with 1+ other rebounder contesting; miss3: rebounds off missed threes
  avg        {dist: [4], shot: [4], contested, miss3}: shares of all rebounds over every player in the file (the page
             shades a player against it: "players with rebound lines", not the whole league)

    python3 nba_rebd.py --out /home/ubuntu/tennis-odds-collector/docs/rebd --props /home/ubuntu/tennis-odds-collector/docs/nba_props.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent / "nba_rebd.sqlite"
URL = ("https://stats.nba.com/stats/playerdashptreb?PlayerID={pid}&TeamID=0&Season={season}&SeasonType=Regular%20Season"
       "&PerMode=Totals&LeagueID=00&LastNGames=0&Month=0&OpponentTeamID=0&Period=0&DateFrom=&DateTo=&GameSegment="
       "&Location=&Outcome=&SeasonSegment=&VsConference=&VsDivision=")
OPP_URL = URL.replace("playerdashptreb?PlayerID={pid}&TeamID=0", "teamdashptreb?TeamID=0").replace("OpponentTeamID=0", "OpponentTeamID={pid}")
REB_MARKETS = ("rebounds", "pts_reb", "reb_ast", "pra")
DIST = ("0-3 Feet", "3-6 Feet", "6-10 Feet", "10+ Feet")
SHOT = ("0-6 Feet", "7-13 Feet", "13-19 Feet", "19+ Feet")
RETRY_H = 3
DDL = """CREATE TABLE IF NOT EXISTS reb (pid INTEGER, season TEXT, seen INTEGER, g INTEGER, row TEXT, fetched_at TEXT,
  PRIMARY KEY (pid, season));
CREATE TABLE IF NOT EXISTS opp (tid INTEGER, season TEXT, seen INTEGER, g INTEGER, row TEXT, fetched_at TEXT,
  PRIMARY KEY (tid, season))"""
TABLES = {"reb": ("pid", URL), "opp": ("tid", OPP_URL)}       # players; teams, by their opponents' rebounds against them


def row_of(j):
    """A playerdashptreb or teamdashptreb response -> [g, reb, oreb, contested, dist x4, shot x4, miss3], or None (no
    rebounds). A team's has a row for each team that played it: summed."""
    sets = {rs["name"]: rs for rs in j.get("resultSets") or []}
    rows = lambda name: [dict(zip(sets[name]["headers"], r)) for r in sets[name]["rowSet"]] if name in sets else []
    ov = rows("OverallRebounding")
    tot = lambda xs, col: sum(int(r.get(col) or 0) for r in xs)
    if not tot(ov, "REB"):
        return None
    by = lambda name, col, labels: [tot([r for r in rows(name) if r.get(col) == lab], "REB") for lab in labels]
    return ([tot(ov, "G"), tot(ov, "REB"), tot(ov, "OREB"), tot(ov, "C_REB")]
            + by("RebDistanceRebounding", "REB_DIST_RANGE", DIST) + by("ShotDistanceRebounding", "SHOT_DIST_RANGE", SHOT)
            + by("ShotTypeRebounding", "SHOT_TYPE_RANGE", ("Miss 3FG",)))


def due(con, pid, season, played, now, table="reb"):
    """Fetch him (or, table "opp", the team) for `season`? played: his games with minutes this season, or the team's
    games (None for last season: fetched once)."""
    r = con.execute(f"SELECT seen, g, fetched_at FROM {table} WHERE {TABLES[table][0]}=? AND season=?", (pid, season)).fetchone()
    if r is None:
        return True
    if played is None:
        return False
    seen, g, at = r
    if played > seen:                                          # a game since the last fetch
        return True
    stale = now - dt.datetime.fromisoformat(at) >= dt.timedelta(hours=RETRY_H)
    return g < played and stale                                # NBA.com's count still trails: retry, not every run


def fetch(con, todo, get, now, pace=1.0, table="reb"):
    """todo: [(pid or team id, season, played or None)]. Stores each response. Returns (stored, failed); stops after 5
    failures in a row (NBA.com refusing)."""
    stored = failed = row_fails = 0
    for k, (pid, season, played) in enumerate(todo):
        if k and pace:
            time.sleep(pace)
        try:
            row = row_of(get(TABLES[table][1].format(pid=pid, season=season)))
        except Exception:                                                     # noqa: BLE001
            failed += 1
            row_fails += 1
            if row_fails >= 5:
                break
            continue
        row_fails = 0
        con.execute(f"INSERT OR REPLACE INTO {table} VALUES (?,?,?,?,?,?)", (pid, season, played or 0, row[0] if row else 0,
                                                                            json.dumps(row) if row else None, now.isoformat()))
        con.commit()
        stored += 1
    return stored, failed


def build(con, season, now, tri_of=None):
    """The season's file (see the module doc). tri_of: {team id: tricode}."""
    players = {str(pid): json.loads(row) for pid, row in con.execute(
        "SELECT pid, row FROM reb WHERE season=? AND row IS NOT NULL ORDER BY pid", (season,))}
    tot = sum(r[1] for r in players.values())
    share = lambda f: round(f / tot, 4) if tot else None
    avg = {"dist": [share(sum(r[4 + k] for r in players.values())) for k in range(4)],
           "shot": [share(sum(r[8 + k] for r in players.values())) for k in range(4)],
           "contested": share(sum(r[3] for r in players.values())), "miss3": share(sum(r[12] for r in players.values()))}
    teams = {tri_of[tid]: json.loads(row) for tid, row in con.execute(
        "SELECT tid, row FROM opp WHERE season=? AND row IS NOT NULL ORDER BY tid", (season,)) if tid in (tri_of or {})}
    return {"season": season, "fetched_at": now.replace(microsecond=0).isoformat(), "dist": ["0-3", "3-6", "6-10", "10+"],
            "shot": ["0-6", "7-13", "13-19", "19+"], "players": players, "teams": teams, "avg": avg}


def targets(props_path):
    """The players with a rebounds-related line in the props payload."""
    D = json.loads(Path(props_path).read_text())
    return sorted({int(p["pid"]) for p in D.get("props") or [] if p.get("market") in REB_MARKETS and p.get("pid")})


def write(out, doc):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f".{doc['season']}.json.tmp"
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    os.replace(tmp, out / f"{doc['season']}.json")


def main():
    import nba_matchup as MU
    import nba_research as R
    import nba_shots as S
    from nba_board import TEAM_ID
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/rebd)")
    ap.add_argument("--props", required=True, help="the props payload (docs/nba_props.json)")
    ap.add_argument("--pace", type=float, default=1.0, help="seconds between NBA.com calls")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    con.executescript(DDL)
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    now = dt.datetime.now(dt.timezone.utc)
    cur = R.season_of(now.astimezone(R.ET).date().isoformat())
    prev = R.prev_season(cur)
    played = dict(mcon.execute("SELECT p.pid, COUNT(*) FROM player_games p JOIN games g ON g.gid = p.gid "
                               "WHERE g.season = ? AND p.min > 0 GROUP BY p.pid", (cur,)))
    pids = targets(a.props)
    todo = [(p, prev, None) for p in pids if due(con, p, prev, None, now)]
    todo += [(p, cur, played.get(p, 0)) for p in pids if due(con, p, cur, played.get(p, 0), now)]
    stored, failed = fetch(con, todo, S._get, now, a.pace)
    tri_of = {int(v): k for k, v in TEAM_ID.items()}
    tgp = S.games_played(mcon, cur)
    tdo = [(t, prev, None) for t in tri_of if due(con, t, prev, None, now, "opp")]
    tdo += [(t, cur, tgp.get(tri_of[t], 0)) for t in tri_of if due(con, t, cur, tgp.get(tri_of[t], 0), now, "opp")]
    tstored, tfailed = fetch(con, tdo, S._get, now, a.pace, "opp")
    for s in (prev, cur):
        write(a.out, build(con, s, now, tri_of))
    print(f"nba_rebd: {len(pids)} players with rebound lines · {stored} fetched, {failed} failed · teams {tstored} fetched, "
          f"{tfailed} failed -> {a.out}")


if __name__ == "__main__":
    main()
