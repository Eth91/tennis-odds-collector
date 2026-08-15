#!/usr/bin/env python3
"""GM-006 — does the dispersion multiplier improve PROBABILITIES? Paired A/B, research model only.

GM-004/005 established that a tournament's residual dispersion is predictable from its own prior
editions: persistence +0.692 raw and +0.611 after removing field-knowledge, OOS MSE on 2025 cut
45-50% against the global constant the model actually uses, placebo 0/400.

That is an INTERMEDIATE metric. Charter rule: ranking quality and probability quality are
different things, and dispersion MSE is neither. The model sells make-cut, top-N and win
probabilities, so the question is whether widening the right tournaments and narrowing the wrong
ones makes those probabilities better. A distribution can be more accurate in width and still
price worse if the width was compensating for something else.

DESIGN — paired, common random numbers.
    A  baseline     every player's sigma as the ratings give it            (what the model does)
    B  multiplied   sigma x (predicted dispersion / global mean)           (the research change)
Same field, same seed, same cut rule; the ONLY difference is the sigma scale. Both arms run in
pga_sim, so pga_ruler is never touched and production stays frozen.

The multiplier for a 2025 event uses that event's 2023-24 editions ONLY. Events with no prior
edition get 1.0 and are reported separately -- they are the honest "no information" case and
must not be quietly dropped, since dropping them would select for well-established tournaments.

⚠️ DETERMINISM FIRST. A paired A/B is worthless if the two arms differ by simulation noise rather
than by the change. Two IDENTICAL runs are compared before anything else and must agree EXACTLY;
a "small" difference is a broken pairing, and a broken pairing biases every verdict toward zero.

2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import hashlib
import math
import pickle
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU
import pga_sim as PS

EPS = 1e-9
NSIM = 20000
SEED = 909

KEY = hashlib.sha1(("%s|%s|%s|%s" % (RU.HALF_LIFE_D, RU.K_SHRINK, RU.SIG_SHRINK,
                                     RU.MIN_ROUNDS)).encode()).hexdigest()[:12]
fits = pickle.load(open("ratings_cache_%s.pkl" % KEY, "rb"))
fit_dates = sorted(fits)


def ratings_for(date):
    lo, hi = 0, len(fit_dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if fit_dates[mid] < date:
            lo = mid + 1
        else:
            hi = mid
    return fits[fit_dates[lo - 1]] if lo > 0 else None


con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
rows = con.execute("SELECT event_id, event, date, player, rnd, score FROM rounds "
                   "WHERE date < '2026-01-01' ORDER BY date").fetchall()
con.close()
ev = defaultdict(lambda: defaultdict(dict))
emeta = {}
for eid, evn, d, pl, rnd, sc in rows:
    if sc is None:
        continue
    ev[eid][int(rnd)][pl] = float(sc)
    emeta[eid] = (str(evn), str(d))


def ekey(n):
    return " ".join(sorted(w for w in str(n).lower().split() if len(w) > 3))


# ── dispersion per event, and the as-of multiplier ─────────────────────────────────────────────
disp, yr_of, name_of = {}, {}, {}
for eid, byr in ev.items():
    R = ratings_for(emeta[eid][1])
    if not R:
        continue
    res = []
    for rnd, sc in byr.items():
        if len(sc) < 40:
            continue
        m = float(np.mean(list(sc.values())))
        for pl, s in sc.items():
            r = R.get(RU.norm(pl)) or R.get(pl)
            if r is not None:
                res.append((s - m) - float(r[0]))
    if len(res) >= 120:
        disp[eid] = float(np.std(res, ddof=1))
        yr_of[eid] = int(emeta[eid][1][:4])
        name_of[eid] = ekey(emeta[eid][0])

hist = defaultdict(list)
for eid, v in disp.items():
    if yr_of[eid] <= 2024:
        hist[name_of[eid]].append(v)
GLOB = float(np.mean([v for eid, v in disp.items() if yr_of[eid] <= 2024]))
print("global dispersion (<=2024) = %.4f over %d events" % (GLOB, sum(1 for e in disp
                                                                     if yr_of[e] <= 2024)))

test = [e for e in disp if yr_of[e] == 2025]
withhist = [e for e in test if name_of[e] in hist]
print("2025 events: %d, of which %d have a 2023-24 edition\n" % (len(test), len(withhist)))


def mult_for(eid):
    h = hist.get(name_of[eid])
    return (float(np.mean(h)) / GLOB) if h else 1.0


# ── determinism floor ──────────────────────────────────────────────────────────────────────────
probe = withhist[0]
R = ratings_for(emeta[probe][1])
fp = [p for p in ev[probe].get(1, {}) if PS.lookup(R, p) is not None]
names, mu, sg, _u, _c, _d = PS.field_ratings(fp, R, spread=1.30)
pl_a = {n: (float(m), float(s)) for n, m, s in zip(names, mu, sg)}
r1 = PS.simulate(pl_a, n=4000, seed=SEED, cut_n=65)
r2 = PS.simulate(pl_a, n=4000, seed=SEED, cut_n=65)
dmax = max(abs(r1.win[p] - r2.win[p]) for p in r1.players)
print("DETERMINISM: two identical runs differ by max %.10f on win  ->  %s"
      % (dmax, "EXACT, pairing is valid" if dmax == 0.0 else "BROKEN PAIRING, verdicts biased"))
if dmax != 0.0:
    raise SystemExit("refusing to run a paired A/B without an exact CRN floor")

# ── run both arms ──────────────────────────────────────────────────────────────────────────────
MK = ("cut", "top20", "top10", "top5", "win")
acc = {a: {k: [] for k in MK} for a in ("A", "B")}
Y = {k: [] for k in MK}
info = []
for i, eid in enumerate(sorted(test), 1):
    byr = ev[eid]
    if 1 not in byr:
        continue
    R = ratings_for(emeta[eid][1])
    if not R:
        continue
    fp = [p for p in byr[1] if PS.lookup(R, p) is not None]
    if len(fp) < 40:
        continue
    names, mu, sg, _u, _c, _dp = PS.field_ratings(fp, R, spread=1.30)
    if len(names) < 40:
        continue
    cut_n = RU.cut_rule(emeta[eid][0], emeta[eid][1], n_field=len(byr[1]))
    m = mult_for(eid)
    tot = {}
    for p in names:
        s = [byr[r].get(p) for r in (1, 2, 3, 4) if r in byr]
        if s and s[0] is not None:
            tot[p] = sum(x for x in s if x is not None), sum(1 for x in s if x is not None)
    played4 = {p: v[0] for p, v in tot.items() if v[1] == 4}
    if len(played4) < 20:
        continue
    made = set(p for p, v in tot.items() if v[1] >= 3)
    order = sorted(played4, key=lambda p: played4[p])
    pos = {}
    for p in order:
        pos[p] = 1 + sum(1 for q in order if played4[q] < played4[p])
    A = {n: (float(a), float(b)) for n, a, b in zip(names, mu, sg)}
    B = {n: (float(a), float(b) * m) for n, a, b in zip(names, mu, sg)}
    ra = PS.simulate(A, n=NSIM, seed=SEED, cut_n=cut_n)
    rb = PS.simulate(B, n=NSIM, seed=SEED, cut_n=cut_n)
    for p in names:
        if p not in pos and p not in made:
            continue
        y = dict(cut=1.0 if p in made else 0.0,
                 top20=1.0 if pos.get(p, 999) <= 20 else 0.0,
                 top10=1.0 if pos.get(p, 999) <= 10 else 0.0,
                 top5=1.0 if pos.get(p, 999) <= 5 else 0.0,
                 win=1.0 if pos.get(p, 999) == 1 else 0.0)
        for k in MK:
            Y[k].append(y[k])
            fa = (ra.make_cut if k == "cut" else ra.win if k == "win"
                  else ra.top(int(k[3:]), ties=False))
            fb = (rb.make_cut if k == "cut" else rb.win if k == "win"
                  else rb.top(int(k[3:]), ties=False))
            acc["A"][k].append(float(fa.get(p, 0.0)))
            acc["B"][k].append(float(fb.get(p, 0.0)))
    info.append((emeta[eid][0], m, len(names)))
    if i % 20 == 0:
        print("   %d/%d events" % (i, len(test)), flush=True)

print("\nevents simulated: %d" % len(info))
ms = np.array([x[1] for x in info])
print("multipliers: mean %.3f  sd %.3f  min %.3f  max %.3f  |  %d events at exactly 1.0 (no prior)"
      % (ms.mean(), ms.std(), ms.min(), ms.max(), int((ms == 1.0).sum())))


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
        z = b[0] + b[1] * x
        q = 1 / (1 + np.exp(-z))
        g = np.array([(q - y).sum(), ((q - y) * x).sum()])
        w = q * (1 - q) + 1e-9
        H = np.array([[w.sum(), (w * x).sum()], [(w * x).sum(), (w * x * x).sum()]])
        try:
            b = b - np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
    return float(b[1])


print("\n" + "=" * 92)
print("PAIRED A/B on 2025 — A = one sigma (frozen model), B = sigma x predicted dispersion")
print("=" * 92)
print("   %-8s %8s %10s %10s %9s %9s %9s" % ("market", "n", "LL A", "LL B", "delta",
                                             "slope A", "slope B"))
tot_a = tot_b = 0.0
for k in MK:
    a, b, y = acc["A"][k], acc["B"][k], Y[k]
    la, lb = ll(a, y), ll(b, y)
    tot_a += la
    tot_b += lb
    print("   %-8s %8d %10.5f %10.5f %+9.5f %9.3f %9.3f  %s"
          % (k, len(y), la, lb, lb - la, slope(a, y), slope(b, y),
             "B BETTER" if lb < la else "A better"))
print("\n   summed log-loss  A %.5f  B %.5f  delta %+.5f  -> %s"
      % (tot_a, tot_b, tot_b - tot_a, "MULTIPLIER HELPS" if tot_b < tot_a else "MULTIPLIER HURTS"))
print("   (calibration slope: 1.0 is perfect; <1 means over-confident, >1 under-confident)")
