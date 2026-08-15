#!/usr/bin/env python3
"""GM-010 — does correcting RHO improve the PROBABILITIES? Paired A/B, research model only.

GM-007/008 measured the within-event week effect on the cleanest samples available:
    R1 -> R2, full field, zero selection      +0.0954   t=+10.90   n=21,810 / 177 events
    stable in each year                       2023 +0.1192  2024 +0.1015  2025 +0.0835
    placebo, partner-swapped within event     0/200, p=0.000
    five of six round pairs (no-cut events)   +0.071 .. +0.100
    two-round averages imply, independently   rho ~ 0.086
The frozen model uses RHO = 0.050.

RHO is not a cosmetic constant. It is the share of a player's round-to-round variance that is
COMMON across their week, so it sets 72-hole variance: at rho the variance of a four-round total
is 4*sigma^2*(1 + 3*rho) rather than 4*sigma^2. Going 0.05 -> 0.085 widens the 72-hole
distribution by about 5%, which pushes matchups away from 50/50 and thins the top-N tails. The
model's own history says the direction matters: at RHO=0.25 it inflated 72-hole variance ~14% and
visibly distorted both.

So the question is not whether 0.085 is the better estimate -- three independent measurements say
it is -- but whether using it makes the probabilities the model SELLS better calibrated.

    A   rho = 0.050   the frozen model
    B   rho = 0.085   the measured value
Same field, same seed, same cut rule, same sigma. Common random numbers, so the arms differ only
by the constant. Determinism is asserted before anything is read; a paired A/B whose floor is not
EXACTLY zero is measuring simulation noise and every verdict is biased toward "no difference".

The R3-R4 anomaly from GM-008 is NOT modelled here. One rho is still assumed, because that is the
change being tested; a stage-dependent rho is a different and larger change.

2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import hashlib
import pickle
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU
import pga_sim as PS

EPS = 1e-9
NSIM = 8000
SEED = 4242
RHO_A = 0.050
RHO_B = 0.085

KEY = hashlib.sha1(("%s|%s|%s|%s" % (RU.HALF_LIFE_D, RU.K_SHRINK, RU.SIG_SHRINK,
                                     RU.MIN_ROUNDS)).encode()).hexdigest()[:12]
fits = pickle.load(open("ratings_cache_%s.pkl" % KEY, "rb"))
fd = sorted(fits)


def rf(d):
    lo, hi = 0, len(fd)
    while lo < hi:
        m = (lo + hi) // 2
        if fd[m] < d:
            lo = m + 1
        else:
            hi = m
    return fits[fd[lo - 1]] if lo > 0 else None


con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
rows = con.execute("SELECT event_id, event, date, player, rnd, score FROM rounds "
                   "WHERE date >= '2025-01-01' AND date < '2026-01-01'").fetchall()
con.close()
ev = defaultdict(lambda: defaultdict(dict))
em = {}
for eid, evn, d, pl, rnd, sc in rows:
    if sc is None:
        continue
    ev[eid][int(rnd)][pl] = float(sc)
    em[eid] = (str(evn), str(d))
print("2025 events: %d" % len(ev))

probe = sorted(ev)[0]
R = rf(em[probe][1])
fp = [p for p in ev[probe].get(1, {}) if PS.lookup(R, p) is not None]
names, mu, sg, _u, _c, _dd = PS.field_ratings(fp, R, spread=1.30)
pl_a = {n: (float(a), float(b)) for n, a, b in zip(names, mu, sg)}
r1 = PS.simulate(pl_a, n=3000, seed=SEED, cut_n=65, rho=RHO_A)
r2 = PS.simulate(pl_a, n=3000, seed=SEED, cut_n=65, rho=RHO_A)
dmax = max(abs(r1.win[p] - r2.win[p]) for p in r1.players)
print("DETERMINISM: identical runs differ by max %.10f -> %s"
      % (dmax, "EXACT" if dmax == 0.0 else "BROKEN"))
if dmax != 0.0:
    raise SystemExit("refusing a paired A/B without an exact CRN floor")

MK = ("cut", "top20", "top10", "top5", "win")
acc = {a: {k: [] for k in MK} for a in ("A", "B")}
Y = {k: [] for k in MK}
nev = 0
for i, eid in enumerate(sorted(ev), 1):
    byr = ev[eid]
    if 1 not in byr:
        continue
    R = rf(em[eid][1])
    if not R:
        continue
    fp = [p for p in byr[1] if PS.lookup(R, p) is not None]
    if len(fp) < 40:
        continue
    names, mu, sg, _u, _c, _dd = PS.field_ratings(fp, R, spread=1.30)
    if len(names) < 40:
        continue
    cut_n = RU.cut_rule(em[eid][0], em[eid][1], n_field=len(byr[1]))
    tot = {}
    for p in names:
        s = [byr[r].get(p) for r in (1, 2, 3, 4) if r in byr]
        tot[p] = (sum(x for x in s if x is not None), sum(1 for x in s if x is not None))
    played4 = {p: v[0] for p, v in tot.items() if v[1] == 4}
    if len(played4) < 20:
        continue
    made = {p for p, v in tot.items() if v[1] >= 3}
    pos = {p: 1 + sum(1 for q in played4 if played4[q] < played4[p]) for p in played4}
    P = {n: (float(a), float(b)) for n, a, b in zip(names, mu, sg)}
    ra = PS.simulate(P, n=NSIM, seed=SEED, cut_n=cut_n, rho=RHO_A)
    rb = PS.simulate(P, n=NSIM, seed=SEED, cut_n=cut_n, rho=RHO_B)
    started = set(byr[1])
    for p in names:
        if p not in started:
            continue
        y = dict(cut=1.0 if p in made else 0.0,
                 top20=1.0 if pos.get(p, 999) <= 20 else 0.0,
                 top10=1.0 if pos.get(p, 999) <= 10 else 0.0,
                 top5=1.0 if pos.get(p, 999) <= 5 else 0.0,
                 win=1.0 if pos.get(p, 999) == 1 else 0.0)
        for k in MK:
            Y[k].append(y[k])
            fa = (ra.make_cut if k == "cut" else ra.win_ties if k == "win"
                  else ra.top(int(k[3:]), ties=True))
            fb = (rb.make_cut if k == "cut" else rb.win_ties if k == "win"
                  else rb.top(int(k[3:]), ties=True))
            acc["A"][k].append(float(fa.get(p, 0.0)))
            acc["B"][k].append(float(fb.get(p, 0.0)))
    nev += 1
    if i % 20 == 0:
        print("   %d/%d" % (i, len(ev)), flush=True)
print("\nevents simulated: %d" % nev)


def ll(p, y):
    p = np.clip(np.asarray(p), EPS, 1 - EPS)
    y = np.asarray(y)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def slope(p, y):
    p = np.clip(np.asarray(p), 1e-6, 1 - 1e-6)
    x = np.log(p / (1 - p))
    y = np.asarray(y)
    b = np.array([0.0, 1.0])
    for _ in range(60):
        q = 1 / (1 + np.exp(-(b[0] + b[1] * x)))
        g = np.array([(q - y).sum(), ((q - y) * x).sum()])
        w = q * (1 - q) + 1e-9
        H = np.array([[w.sum(), (w * x).sum()], [(w * x).sum(), (w * x * x).sum()]])
        try:
            b = b - np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
    return float(b[1])


print("\n" + "=" * 94)
print("PAIRED A/B on 2025 — A rho=%.3f (frozen)  vs  B rho=%.3f (measured)" % (RHO_A, RHO_B))
print("=" * 94)
print("   %-8s %8s %10s %10s %10s %9s %9s" % ("market", "n", "LL A", "LL B", "delta",
                                              "slope A", "slope B"))
ta = tb = 0.0
for k in MK:
    a, b, y = acc["A"][k], acc["B"][k], Y[k]
    la, lb = ll(a, y), ll(b, y)
    ta += la
    tb += lb
    sa, sb = slope(a, y), slope(b, y)
    print("   %-8s %8d %10.5f %10.5f %+10.5f %9.3f %9.3f  %s  %s"
          % (k, len(y), la, lb, lb - la, sa, sb,
             "B BETTER" if lb < la else "A better",
             "slope->1" if abs(sb - 1) < abs(sa - 1) else ""))
print("\n   summed log-loss  A %.5f  B %.5f  delta %+.5f  -> %s"
      % (ta, tb, tb - ta, "RHO=0.085 HELPS" if tb < ta else "RHO=0.085 HURTS"))
print("   base rates: " + "  ".join("%s %.3f" % (k, float(np.mean(Y[k]))) for k in MK))
