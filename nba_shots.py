#!/usr/bin/env python3
"""Shot zones for the props page's Matchup shot chart: docs/shots/{season}.json — every player's makes and attempts in
the six court zones (stats.nba.com leaguedashplayershotlocations, By Zone), what every team lets its opponents make
and take in each (leaguedashteamshotlocations, MeasureType=Opponent), each team's games played (nba_matchup's
finals) and the league's totals. Two requests a season; the current season is fetched every run, a past season once.

Every shot too, for the dots: stats.nba.com shotchartdetail with PlayerID=0 / TeamID=0 is the whole league's shots for a
season (court position, made or missed). A response stops at 102,400 rows, so it is fetched a month at a time; a month
over (and three days past) is marked and never fetched again, the open one whole on every run (a cut-off response can
leave holes anywhere in it, so "since the last stored shot" is not safe).
They are kept in nba_shots.sqlite, and docs/shots/p/{pid}.json holds each player's:
{pid, s: {season: [x, y, made, x, y, made, ...]}} in the court's tenths of a foot (basket at 0,0), past half court left out.

Zones, in order: Restricted Area, Paint (non-RA), Mid-Range, Left Corner 3, Right Corner 3, Above the Break 3.
File: {season, fetched_at, league: [[fgm, fga] x 6], players: {pid: [[fgm, fga] x 6]},
       teams: {TRI: {gp, opp: [[fgm, fga] x 6]}}}

    python3 nba_shots.py --out /home/ubuntu/tennis-odds-collector/docs/shots
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import time
from collections import Counter
from pathlib import Path

ZONES = ("Restricted Area", "In The Paint (Non-RA)", "Mid-Range", "Left Corner 3", "Right Corner 3", "Above the Break 3")
URL = ("https://stats.nba.com/stats/{ep}?College=&Conference=&Country=&DateFrom=&DateTo=&DistanceRange=By%20Zone"
       "&Division=&DraftPick=&DraftYear=&GameScope=&GameSegment=&Height=&ISTRound=&LastNGames=0&LeagueID=00&Location="
       "&MeasureType={measure}&Month=0&OpponentTeamID=0&Outcome=&PORound=0&PaceAdjust=N&PerMode=Totals&Period=0"
       "&PlayerExperience=&PlayerPosition=&PlusMinus=N&Rank=N&Season={season}&SeasonSegment="
       "&SeasonType=Regular%20Season&ShotClockRange=&StarterBench=&TeamID=0&VsConference=&VsDivision=&Weight=")


SHOTS_URL = ("https://stats.nba.com/stats/shotchartdetail?AheadBehind=&CFID=&CFPARAMS=&ClutchTime=&Conference="
             "&ContextFilter=&ContextMeasure=FGA&DateFrom={d0}&DateTo={d1}&Division=&EndPeriod=10&EndRange=28800&GROUP_ID="
             "&GameEventID=&GameID=&GameSegment=&GroupID=&GroupMode=&GroupQuantity=5&LastNGames=0&LeagueID=00&Location="
             "&Month=0&OnOff=&OpponentTeamID=0&Outcome=&PORound=0&Period=0&PlayerID=0&PlayerID1=&PlayerID2=&PlayerID3="
             "&PlayerID4=&PlayerID5=&PlayerPosition=&PointDiff=&Position=&RangeType=0&RookieYear=&Season={season}"
             "&SeasonSegment=&SeasonType=Regular%20Season&ShotClockRange=&StartPeriod=1&StartRange=0&StarterBench="
             "&TeamID=0&VsConference=&VsDivision=&VsPlayerID1=&VsPlayerID2=&VsPlayerID3=&VsPlayerID4=&VsPlayerID5=&VsTeamID=")
SHOTS_DB = Path(__file__).resolve().parent / "nba_shots.sqlite"
HALF = 420                                       # tenths of a foot from the basket to half court (beyond: heaves)
DDL = """CREATE TABLE IF NOT EXISTS shots (season TEXT, gid TEXT, event INTEGER, pid INTEGER, team_id INTEGER, date TEXT,
    x INTEGER, y INTEGER, made INTEGER, PRIMARY KEY (gid, event));
