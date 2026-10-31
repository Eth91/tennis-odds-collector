#!/usr/bin/env python3
"""NBA_Q15 E7, step 1: the engine's ROLE1 v3 projection (minutes x rates) for every player-game, regular seasons
2023-24 / 2024-25 and postseasons 2023-2025, from the deployed code at 0d328161ae (read-only checkout, ENGINE).

Postseason games use their season's rows plus the postseason games before them (nba_q15_under_post.post_rows).

    python3 nba_q15_proj.py OUT.pkl [--engine ~/nba-engine-ro] [--mode box|rot|lag]   # {(date, pid, market): (projection, v3 minutes)}

Who is out tonight (the projection rescales the team's minutes to 240 over the players it treats as active):
- box: the engine's backtest as deployed. Every player from the team's last 3 games who logged no minutes tonight is
  out. A deep-bench player's DNP-CD in a close game, against his garbage-time minutes in a blowout, leaks the final
  margin into the projection.
- rot: only rotation players (the engine's absences filter, 17+ minutes over 3+ games) can be out. The deep bench is
  active.
- lag: rot, and only players who also missed the team's previous game: no first-night absence at all.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--engine", default=str(Path.home() / "nba-engine-ro"))
    ap.add_argument("--mode", choices=("box", "rot", "lag"), default="box")
    a = ap.parse_args()
    sys.path.insert(0, a.engine)
    sys.path.append(str(HERE))
    import nba_boost as BOOST
    import nba_lowend as LO
    import nba_minutes as M
    import nba_tests4 as T
    from nba_q15_under_post import post_rows
    for P in (BOOST.PREV, getattr(M, "PREV", BOOST.PREV)):
        P.setdefault("2022-23", "2021-22")
    rows, pos, five = LO.load()
    rows.setdefault("2021-22", [])
    post = post_rows(five)
    out = {}

    def games(season):
        """T.player_games' projection, with tonight's outs per --mode (box is T.player_games itself)."""
        if a.mode == "box":
            yield from T.player_games(season)
            return
        bd, s_ = season.bd, season.s
        for team, gs in sorted(bd.games.items()):
            for d, gid, g_s, box in gs:
                if g_s != s_:
                    continue
                played = {p for p, x in box.items() if x["min"]}
                starters = bd.usual_five(team, d) or bd.starters(team, d)
                out_all = (bd.on_team_tonight(team, d) - played) & (bd.roster(team, d) | starters)
                outs = set(season.role.absences(team, d, out_all))
                if a.mode == "lag":
                    outs = {x for x in outs if bd.absence_n(x, team, d) >= 2}
                v3 = season.v3(team, d, outs)
                for p in sorted(played):
                    rt = BOOST.rates(bd, p, d)
                    if p in v3 and rt:
                        yield {"date": d, "pid": p, "min": v3[p]["min"], "rt": rt}

    def dump(season, dates=None):
        for r in games(season):
            if dates is None or r["date"] in dates:
                for mk in T.MARKETS:
                    out[(r["date"], int(r["pid"]), mk)] = (float(T.proj(r, mk)), float(r["min"]))

    for s in ("2023-24", "2024-25"):
        dump(M.Season(s, rows, pos, five))
    for s in ("2022-23", "2023-24", "2024-25"):
        rs = dict(rows)
        rs[s] = sorted(rows.get(s, []) + post[s], key=lambda r: (r["date"], r["gid"]))
        dump(M.Season(s, rs, pos, five), {r["date"] for r in post[s]})
    with open(a.out, "wb") as f:
        pickle.dump(out, f)
    print(len(out), "player-game-markets")


if __name__ == "__main__":
    main()
