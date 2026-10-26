#!/usr/bin/env python3
"""Box scores for the props page: one small JSON per final game, docs/box/{gid}.json, so a tap on a chart bar opens
that game's box score. Which finals exist comes from nba_matchup.sqlite's games (read-only); the box itself from
cdn.nba.com liveData (nba_rosters._get), fetched once per game: a final box does not change, so a written file is
never fetched again.

File: {gid, date, status, teams: [away, home]}; a team is {tri, pts, home, players, dnp, tot}:
  players  [[pid, name, starter, min, pts, reb, ast, fgm, fga, fg3m, fg3a, ftm, fta, stl, blk, tov, pf, pm]] in the
           box's order (starters first), only those who played
  dnp      [[name, reason]] the rest (reason: the box's description, else "DNP")
  tot      [pts, reb, ast, fgm, fga, fg3m, fg3a, ftm, fta, stl, blk, tov, pf]

    python3 nba_boxscore.py --out /home/ubuntu/tennis-odds-collector/docs/box     # write the missing ones
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nba_matchup as MU

LINE = ("points", "reboundsTotal", "assists", "fieldGoalsMade", "fieldGoalsAttempted", "threePointersMade",
        "threePointersAttempted", "freeThrowsMade", "freeThrowsAttempted", "steals", "blocks", "turnovers",
        "foulsPersonal")


def compact(b):
    """A cdn.nba.com liveData game dict -> the page's box score, or None while the game is not final."""
    if b.get("gameStatus") != 3:
        return None
    teams = []
    for side, home in ((b["awayTeam"], False), (b["homeTeam"], True)):
        players, dnp = [], []
        for p in side.get("players", []):
            s = p.get("statistics") or {}
            mn = MU._minutes(s.get("minutes"))
            if str(p.get("played")) != "1" or mn <= 0:
                dnp.append([p.get("name") or "", (p.get("notPlayingDescription") or "").strip() or "DNP"])
                continue
            players.append([int(p["personId"]), p.get("name") or "", int(str(p.get("starter")) == "1"), int(mn + .5)]
                           + [s.get(k, 0) for k in LINE] + [round(s.get("plusMinusPoints", 0))])
        st = side.get("statistics") or {}
        teams.append({"tri": side["teamTricode"], "pts": side.get("score"), "home": home, "players": players,
                      "dnp": dnp, "tot": [st.get(k, 0) for k in LINE]})
    return {"gid": b["gameId"], "date": MU.parse_box(b)[0][2], "status": b.get("gameStatusText") or "Final",
            "teams": teams}


def write_missing(con, out, get=None, workers=4):
    """Write docs/box/{gid}.json for every final game in the cache that has none. Returns (written, failed)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    todo = [g for (g,) in con.execute("SELECT gid FROM games WHERE home_pts IS NOT NULL ORDER BY date DESC")
            if not (out / f"{g}.json").exists()]
    if get is None:
        import nba_rosters as R
        get = lambda g: R._get(R.BOX.format(g))["game"]

    def one(g):
        try:
            return compact(get(g))
        except Exception:                                                    # noqa: BLE001
            return None
    written = failed = 0
    with ThreadPoolExecutor(workers) as ex:
        for g, box in zip(todo, ex.map(one, todo)):
            if not box:
                failed += 1
                continue
            tmp = out / f".{g}.json.tmp"
            tmp.write_text(json.dumps(box, separators=(",", ":")))
            os.replace(tmp, out / f"{g}.json")
            written += 1
    return written, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the box score folder the page reads (docs/box)")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    written, failed = write_missing(con, a.out, workers=a.workers)
    print(f"nba_boxscore: {written} written, {failed} failed -> {a.out}")


if __name__ == "__main__":
    main()
