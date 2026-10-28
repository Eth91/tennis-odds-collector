#!/usr/bin/env python3
"""Assists and rebounds by court zone, for the props page's Matchup page: docs/pbp/{season}.json, from each final game's
cdn.nba.com play-by-play (fetched once: a final game's play-by-play does not change; kept in nba_pbp.sqlite).

  assists   every made field goal, who made it and who assisted it, and the zone of the shot: where a player's passes
            become baskets, and how many assisted baskets each team gives up in each zone
  rebounds  every player rebound, offensive or defensive, and the zone of the miss it came off (a missed free throw
            its own zone): where a player's rebounds come from, and how many rebounds each team's opponents get

Zones: the shot chart's six, Restricted Area (4 ft), Paint, Mid-Range, Left Corner 3, Right Corner 3, Above the Break 3
(+ Free Throw for rebounds), from the shot's legacy court position in tenths of a foot (basket at 0,0; a three with
y <= 92 is a corner three; x < 0 the left corner, as stats.nba's LOC_X, which xLegacy matches shot for shot).

File: {season, fetched_at, zones, league: {gp, ast: [6], reb: [7], miss: [7]},
       teams: {TRI: [gp, ast allowed x6, reb allowed x7, misses x7]}, players: {pid: [gp, ast x6, reb x7, oreb]}}
  gp       a team's games, a player's games with minutes (nba_matchup.sqlite)
  ast      assisted makes by zone (a team: its opponents' assisted makes against it); reb: rebounds by the miss's zone
           (a team: its opponents' players' rebounds against it); league: all teams' totals, gp = team-games
  misses   a team's own missed shots that a player rebounded, by zone (long misses make long rebounds)

    python3 nba_pbp.py --out /home/ubuntu/tennis-odds-collector/docs/pbp
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DB = Path(__file__).resolve().parent / "nba_pbp.sqlite"
URL = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{}.json"
ZONES = ("Restricted Area", "Paint", "Mid-Range", "Left Corner 3", "Right Corner 3", "Above the Break 3")
FT = len(ZONES)                                          # rebounds off a missed free throw: zone 6
VERSION = 2                                              # 2: the corners split (a store of an older version is refilled)
DDL = """CREATE TABLE IF NOT EXISTS games (gid TEXT PRIMARY KEY, season TEXT, date TEXT);
CREATE TABLE IF NOT EXISTS makes (gid TEXT, team TEXT, opp TEXT, pid INTEGER, ast_pid INTEGER, zone INTEGER, pts INTEGER);
CREATE TABLE IF NOT EXISTS rebs (gid TEXT, team TEXT, opp TEXT, pid INTEGER, kind TEXT, zone INTEGER);
CREATE INDEX IF NOT EXISTS makes_gid ON makes (gid);
CREATE INDEX IF NOT EXISTS rebs_gid ON rebs (gid);"""


def zone(a):
    """A shot action -> its zone index (ZONES), from its legacy court position, else its distance."""
    t, d, x, y = a.get("actionType"), a.get("shotDistance"), a.get("xLegacy"), a.get("yLegacy")
    if t == "3pt":
        return (3 if x < 0 else 4) if x is not None and y is not None and y <= 92 else 5
    if d is not None and d <= 4:
        return 0
    if x is not None and y is not None:
        return 1 if abs(x) <= 80 and y <= 142 else 2
    return 1 if d is not None and d <= 14 else 2


def parse(actions, home, away):
    """A game's play-by-play actions -> (makes [(team, opp, pid, ast_pid, zone, pts)], rebs [(team, opp, pid, kind, zone)]).
    Team rebounds (no player) are left out; a rebound whose miss is not in the feed is left out."""
    other = {home: away, away: home}
    by_num = {a.get("actionNumber"): a for a in actions}
    makes, rebs = [], []
    for a in actions:
        t, team = a.get("actionType"), a.get("teamTricode")
        if team not in other:
            continue
        if t in ("2pt", "3pt") and a.get("shotResult") == "Made" and a.get("personId"):
            makes.append((team, other[team], int(a["personId"]), int(a["assistPersonId"]) if a.get("assistPersonId") else None,
                          zone(a), 3 if t == "3pt" else 2))
        elif t == "rebound" and a.get("personId"):
            miss = by_num.get(a.get("shotActionNumber"))
            if not miss:
                continue
            z = FT if miss.get("actionType") == "freethrow" else zone(miss)
            rebs.append((team, other[team], int(a["personId"]), "o" if a.get("subType") == "offensive" else "d", z))
    return makes, rebs


def connect(path):
    """The store; one written by an older VERSION is emptied, so every game is fetched again under the current zones."""
    con = sqlite3.connect(path)
    if con.execute("PRAGMA user_version").fetchone()[0] < VERSION:
        con.executescript("DROP TABLE IF EXISTS games; DROP TABLE IF EXISTS makes; DROP TABLE IF EXISTS rebs;")
        con.execute(f"PRAGMA user_version = {VERSION}")
    con.executescript(DDL)
    return con


def fetch(con, mcon, seasons, get=None, workers=4):
    """Store the play-by-play of every final game in `seasons` (nba_matchup's games) not stored yet. Returns (stored, failed)."""
    have = {g for (g,) in con.execute("SELECT gid FROM games")}
    marks = ",".join("?" * len(seasons))
    todo = [r for r in mcon.execute(f"SELECT gid, season, date, home, away FROM games WHERE season IN ({marks}) "
                                    "AND home_pts IS NOT NULL ORDER BY date DESC", list(seasons)) if r[0] not in have]
    if get is None:
        import nba_rosters as R
        get = lambda gid: R._get(URL.format(gid))["game"]["actions"]

    def one(r):
        try:
            return parse(get(r[0]), r[3], r[4])
        except Exception:                                                     # noqa: BLE001
            return None
    stored = failed = 0
    with ThreadPoolExecutor(workers) as ex:
        for (gid, season, date, _, _), got in zip(todo, ex.map(one, todo)):
            if not got or not got[0]:                                         # no feed yet, or no made shots: retried
                failed += 1
                continue
            makes, rebs = got
            con.executemany("INSERT INTO makes VALUES (?,?,?,?,?,?,?)", [(gid,) + m for m in makes])
            con.executemany("INSERT INTO rebs VALUES (?,?,?,?,?,?)", [(gid,) + r for r in rebs])
            con.execute("INSERT INTO games VALUES (?,?,?)", (gid, season, date))
            stored += 1
            if stored % 50 == 0:
                con.commit()                                  # a long first fill keeps what it has if it stops
    con.commit()
    return stored, failed


def build(con, mcon, season):
    """The season's file (see the module doc)."""
    nz, nr = len(ZONES), len(ZONES) + 1
    gids = {g for (g,) in con.execute("SELECT gid FROM games WHERE season=?", (season,))}
    teams, players = {}, {}
    team = lambda t: teams.setdefault(t, [0] + [0] * nz + [0] * nr + [0] * nr)
    plyr = lambda p: players.setdefault(p, [0] + [0] * nz + [0] * nr + [0])
    for (gid, home, away) in mcon.execute("SELECT gid, home, away FROM games WHERE season=? AND home_pts IS NOT NULL", (season,)):
        if gid in gids:
            team(home)[0] += 1
            team(away)[0] += 1
    marks = ",".join("?" * len(gids)) or "NULL"
    for opp, ast_pid, z in con.execute(f"SELECT opp, ast_pid, zone FROM makes WHERE ast_pid IS NOT NULL AND gid IN ({marks})", list(gids)):
        team(opp)[1 + z] += 1
        plyr(ast_pid)[1 + z] += 1
    for tm, opp, pid, kind, z in con.execute(f"SELECT team, opp, pid, kind, zone FROM rebs WHERE gid IN ({marks})", list(gids)):
        team(opp)[1 + nz + z] += 1
        team(tm if kind == "o" else opp)[1 + nz + nr + z] += 1           # the shooter's team: his own miss, or theirs
        p = plyr(pid)
        p[1 + nz + z] += 1
        p[-1] += kind == "o"
    for pid, n in mcon.execute(f"SELECT p.pid, COUNT(*) FROM player_games p JOIN games g ON g.gid = p.gid WHERE g.season = ? "
                               f"AND p.min > 0 AND p.gid IN ({marks}) GROUP BY p.pid", [season] + list(gids)):
        if pid in players:
            players[pid][0] = n
    league = {"gp": sum(t[0] for t in teams.values()),
              "ast": [sum(t[1 + z] for t in teams.values()) for z in range(nz)],
              "reb": [sum(t[1 + nz + z] for t in teams.values()) for z in range(nr)],
              "miss": [sum(t[1 + nz + nr + z] for t in teams.values()) for z in range(nr)]}
    return {"season": season, "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "zones": list(ZONES), "league": league, "teams": teams,
            "players": {str(p): v for p, v in players.items() if v[0]}}


def write(out, doc):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f".{doc['season']}.json.tmp"
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    os.replace(tmp, out / f"{doc['season']}.json")


def main():
    import nba_matchup as MU
    import nba_research as R
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/pbp)")
    a = ap.parse_args()
    con = connect(DB)
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    cur = R.season_of(dt.datetime.now(R.ET).date().isoformat())
    seasons = (R.prev_season(cur), cur)
    stored, failed = fetch(con, mcon, seasons)
    for s in seasons:
        write(a.out, build(con, mcon, s))
    print(f"nba_pbp: {stored} games stored, {failed} not yet · {', '.join(seasons)} -> {a.out}")


if __name__ == "__main__":
    main()
