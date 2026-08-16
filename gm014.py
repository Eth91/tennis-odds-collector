#!/usr/bin/env python3
"""GM-014 — is the MEASURED rho usable once SPREAD is re-tuned with it? Best-of-each, not one-at-a-time.

GM-010 substituted rho 0.050 -> 0.085 and every placement calibration slope moved further above
1.0. The measurement behind 0.085 is not in doubt (cleanest sample, replicated per year, placebo
p=0.000, two functional forms, five of six round pairs). The explanation is coupling: SPREAD=1.30
was tuned on 2025 WITH rho pinned at 0.050, and the two push on the same quantity from opposite
ends -- rho widens each player's own 72-hole distribution (compressing relative differences),
SPREAD widens the differences between players. Changing one alone breaks a pair that was fitted
together, and that is a statement about the fit, not about the golf.

So the honest question is not "is 0.085 better than 0.050" but "is the BEST model at rho=0.085
better than the BEST model at rho=0.050".

    TUNE   on 2024 only, a SPREAD grid at each rho, scored by summed log-loss over the five markets
    TEST   the winner from each rho, head to head, on 2025
Tuning on 2025 and testing on 2025 would be circular, which is why the tune year is 2024 and the
comparison year is untouched by it. 2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.

Lean by design: NSIM=4000 and a three-point SPREAD grid. The quantity being compared is a
difference between configurations under common random numbers, not an absolute probability, so
Monte-Carlo noise largely cancels -- and the determinism floor is asserted before anything is read.
"""
import hashlib
import pickle
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU
import pga_sim as PS

EPS = 1e-9
NSIM = 4000
SEED = 31337
GRID = (1.15, 1.30, 1.45)
RHOS = (0.050, 0.085)
MK = ("cut", "top20", "top10", "top5", "win")

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
                   "WHERE date >= '2024-01-01' AND date < '2026-01-01'").fetchall()
con.close()
ev = defaultdict(lambda: defaultdict(dict))
em = {}
for eid, evn, d, pl, rnd, sc in rows:
    if sc is None:
        continue
    ev[eid][int(rnd)][pl] = float(sc)
    em[eid] = (str(evn), str(d))
Y24 = sorted([e for e in ev if em[e][1][:4] == "2024"])
Y25 = sorted([e for e in ev if em[e][1][:4] == "2025"])
print("events: 2024 %d | 2025 %d" % (len(Y24), len(Y25)), flush=True)

probe = Y24[0]
R = rf(em[probe][1])
fp = [p for p in ev[probe].get(1, {}) if PS.lookup(R, p) is not None]
nm, mu, sg, _u, _c, _d = PS.field_ratings(fp, R, spread=1.30)
P0 = {n: (float(a), float(b)) for n, a, b in zip(nm, mu, sg)}
r1 = PS.simulate(P0, n=2000, seed=SEED, cut_n=65, rho=0.05)
r2 = PS.simulate(P0, n=2000, seed=SEED, cut_n=65, rho=0.05)
dmax = max(abs(r1.win[p] - r2.win[p]) for p in r1.players)
print("DETERMINISM: %.10f -> %s" % (dmax, "EXACT" if dmax == 0.0 else "BROKEN"), flush=True)
if dmax != 0.0:
    raise SystemExit("refusing without an exact CRN floor")


def ll(p, y):
    p = np.clip(np.asarray(p), EPS, 1 - EPS)
    y = np.asarray(y)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def score(events, rho, spread):
    acc = {k: [] for k in MK}
    Y = {k: [] for k in MK}
    for eid in events:
        byr = ev[eid]
        if 1 not in byr:
            continue
        R = rf(em[eid][1])
        if not R:
            continue
        fp = [p for p in byr[1] if PS.lookup(R, p) is not None]
        if len(fp) < 40:
            continue
        names, mu, sg, _u, _c, _d = PS.field_ratings(fp, R, spread=spread)
        if len(names) < 40:
            continue
        cut_n = RU.cut_rule(em[eid][0], em[eid][1], n_field=len(byr[1]))
        tot = {}
        for p in names:
            sc = [byr[r].get(p) for r in (1, 2, 3, 4) if r in byr]
            tot[p] = (sum(x for x in sc if x is not None),
                      sum(1 for x in sc if x is not None))
        p4 = {p: v[0] for p, v in tot.items() if v[1] == 4}
        if len(p4) < 20:
            continue
        made = {p for p, v in tot.items() if v[1] >= 3}
        pos = {p: 1 + sum(1 for q in p4 if p4[q] < p4[p]) for p in p4}
        P = {n: (float(a), float(b)) for n, a, b in zip(names, mu, sg)}
        r = PS.simulate(P, n=NSIM, seed=SEED, cut_n=cut_n, rho=rho)
        started = set(byr[1])
        for p in names:
            if p not in started:
                continue
            yv = dict(cut=1.0 if p in made else 0.0,
                      top20=1.0 if pos.get(p, 999) <= 20 else 0.0,
                      top10=1.0 if pos.get(p, 999) <= 10 else 0.0,
                      top5=1.0 if pos.get(p, 999) <= 5 else 0.0,
                      win=1.0 if pos.get(p, 999) == 1 else 0.0)
            for k in MK:
                Y[k].append(yv[k])
                f = (r.make_cut if k == "cut" else r.win_ties if k == "win"
                     else r.top(int(k[3:]), ties=True))
                acc[k].append(float(f.get(p, 0.0)))
    return sum(ll(acc[k], Y[k]) for k in MK), len(Y["cut"])


print("\n" + "=" * 78)
print("TUNE SPREAD on 2024, separately at each rho")
print("=" * 78, flush=True)
best = {}
for rho in RHOS:
    print("   rho = %.3f" % rho, flush=True)
    for sp in GRID:
        v, n = score(Y24, rho, sp)
        star = ""
        if rho not in best or v < best[rho][1]:
            best[rho] = (sp, v)
            star = "  <-"
        print("      SPREAD %.2f   summed LL %.5f   (n=%d)%s" % (sp, v, n, star), flush=True)
print("\n   best on 2024:  " + " | ".join("rho %.3f -> SPREAD %.2f (LL %.5f)"
                                          % (r, best[r][0], best[r][1]) for r in RHOS))

print("\n" + "=" * 78)
print("HEAD TO HEAD on 2025 — best config at each rho")
print("=" * 78, flush=True)
res = {}
for rho in RHOS:
    sp = best[rho][0]
    v, n = score(Y25, rho, sp)
    res[rho] = v
    print("   rho %.3f  SPREAD %.2f   summed LL %.5f   (n=%d)" % (rho, sp, v, n), flush=True)
a, b = res[0.050], res[0.085]
print("\n   delta (0.085 best - 0.050 best) = %+.5f  ->  %s" % (b - a,
      "MEASURED RHO IS USABLE once SPREAD is re-tuned" if b < a
      else "measured rho is NOT usable even with SPREAD re-tuned"))
print("   frozen production is rho=0.050 / SPREAD=1.30; the 0.050 arm here re-tunes SPREAD on")
print("   2024, so it is not identical to production either. This compares BEST to BEST.")
