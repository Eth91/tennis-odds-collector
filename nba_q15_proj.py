#!/usr/bin/env python3
"""NBA_Q15 E7, step 1: the engine's ROLE1 v3 projection (minutes x rates) for every player-game, regular seasons
2023-24 / 2024-25 and postseasons 2023-2025, from the deployed code at 0d328161ae (read-only checkout, ENGINE).

Postseason games use their season's rows plus the postseason games before them (nba_q15_under_post.post_rows).

    python3 nba_q15_proj.py OUT.pkl [--engine ~/nba-engine-ro]      # {(date, pid, market): (projection, v3 minutes)}
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

    def dump(season, dates=None):
        for r in T.player_games(season):
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
