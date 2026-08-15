#!/usr/bin/env python3
"""GM-007 — the in-play advantage: how much of it is INFORMATION, and how much is arithmetic?

Established earlier that in-play forecasting scores far better than pre-tournament. That is used
as evidence the in-play path is doing something clever. Most of it may be neither clever nor
information: a model that already knows three of four rounds has three quarters less variance left
to be wrong about. Sharpening that comes from having fewer rounds remaining is ARITHMETIC and
cannot be ported back to a pre-tournament forecast, however impressive the log-loss looks.

The part that COULD port back is form: if a player's rounds so far predict their remaining rounds
beyond their rating, the model is carrying week-to-week information it currently prices at
RHO = 0.05 -- and RHO is the single constant that governs how much a completed round should move
the rest of the week.

    LEG 1  within-event persistence: corr(residual so far, residual remaining), per stage.
           R1 -> R2 is the clean one: EVERY player in the field plays both, so there is no
           selection at all. Later stages are computed on NO-CUT events only, because among
           cut-makers R1-R2 is truncated by the very cut that selected them, which drags the
           correlation in a direction that has nothing to do with form.
    LEG 2  compare that to RHO = 0.05. RHO is the model's answer to this exact question, measured
           three ways in [0.034, 0.109]. If the in-event correlation is much larger, the model
           under-updates during a tournament and there is a real mechanism to add. If it matches,
           the in-play path is already correct and the "advantage" is arithmetic.
    LEG 3  quantify the arithmetic directly: how much does remaining-round variance fall by stage?
           If 72-hole variance is 4 sigma^2 and only 1 remains, sd falls by half before any
           information is used at all.

⚠️ THE HOT HAND IS THE OBVIOUS TRAP HERE. A positive raw correlation between a player's early and
late rounds is guaranteed by TALENT: good players score below the field mean in both halves. That
is why everything is measured on RESIDUALS to the as-of rating -- the correlation being tested is
what remains AFTER ability is removed. A placebo pairing each player's first half with a DIFFERENT
player's second half in the same event is run to confirm the residual really is ability-free.

2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import hashlib
import math
import pickle
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

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

# residual per (event, rnd, player)
res = defaultdict(dict)
for eid, byr in ev.items():
    R = ratings_for(emeta[eid][1])
    if not R:
        continue
    for rnd, sc in byr.items():
        if len(sc) < 40:
            continue
        m = float(np.mean(list(sc.values())))
        for pl, s in sc.items():
            r = R.get(RU.norm(pl)) or R.get(pl)
            if r is not None:
                res[(eid, rnd)][pl] = (s - m) - float(r[0])
print("event-rounds with residuals: %d" % len(res))

nocut = {eid for eid, byr in ev.items()
         if 4 in byr and 1 in byr and len(byr[4]) >= 0.9 * len(byr[1]) and len(byr[1]) >= 40}
print("no-cut events: %d" % len(nocut))


def pers(stage_a, stage_b, only=None, label=""):
    """corr(mean residual over rounds stage_a, mean residual over stage_b), same player-event."""
    X, Y, G = [], [], []
    for eid in ev:
        if only and eid not in only:
            continue
        ra = [r for r in stage_a if (eid, r) in res]
        rb = [r for r in stage_b if (eid, r) in res]
        if len(ra) != len(stage_a) or len(rb) != len(stage_b):
            continue
        common = set(res[(eid, ra[0])])
        for r in ra + rb:
            common &= set(res[(eid, r)])
        if len(common) < 40:
            continue
        for p in common:
            X.append(float(np.mean([res[(eid, r)][p] for r in ra])))
            Y.append(float(np.mean([res[(eid, r)][p] for r in rb])))
            G.append(eid)
    if len(X) < 300:
        print("   %-46s too few (%d)" % (label, len(X)))
        return None
    X = np.array(X); Y = np.array(Y)
    r = float(np.corrcoef(X, Y)[0, 1])
    # event-clustered SE on the correlation, via per-event correlations
    byev = defaultdict(list)
    for x, y, g in zip(X, Y, G):
        byev[g].append((x, y))
    rs = []
    for g, v in byev.items():
        if len(v) >= 30:
            a = np.array([t[0] for t in v]); b = np.array([t[1] for t in v])
            if a.std() > 1e-9 and b.std() > 1e-9:
                rs.append(float(np.corrcoef(a, b)[0, 1]))
    se = (np.std(rs, ddof=1) / math.sqrt(len(rs))) if len(rs) > 2 else float("nan")
    print("   %-46s corr %+.4f  (n=%d rounds-pairs, %d events, clustered SE %.4f, t=%+.2f)"
          % (label, r, len(X), len(byev), se, r / se if se == se and se > 0 else float("nan")))
    return r, X, Y, G


print("\n" + "=" * 96)
print("LEG 1 — does a player's form SO FAR predict their REMAINING rounds, beyond the rating?")
print("=" * 96)
print("   the model's answer to this question is RHO = 0.05\n")
a = pers([1], [2], label="R1 -> R2   FULL FIELD (no selection anywhere)")
pers([1], [2], only=nocut, label="R1 -> R2   no-cut events only")
pers([1, 2], [3, 4], only=nocut, label="R1R2 -> R3R4   no-cut events only")
pers([3], [4], only=nocut, label="R3 -> R4   no-cut events only")
pers([1, 2, 3], [4], only=nocut, label="R1R2R3 -> R4   no-cut events only")

print("\n" + "=" * 96)
print("PLACEBO — pair each player's first half with ANOTHER player's second half, same event")
print("=" * 96)
if a:
    _r, X, Y, G = a
    rng = np.random.default_rng(3)
    byev = defaultdict(list)
    for i, g in enumerate(G):
        byev[g].append(i)
    null = []
    for _ in range(200):
        Yp = np.array(Y, copy=True)
        for g, idx in byev.items():
            perm = list(idx)
            rng.shuffle(perm)
            Yp[idx] = Y[perm]
        null.append(float(np.corrcoef(X, Yp)[0, 1]))
    null = np.array(null)
    print("   real corr %+.4f | placebo mean %+.4f sd %.4f | |placebo| >= real in %d/200 (p=%.3f)"
          % (a[0], null.mean(), null.std(), int((np.abs(null) >= abs(a[0])).sum()),
             (np.abs(null) >= abs(a[0])).sum() / 200))

print("\n" + "=" * 96)
print("LEG 2 — is the model's RHO right for in-play updating?")
print("=" * 96)
print("   RHO in the frozen model            = %.3f" % RU.RHO)
if a:
    print("   measured within-event R1->R2 corr  = %+.4f" % a[0])
    d = a[0] - RU.RHO
    print("   difference                         = %+.4f -> %s"
          % (d, "model UNDER-updates in play, a real mechanism to add" if d > 0.05
             else "model OVER-updates" if d < -0.05
             else "MATCHES: the in-play path already prices this correctly"))

print("\n" + "=" * 96)
print("LEG 3 — how much in-play sharpening is pure ARITHMETIC, before any information?")
print("=" * 96)
sig = 2.82
for done in (0, 1, 2, 3):
    left = 4 - done
    sd = sig * math.sqrt(left)
    print("   after R%d: %d rounds remain, sd of the remaining total = %.2f strokes  (%.0f%% of "
          "the pre-tournament %.2f)" % (done, left, sd, 100 * sd / (sig * 2.0), sig * 2.0))
print("\n   A forecast made after R3 has HALF the remaining uncertainty of a pre-tournament one")
print("   before it learns anything at all. Any comparison of in-play to pre-tournament skill")
print("   that does not hold rounds-remaining fixed is measuring this, not the model.")
