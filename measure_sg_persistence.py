"""Which SG categories predict NEXT season, and which are noise? This sets the weights.

The whole premise of wiring SG in is that total score conflates a persistent skill (approach) with
a near-noise one (putting), so two players on the same rating are not equally repeatable. That is a
CLAIM until measured. Two things worth knowing, and they are different:

  SELF-PERSISTENCE   corr(SG_X in year Y, SG_X in year Y+1) — does the skill itself repeat?
  FORWARD POWER      corr(SG_X in year Y, SG_TOT in year Y+1) — does it predict future TOTAL
                     performance, which is what we actually price?

A category can be persistent and still not help (if it is already fully reflected in total score),
so FORWARD POWER against the part of next year our rating MISSES is the real test. Reported as a
partial: corr(SG_X this year, SG_TOT next year) after removing SG_TOT this year.
"""
import os
import shutil
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_sgp.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP
con = sqlite3.connect(_SNAP)
rows = con.execute("SELECT year, stat, player, avg FROM sg_stats WHERE avg IS NOT NULL").fetchall()
con.close()

by = defaultdict(dict)                      # (player, year) -> {stat: avg}
for yr, stat, player, avg in rows:
    by[(RU.norm(player), yr)][stat] = avg
years = sorted({y for _p, y in by})
print("seasons: %s | player-seasons: %d" % (years, len(by)))

CATS = ["SG_OTT", "SG_APP", "SG_ARG", "SG_PUTT", "SG_T2G", "SG_TOT"]


def corr(pairs):
    if len(pairs) < 25:
        return None, len(pairs)
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if not sx or not sy:
        return None, len(pairs)
    return sum((a - mx) * (b - my) for a, b in pairs) / len(pairs) / (sx * sy), len(pairs)


print()
print("  %-9s %14s %16s %20s" % ("category", "self-persist", "predicts SG_TOT", "PARTIAL (adds to"))
print("  %-9s %14s %16s %20s" % ("", "Y -> Y+1", "next year", "SG_TOT this year)"))
weights = {}
for c in CATS:
    self_p, n1 = corr([(by[(p, y)][c], by[(p, y + 1)][c])
                       for (p, y) in by
                       if (p, y + 1) in by and c in by[(p, y)] and c in by[(p, y + 1)]])
    fwd, n2 = corr([(by[(p, y)][c], by[(p, y + 1)]["SG_TOT"])
                    for (p, y) in by
                    if (p, y + 1) in by and c in by[(p, y)] and "SG_TOT" in by[(p, y + 1)]])
    # partial: residualise both sides on SG_TOT this year, so we see what the category adds
    trip = [(by[(p, y)][c], by[(p, y)]["SG_TOT"], by[(p, y + 1)]["SG_TOT"])
            for (p, y) in by
            if (p, y + 1) in by and c in by[(p, y)] and "SG_TOT" in by[(p, y)]
            and "SG_TOT" in by[(p, y + 1)]]
    part = None
    if len(trip) >= 25:
        def resid(idx, ctrl=1):
            xs = [t[idx] for t in trip]
            zs = [t[ctrl] for t in trip]
            mz = st.mean(zs)
            den = sum((z - mz) ** 2 for z in zs)
            mx_ = st.mean(xs)
            b = (sum((x - mx_) * (z - mz) for x, z in zip(xs, zs)) / den) if den else 0
            a = mx_ - b * mz
            return [x - (a + b * z) for x, z in zip(xs, zs)]
        part, _ = corr(list(zip(resid(0), resid(2))))
    weights[c] = part
    print("  %-9s %13s %15s %19s"
          % (c,
             ("%+.3f (n=%d)" % (self_p, n1)) if self_p is not None else "n/a",
             ("%+.3f" % fwd) if fwd is not None else "n/a",
             ("%+.3f" % part) if part is not None else "n/a"))
print()
print("  self-persist: does the skill repeat.  predicts: raw forward power.")
print("  PARTIAL is the one that matters — what the category adds ONCE this year's total is known.")
print("  A category with high self-persistence but ~0 partial is already priced by total score.")
usable = {c: v for c, v in weights.items() if v is not None and c not in ("SG_TOT", "SG_T2G")}
if usable:
    best = max(usable.items(), key=lambda kv: kv[1])
    worst = min(usable.items(), key=lambda kv: kv[1])
    print()
    print("  strongest ADDITION: %s (%+.3f)   weakest: %s (%+.3f)"
          % (best[0], best[1], worst[0], worst[1]))
    if best[1] < 0.10:
        print("  -> NOTHING adds much beyond total score. Wiring SG in is unlikely to help;")
        print("     say so rather than shipping a change that cannot be justified.")