CREATE TABLE IF NOT EXISTS fetched (season TEXT, month TEXT, PRIMARY KEY (season, month));"""


def _get(url, tries=4):
    from curl_cffi import requests as cr
    import nba_tracking as T
    err = None
    for k in range(tries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=60, headers=T.H)
            if r.status_code == 200:
                return r.json()
            err = f"HTTP {r.status_code}"
        except Exception as e:                                              # timeouts, resets
            err = type(e).__name__
        time.sleep(5 * (k + 1))
    raise RuntimeError(f"gave up after {tries} tries ({err})")


def zones(j, lead):
    """{first column: [[fgm, fga] x 6]} from a By Zone response; `lead` = the columns before the zone triples."""
    rs = j["resultSets"]
    rs = rs if isinstance(rs, dict) else rs[0]
    cats = next(h["columnNames"] for h in rs["headers"] if h.get("name") == "SHOT_CATEGORY")
    at = [lead + 3 * cats.index(z) for z in ZONES]
    return {row[0]: [[int(row[i] or 0), int(row[i + 1] or 0)] for i in at] for row in rs["rowSet"]}


def build(season, players_j, teams_j, gp, tri_of):
    """The season's file. gp: {TRI: games}; tri_of: {team id: TRI}."""
    players = {str(pid): z for pid, z in zones(players_j, 6).items() if any(a for _, a in z)}
    teams = {}
    for tid, z in zones(teams_j, 2).items():
        tri = tri_of.get(int(tid))
        if tri:
            teams[tri] = {"gp": gp.get(tri, 0), "opp": z}
    league = [[sum(t["opp"][k][0] for t in teams.values()), sum(t["opp"][k][1] for t in teams.values())]
              for k in range(len(ZONES))]
    return {"season": season, "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "league": league, "players": players, "teams": teams}


def store_shots(con, season, j):
    """Add a shotchartdetail response's shots to the store. Returns the number of rows it carried."""
    rs = j["resultSets"][0] if isinstance(j["resultSets"], list) else j["resultSets"]
    ix = {h: k for k, h in enumerate(rs["headers"])}
    rows = [(season, r[ix["GAME_ID"]], r[ix["GAME_EVENT_ID"]], r[ix["PLAYER_ID"]], r[ix["TEAM_ID"]],
             "{}-{}-{}".format(r[ix["GAME_DATE"]][:4], r[ix["GAME_DATE"]][4:6], r[ix["GAME_DATE"]][6:]),
             r[ix["LOC_X"]], r[ix["LOC_Y"]], int(r[ix["SHOT_MADE_FLAG"]] or 0)) for r in rs["rowSet"]]
    con.executemany("INSERT OR IGNORE INTO shots VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)


def _months(season):
    y = int(season[:4])
    for k in range(9):                                         # October to June
        m0 = dt.date(y + (k + 9) // 12, (k + 9) % 12 + 1, 1)
        m1 = dt.date(m0.year + m0.month // 12, m0.month % 12 + 1, 1) - dt.timedelta(days=1)
        yield m0, m1


def fetch_shots(con, season, get=None, today=None):
    """Fetch the season a month at a time: a month already marked is skipped, an open one is fetched whole, a month
    over by three days is marked done. Returns the rows fetched."""
    get, today = get or _get, today or dt.date.today()
    q = lambda d: f"{d.month:02d}%2F{d.day:02d}%2F{d.year}"
    n = 0
    for m0, m1 in _months(season):
        if m0 > today:
            break
        if con.execute("SELECT 1 FROM fetched WHERE season=? AND month=?", (season, m0.isoformat()[:7])).fetchone():
            continue
        n += store_shots(con, season, get(SHOTS_URL.format(season=season, d0=q(m0), d1=q(m1))))
        if m1 + dt.timedelta(days=3) < today:
            con.execute("INSERT OR IGNORE INTO fetched VALUES (?, ?)", (season, m0.isoformat()[:7]))
            con.commit()
    return n


def write_player_shots(con, out, seasons):
    """docs/shots/p/{pid}.json for every player with a shot in `seasons`. Returns how many were written."""
    out = Path(out) / "p"
    out.mkdir(parents=True, exist_ok=True)
    marks = ",".join("?" * len(seasons))
    per = {}
    for pid, season, x, y, made in con.execute(
            f"SELECT pid, season, x, y, made FROM shots WHERE season IN ({marks}) AND y <= ? ORDER BY date, gid, event",
            list(seasons) + [HALF]):
        per.setdefault(pid, {}).setdefault(season, []).extend((x, y, made))
    for pid, s in per.items():
        tmp = out / f".{pid}.json.tmp"
        tmp.write_text(json.dumps({"pid": pid, "s": s}, separators=(",", ":")))
        os.replace(tmp, out / f"{pid}.json")
    return len(per)


def games_played(mcon, season):
    c = Counter()
    for h, a in mcon.execute("SELECT home, away FROM games WHERE season=? AND home_pts IS NOT NULL", (season,)):
        c[h] += 1
        c[a] += 1
    return dict(c)


def write(out, season, mcon, get=None, tri_of=None):
    get = get or _get
    if tri_of is None:
        from nba_board import TEAM_ID
        tri_of = {int(v): k for k, v in TEAM_ID.items()}
    pj = get(URL.format(ep="leaguedashplayershotlocations", measure="Base", season=season))
    tj = get(URL.format(ep="leaguedashteamshotlocations", measure="Opponent", season=season))
    doc = build(season, pj, tj, games_played(mcon, season), tri_of)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f".{season}.json.tmp"
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    os.replace(tmp, out / f"{season}.json")
    return doc


def main():
    import nba_matchup as MU
    import nba_research as R
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/shots)")
    a = ap.parse_args()
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    cur = R.season_of(dt.datetime.now(R.ET).date().isoformat())
    for s in (cur, R.prev_season(cur)):
        if s != cur and (Path(a.out) / f"{s}.json").exists():
            continue                                                     # a past season does not change
        d = write(a.out, s, mcon)
        print(f"nba_shots: {s} · {len(d['players'])} players · {len(d['teams'])} teams -> {a.out}")
    con = sqlite3.connect(SHOTS_DB)
    con.executescript(DDL)
    for s in (cur, R.prev_season(cur)):
        print(f"nba_shots: {s} · {fetch_shots(con, s)} shots fetched")
    print(f"nba_shots: dots for {write_player_shots(con, a.out, (R.prev_season(cur), cur))} players")


if __name__ == "__main__":
    main()
