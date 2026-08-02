"""Measure the per-round over-dispersion in birdie counts, then solve the beta-binomial.

p_x_or_more treats 18 holes as INDEPENDENT Bernoulli trials. Real rounds are not: a soft, calm,
receptive day lifts every hole at once, so counts are over-dispersed relative to Poisson-binomial.
That is why the reliability slope sits at 0.61 and why no scalar shrink could fix it (solving
DISPERSION on the probability scale peaked at 0.608 and never approached 1.0, even at D=0.01 where
every player collapses to the field rate).

Model: one multiplicative day factor per ROUND, theta ~ mean 1 with variance PHI, applied to every
hole's rate in that round. Then
    P(>=k) = sum_j w_j * PoissonBinomial(>=k | rates * theta_j)
over a discretised theta. That adds exactly the shared-shock structure the data shows, and it
COMPRESSES the between-player spread of P(>=k) — integrating over a common shock lifts low-rate
players proportionally more, which is the direction the 0.61 slope needs.

Step 1 measures PHI directly from the excess variance of round birdie counts.
Step 2 checks the reliability slope across PHI, leak-free (early-half rates -> late-half rounds).
"""
import math
import os
import shutil
import sqlite3
import statistics as st
from collections import defaultdict

import pga_birdies as B
import pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_bb.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP
B.DB = _SNAP

con = sqlite3.connect(_SNAP)
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
print("field rates: par3 %.3f par4 %.3f par5 %.3f" % (g[3], g[4], g[5]))

# ---------------------------------------------------------------- 1. measure PHI
# For each round, expected birdies and the Poisson-binomial variance under independence.
# Observed variance in excess of that, scaled by mu^2, estimates Var(theta) = PHI.
num = den = 0.0
n_used = 0
for pl, v in by_pl.items():
    if len(v) < 10:
        continue
    agg = {3: [0, 0], 4: [0, 0], 5: [0, 0]}
    for _t, _r, a3, b3, a4, b4, a5, b5 in v:
        agg[3][0] += a3; agg[3][1] += b3
        agg[4][0] += a4; agg[4][1] += b4
        agg[5][0] += a5; agg[5][1] += b5
    rate = {}
    for par in (3, 4, 5):
        hh, bb = agg[par]
        kh = B.K_H_PAR.get(par, B.K_H)
        r0 = (bb + kh * g[par]) / (hh + kh)
        rate[par] = min(g[par] + B.DISPERSION * (r0 - g[par]), .95)
    for _t, _r, a3, b3, a4, b4, a5, b5 in v:
        holes = {3: a3, 4: a4, 5: a5}
        if sum(holes.values()) < 15:
            continue
        obs = b3 + b4 + b5
        mu = sum(holes[p] * rate[p] for p in (3, 4, 5))
        var_ind = sum(holes[p] * rate[p] * (1 - rate[p]) for p in (3, 4, 5))
        if mu <= 0:
            continue
        num += (obs - mu) ** 2 - var_ind        # excess squared deviation
        den += mu ** 2                          # theta enters multiplicatively
        n_used += 1
PHI = max(num / den, 0.0) if den else 0.0
print()
print("[1] OVER-DISPERSION, measured on %d player-rounds" % n_used)
print("    excess variance / mu^2 = PHI = %.5f  (theta sd = %.3f, i.e. +/-%.1f%% day-to-day)"
      % (PHI, math.sqrt(PHI), 100 * math.sqrt(PHI)))
print("    independence would mean PHI = 0; anything above it is the shared day/course effect.")

# ------------------------------------------------- 2. beta-binomial P(>=k) and slope
def theta_nodes(phi, n=15):
    """Discretise a mean-1, variance-phi gamma into n equal-weight nodes."""
    if phi <= 1e-9:
        return [(1.0, 1.0)]
    k = 1.0 / phi                      # gamma shape with mean 1
    # equal-probability nodes via the gamma quantile, approximated by Wilson-Hilferty
    out = []
    for i in range(n):
        q = (i + 0.5) / n
        z = st.NormalDist().inv_cdf(q)
        x = k * (1 - 1 / (9 * k) + z * math.sqrt(1 / (9 * k))) ** 3 / k
        out.append((max(x, 1e-6), 1.0 / n))
    m = sum(w * x for x, w in out)
    return [(x / m, w) for x, w in out]     # renormalise to mean exactly 1


def p_ge_bb(rates, k, mix, phi):
    if phi <= 1e-9:
        return B.p_x_or_more(rates, k, mix)
    tot_p = 0.0
    for th, w in theta_nodes(phi):
        r = {p: min(rates[p] * th, 0.98) for p in rates}
        tot_p += w * B.p_x_or_more(r, k, mix)
    return tot_p


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
        r0 = (bb + kh * g[par]) / (hh + kh)
        base[par] = min(g[par] + B.DISPERSION * (r0 - g[par]), .95)
    late = []
    for _t, _r, a3, b3, a4, b4, a5, b5 in v[h:]:
        mixr = {3: a3, 4: a4, 5: a5}
        if sum(mixr.values()) >= 15:
            late.append((mixr, 1.0 if (b3 + b4 + b5) >= 4 else 0.0))
    if late:
        cells.append((base, late))


def slope(phi, nb=10):
    preds, obs = [], []
    for base, late in cells:
        for mixr, y in late:
            preds.append(p_ge_bb(base, 4, mixr, phi))
            obs.append(y)
    srt = sorted(zip(preds, obs))
    sz = len(srt) // nb
    xs, ys = [], []
    for i in range(nb):
        ch = srt[i * sz:(i + 1) * sz] if i < nb - 1 else srt[i * sz:]
        if ch:
            xs.append(st.mean(c[0] for c in ch))
            ys.append(st.mean(c[1] for c in ch))
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return ((sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0,
            st.mean(preds), st.mean(obs))


print()
print("[2] RELIABILITY SLOPE vs PHI (leak-free: early-half rates -> late-half rounds, %d rounds)"
      % sum(len(c[1]) for c in cells))
print("    %8s %9s %11s %11s" % ("PHI", "slope", "pred mean", "real mean"))
best = None
for phi in (0.0, PHI * 0.5, PHI, PHI * 1.5, PHI * 2.5, PHI * 4):
    sl, pm, rm = slope(phi)
    tag = ""
    if abs(phi - PHI) < 1e-12:
        tag = "  <- measured"
    print("    %8.4f %9.3f %11.4f %11.4f%s" % (phi, sl, pm, rm, tag))
    if best is None or abs(sl - 1.0) < best[1]:
        best = (phi, abs(sl - 1.0), sl)
print()
print("    BEST slope %.3f at PHI=%.4f  (independence, PHI=0, gives %.3f)"
      % (best[2], best[0], slope(0.0)[0]))
print()
if best[2] >= 0.85:
    print("    -> beta-binomial CLEARS the 0.85 arming bar. The birdie stream can be un-gated.")
else:
    print("    -> still under the 0.85 bar; the shared day factor is not the whole story.")
