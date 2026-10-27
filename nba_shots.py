#!/usr/bin/env python3
"""Shot zones for the props page's Matchup shot chart: docs/shots/{season}.json — every player's makes and attempts in
the six court zones (stats.nba.com leaguedashplayershotlocations, By Zone), what every team lets its opponents make
and take in each (leaguedashteamshotlocations, MeasureType=Opponent), each team's games played (nba_matchup's
finals) and the league's totals. Two requests a season; the current season is fetched every run, a past season once.

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


if __name__ == "__main__":
    main()
