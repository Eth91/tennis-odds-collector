#!/usr/bin/env python3
"""NBA_MINUTES_PREREG.md amendment 7: blowouts in the minutes base (fix B).

V3's base is the plain mean of his last 5 games; fix B counts a game decided by M+ points with weight w. M and w are fit
on 2023-24 by the MAE over every player-game and read on 2024-25; then gate 2, UNDER20's ping set with fix B's minutes.
Mac only (.projdata).

    python3 nba_blowout.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_minutes_v4 as V4

MS, WS = (10, 15, 20), (0.0, 0.25, 0.5, 0.75)
GATE_ALL, GATE_GROUP, GATE_ROI = 0.05, 0.02, 0.01
OUT = Path(__file__).resolve().parent / ".projdata" / "blowout_result.json"


def margins(rows_db):
    """{gid: final margin} from the sum of each team's points in the box scores."""
    pts = defaultdict(lambda: defaultdict(float))
    for rs in rows_db.values():
        for r in rs:
            pts[r["gid"]][r["team"]] += r["pts"] or 0
    return {g: abs(t[a] - t[b]) for g, t in pts.items() if len(t) == 2 for a, b in [tuple(t)]}


def weight(mg, m, w):
    return lambda gid: w if mg.get(gid, 0) >= m else 1.0


class Blowout:
    """Fix B's minutes per night for (M, w), cached."""

    def __init__(self, season, ns, mg):
        self.season, self.ns, self.mg, self.cache = season, ns, mg, {}

    def minutes(self, i, m, w):
        key = (i, m, w)
        if key not in self.cache:
            n, s = self.ns[i], self.season
            pr = V4.project_s(s.role, s.priors, s.groups, n["team"], n["date"], n["active"], n["absent"], wt=weight(self.mg, m, w))
            self.cache[key] = {p: pr[p] for p in n["v3"]}
        return self.cache[key]


def main():
    sys.path.insert(0, ".")
    g = {}
    exec(open("nba_tests4_checks.py").read().split("NAMES = [")[0], g)   # seasons, rows (V3 x rates), tip lines
    seasons, rows, lines, T = g["seasons"], g["rows"], g["lines"], g["T"]
    mg = margins(g["rows_db"])
    ns = {s: V4.nights(seasons[s]) for s in seasons}
    bl = {s: Blowout(seasons[s], ns[s], mg) for s in seasons}
    s23 = ns["2023-24"]
    every = lambda n, p: True
    grid = {(m, w): V4.mae(s23, lambda i, p, m=m, w=w: bl["2023-24"].minutes(i, m, w)[p], every)[0] for m in MS for w in WS}
    v3_23 = V4.mae(s23, lambda i, p: s23[i]["v3"][p], every)[0]
    (m_b, w_b), best = min(grid.items(), key=lambda kv: kv[1])
    print(f"fit on 2023-24 (V3 {v3_23:.4f}): " + "  ".join(f"M{m} w{w} {e:.4f}" for (m, w), e in sorted(grid.items())))
    print(f"pick M {m_b}, w {w_b}")

    res = {"grid": {f"{m} {w}": e for (m, w), e in grid.items()}, "m": m_b, "w": w_b, "mae": {}}
    for s in ("2023-24", "2024-25"):
        n_, se = ns[s], seasons[s]
        blow = {}                                            # (night, pid) -> a blowout among his last 5 games
        for i, n in enumerate(n_):
            prior = se.role.before(n["team"], n["date"])
            for p in n["act"]:
                last = [gd for _d, gd, b in prior if p in b and b[p]["min"]][-5:]
                blow[(i, p)] = any(mg.get(gd, 0) >= m_b for gd in last)
        cuts = {"all": every, "starters": lambda n, p: n["starter"][p], "bench": lambda n, p: not n["starter"][p],
                "starters, a blowout in his last 5": None}
        res["mae"][s] = {}
        for name, f in (("V3", lambda i, p: n_[i]["v3"][p]), ("B", lambda i, p: bl[s].minutes(i, m_b, w_b)[p])):
            row = {}
            for c, sel in cuts.items():
                if sel is None:
                    err = [abs(f(i, p) - n["act"][p]) for i, n in enumerate(n_) for p in n["act"] if n["starter"][p] and blow[(i, p)]]
                    row[c] = (float(np.mean(err)), len(err))
                else:
                    row[c] = V4.mae(n_, f, sel)
            res["mae"][s][name] = row
            print(f"{s} {name:2s} " + "  ".join(f"{c} {v[0]:.3f} (n {v[1]})" for c, v in row.items()))
    m25 = res["mae"]["2024-25"]
    gain = m25["V3"]["all"][0] - m25["B"]["all"][0]
    worst = max(m25["B"][c][0] - m25["V3"][c][0] for c in ("starters", "bench"))
    gate1 = gain >= GATE_ALL and worst <= GATE_GROUP
    print(f"\ngate 1: 2024-25 overall {gain:+.3f} better (need >= {GATE_ALL}); worst group {worst:+.3f} (need <= {GATE_GROUP}) "
          f"-> {'PASS' if gate1 else 'FAIL'}")

    unders = {s: {"V3": V4.under_set(rows[s], lines, T.MARKETS, ns[s], lambda i, p, s=s: ns[s][i]["v3"][p]),
                  "B": V4.under_set(rows[s], lines, T.MARKETS, ns[s], lambda i, p, s=s: bl[s].minutes(i, m_b, w_b)[p])}
              for s in ("2023-24", "2024-25")}
    for s, u in unders.items():
        print(f"{s} UNDER20 ping set: " + "  ".join(f"{k} n {v[0]} ROI {v[1]:+.3f}" for k, v in u.items()))
    gate2 = unders["2024-25"]["B"][1] >= unders["2024-25"]["V3"][1] - GATE_ROI
    print(f"gate 2: {'PASS' if gate2 else 'FAIL'}")
    res.update(gate1=gate1, gate2=gate2, unders=unders)
    OUT.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
