#!/usr/bin/env python3
"""GM-004 — is a tournament's SCORING DISPERSION predictable before it is played?

GM-003's real finding was not the round effect (that failed 2025) but the thing underneath it:
spread tracks how hard the day plays, corr +0.271 over 944 event-rounds. The frozen model has one
per-player sigma and applies it everywhere, so it quotes the same width at a benign resort course
and a wind-blown major. That is a DISTRIBUTION-SHAPE error, and unlike a ranking error it lands on
every probability the model sells -- make-cut, top-N, win, round scores -- while leaving ordering
metrics untouched, which is exactly why nothing has caught it.

But difficulty is only useful if it is knowable IN ADVANCE. The field mean of a round is not known
until the round is over. A course's own history is.

    target      D = sd of RESIDUALS for an event-round
                residual = (score - that round's field mean) - as-of rating
                Residuals, not raw scores: raw spread also contains FIELD HETEROGENEITY (an
                opposite-field event has more spread because the players differ more), and the
                model already knows about that through the ratings. What it does not know is the
                leftover dispersion, which is what a sigma multiplier would have to capture.
    predictor   the same event's dispersion in PRIOR YEARS ONLY
    baseline    the global mean dispersion -- i.e. exactly what the model does today

Three ways this dies, all checked:
  * dispersion is not persistent at all -> nothing to predict
  * it is persistent but a prior-year mean beats the global constant only in-sample
  * it survives both and still fails a placebo that shuffles event identity

As-of ratings come from the cached walk-forward fit whose key matches the live constants
(21951082e4c6), so no rating sees a round from its own event or later.
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
print("ratings cache %s: %d as-of dates" % (KEY, len(fits)))
fit_dates = sorted(fits)

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
print("events %d" % len(ev))


def ratings_for(date):
    """Latest cached fit STRICTLY BEFORE this event's date."""
    lo, hi = 0, len(fit_dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if fit_dates[mid] < date:
            lo = mid + 1
        else:
            hi = mid
    return fits[fit_dates[lo - 1]] if lo > 0 else None


D = {}            # (event_id, rnd) -> dispersion of residuals
nocov = 0
for eid, byr in ev.items():
    evn, d0 = emeta[eid]
    R = ratings_for(d0)
    if not R:
        nocov += 1
        continue
    for rnd, sc in byr.items():
        if len(sc) < 40:
            continue
        m = float(np.mean(list(sc.values())))
        res = []
        for pl, s in sc.items():
            r = R.get(RU.norm(pl)) or R.get(pl)
            if r is None:
                continue
            res.append((s - m) - float(r[0]))
        if len(res) >= 40:
            D[(eid, rnd)] = float(np.std(res, ddof=1))
print("event-rounds with dispersion: %d (events without a prior fit: %d)" % (len(D), nocov))
allD = np.array(list(D.values()))
print("dispersion: mean %.3f  sd %.3f  min %.3f  max %.3f  (the model assumes ONE number here)"
      % (allD.mean(), allD.std(), allD.min(), allD.max()))
print("   spread of dispersion is %.0f%% of its mean" % (100 * allD.std() / allD.mean()))

# event-level dispersion (mean over that event's rounds) and its year
edisp, eyear, ename = {}, {}, {}
tmp = defaultdict(list)
for (eid, rnd), v in D.items():
    tmp[eid].append(v)
for eid, v in tmp.items():
    edisp[eid] = float(np.mean(v))
    ename[eid] = emeta[eid][0]
    eyear[eid] = int(emeta[eid][1][:4])


def ekey(n):
    return " ".join(sorted(w for w in str(n).lower().split() if len(w) > 3))


byname = defaultdict(dict)
for eid, v in edisp.items():
    byname[ekey(ename[eid])][eyear[eid]] = v

print("\n" + "=" * 92)
print("1 — IS DISPERSION PERSISTENT year to year at the same event?")
print("=" * 92)
pairs = []
for k, yv in byname.items():
    ys = sorted(yv)
    for a, b in zip(ys, ys[1:]):
        if b - a == 1:
            pairs.append((yv[a], yv[b]))
if len(pairs) >= 20:
    x = np.array([p[0] for p in pairs]); y = np.array([p[1] for p in pairs])
    r = float(np.corrcoef(x, y)[0, 1])
    print("   corr(dispersion year Y, same event year Y+1) = %+.3f over %d consecutive pairs"
          % (r, len(pairs)))
    print("   a course with a repeatable dispersion personality would show a clear positive here")
else:
    print("   too few consecutive pairs (%d)" % len(pairs))

print("\n" + "=" * 92)
print("2 — OOS: predict 2025 event dispersion from 2023-24, vs the model's global constant")
print("=" * 92)
prior = defaultdict(list)
for k, yv in byname.items():
    for y, v in yv.items():
        if y <= 2024:
            prior[k].append(v)
glob = float(np.mean([v for k, yv in byname.items() for y, v in yv.items() if y <= 2024]))
te = [(k, yv[2025]) for k, yv in byname.items() if 2025 in yv and k in prior]
print("   2025 events with a 2023-24 history: %d | global constant %.4f" % (len(te), glob))
if len(te) >= 20:
    act = np.array([v for _k, v in te])
    pred = np.array([float(np.mean(prior[k])) for k, _v in te])
    mse_g = float(np.mean((act - glob) ** 2))
    mse_p = float(np.mean((act - pred) ** 2))
    print("   MSE vs global constant %.5f | vs prior-edition mean %.5f | %s (%.1f%%)"
          % (mse_g, mse_p, "BETTER" if mse_p < mse_g else "WORSE",
             100 * (mse_g - mse_p) / mse_g))
    print("   corr(predicted, actual) = %+.3f" % float(np.corrcoef(pred, act)[0, 1]))

    # shrunk blend, since a single prior year is noisy
    print("\n   shrunk toward the global constant:")
    best = (None, mse_g)
    for w in (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0):
        p = w * pred + (1 - w) * glob
        m = float(np.mean((act - p) ** 2))
        star = ""
        if m < best[1]:
            best = (w, m)
            star = "  <-"
        print("      w=%.1f  MSE %.5f%s" % (w, m, star))
    print("   best weight %s" % str(best[0]))

    # PLACEBO: pair each 2025 event with ANOTHER event's history
    rng = np.random.default_rng(5)
    ks = [k for k, _v in te]
    beat = 0
    for _ in range(400):
        perm = list(ks)
        rng.shuffle(perm)
        pp = np.array([float(np.mean(prior[k])) for k in perm])
        if float(np.mean((act - pp) ** 2)) <= mse_p:
            beat += 1
    print("\n   PLACEBO (histories shuffled between events): beat the real one %d/400 (p=%.3f)"
          % (beat, beat / 400))

print("\n" + "=" * 92)
print("3 — WHAT DRIVES IT? dispersion vs how hard the event played")
print("=" * 92)
hard, disp = [], []
for eid, v in edisp.items():
    sc = [s for rnd in ev[eid].values() for s in rnd.values()]
    if len(sc) >= 100:
        hard.append(float(np.mean(sc)))
        disp.append(v)
if len(hard) >= 30:
    print("   corr(event mean score, residual dispersion) = %+.3f over %d events"
          % (float(np.corrcoef(hard, disp)[0, 1]), len(hard)))
    lo = np.percentile(hard, 33); hi = np.percentile(hard, 67)
    for lab, sel in (("easiest third", [d for h, d in zip(hard, disp) if h <= lo]),
                     ("middle third ", [d for h, d in zip(hard, disp) if lo < h < hi]),
                     ("hardest third", [d for h, d in zip(hard, disp) if h >= hi])):
        print("      %s  n=%3d  dispersion %.3f" % (lab, len(sel), float(np.mean(sel))))
