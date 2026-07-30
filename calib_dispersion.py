"""Solve for the DISPERSION that makes the reliability slope 1.0.

Shrinking the RATE by 0.552 only moved the probability slope 0.552 -> 0.608, because
P(>=k birdies) over 18 holes is a threshold function: it amplifies rate differences, so a rate
shrink does not pass through one-for-one. The constant has to be solved on the quantity we
actually care about — the calibration of the PROBABILITY — rather than assumed to transfer.

Bisects D on the out-of-sample reliability slope over ~20k leak-free player-rounds.
"""
import sqlite3
import statistics as st
from collections import defaultdict

import pga_birdies as B
import pga_ruler as RU

K_TARGET = 4
con = sqlite3.connect(B.DB)
rows = con.execute("SELECT player, tid, rnd, p3h, p3b, p4h, p4b, p5h, p5b "
                   "FROM birdie_rounds").fetchall()
con.close()
by_pl = defaultdict(list)
for pl, tid, rnd, a3, b3, a4, b4, a5, b5 in rows:
    by_pl[RU.norm(pl)].append((str(tid), rnd, a3 or 0, b3 or 0, a4 or 0, b4 or 0, a5 or 0, b5 or 0))
tot = defaultdict(lambda: [0, 0])
for v in by_pl.values():
    for _t, _r, a3, b3, a4, b4, a5, b5 in v:
        tot[3][0] += a3; tot[3][1] += b3
        tot[4][0] += a4; tot[4][1] += b4
        tot[5][0] += a5; tot[5][1] += b5
g = {p: (v[1] / v[0] if v[0] else .15) for p, v in tot.items()}

# precompute each player's early-half raw shrunk rate and their late-half rounds ONCE
cells = []
for pl, v in by_pl.items():
    if len(v) < 10:
        continue
    v.sort(key=lambda z: (z[0], z[1]))
    h = len(v) // 2
    agg = {3: [0, 0], 4: [0, 0], 5: [0, 0]}
    for _t, _r, a3, b3, a4, b4, a5, b5 in v[:h]:
        agg[3][0] += a3; agg[3][1] += b3
        agg[4][0] += a4; agg[4][1] += b4
        agg[5][0] += a5; agg[5][1] += b5
    base = {}
    for par in (3, 4, 5):
        hh, bb = agg[par]
        kh = B.K_H_PAR.get(par, B.K_H)
        base[par] = (bb + kh * g[par]) / (hh + kh)
    late = []
    for _t, _r, a3, b3, a4, b4, a5, b5 in v[h:]:
        mixr = {3: a3, 4: a4, 5: a5}
        if sum(mixr.values()) >= 15:
            late.append((mixr, 1.0 if (b3 + b4 + b5) >= K_TARGET else 0.0))
    if late:
        cells.append((base, late))
print("players %d, out-of-sample rounds %d" % (len(cells), sum(len(c[1]) for c in cells)))


def slope_for(D):
    preds, obs = [], []
    for base, late in cells:
        rate = {par: min(g[par] + D * (base[par] - g[par]), 0.95) for par in (3, 4, 5)}
        for mixr, y in late:
            preds.append(B.p_x_or_more(rate, K_TARGET, mixr))
            obs.append(y)
    srt = sorted(zip(preds, obs))
    nb, sz = 10, len(srt) // 10
    xs, ys = [], []
    for i in range(nb):
        ch = srt[i * sz:(i + 1) * sz] if i < nb - 1 else srt[i * sz:]
        if ch:
            xs.append(st.mean(c[0] for c in ch))
            ys.append(st.mean(c[1] for c in ch))
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0


print()
print("  D (rate shrink)   reliability slope on P(>=%d)" % K_TARGET)
for D in (1.0, 0.75, 0.552, 0.4, 0.3, 0.2, 0.1):
    print("     %.3f            %+.3f" % (D, slope_for(D)))
lo, hi = 0.01, 1.0
for _ in range(28):
    mid = (lo + hi) / 2
    if slope_for(mid) < 1.0:
        hi = mid
    else:
        lo = mid
D = (lo + hi) / 2
print()
print("  SOLVED: D = %.4f gives reliability slope %+.3f" % (D, slope_for(D)))
print("  (currently in force: %.4f)" % B.DISPERSION)
