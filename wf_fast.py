#!/usr/bin/env python3
"""End-to-end accuracy of the CURRENT pga_ruler, with a persistent fit cache.

~85% of a walk-forward is RU.fit recomputing every player's rating from scratch per event. But a
fit depends ONLY on (asof date, the rating constants) — not on anything downstream — so it is
cacheable across runs, and across arms that share those constants.

  pass 1  compute the 218 fits, 2 workers, write ratings_cache_<hash>.pkl
  pass 2  simulate + score (cheap)

Any later run with the same rating constants skips pass 1 entirely. The cache key HASHES the
constants, so changing HALF_LIFE_D/K_SHRINK/SIG_SHRINK/MIN_ROUNDS produces a different file — a
stale cache silently answering for the wrong model is exactly the failure this is meant to avoid.

Measures: Brier, Brier skill, log-loss and calibration slope per market, train vs 2026 holdout,
on the model as it stands after today's changes (cut rule, SHAPE_SLOPE regime split, RANK_OFFSETS,
IN_PLAY_SHAPE_SLOPE).
"""
import datetime as dt
import hashlib
import os
import pickle
import sys
import time
from multiprocessing import Pool

import numpy as np

import pga_ruler as RU
import pga_sim_validate as V

SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
SEED = 31
MK = [("win", 1, False), ("top5", 5, False), ("top10", 10, False), ("top20", 20, False),
      ("win_ties", 1, True), ("top5_ties", 5, True), ("top10_ties", 10, True),
      ("top20_ties", 20, True)]
EPS = 1e-9

KEY = hashlib.sha1(("%s|%s|%s|%s" % (RU.HALF_LIFE_D, RU.K_SHRINK, RU.SIG_SHRINK,
                                     RU.MIN_ROUNDS)).encode()).hexdigest()[:12]
CACHE = "ratings_cache_%s.pkl" % KEY
print("rating constants: half_life=%s k=%s sig=%s min=%s -> cache %s"
      % (RU.HALF_LIFE_D, RU.K_SHRINK, RU.SIG_SHRINK, RU.MIN_ROUNDS, CACHE), flush=True)

events = V.load_events()
all_rows = RU.all_rows()
first = min(e["date"] for e in events)
burn = (dt.date.fromisoformat(str(first)[:10]) + dt.timedelta(days=270)).isoformat()
usable = [e for e in events if e["date"] >= burn and e["struct"] in ("cut_R2", "no_cut")]
dates = sorted({e["date"] for e in usable})
print("events %d, distinct asof dates %d" % (len(usable), len(dates)), flush=True)


def _fit_one(d0):
    R_raw, _ = RU.fit(asof=d0, rows=[r for r in all_rows if r[1] < d0])
    return d0, {RU.norm(k): v for k, v in R_raw.items()}


if os.path.exists(CACHE):
    fits = pickle.load(open(CACHE, "rb"))
    print("loaded %d cached fits" % len(fits), flush=True)
else:
    t0 = time.time()
    with Pool(2) as pool:
        fits = {}
        for i, (d0, R) in enumerate(pool.imap_unordered(_fit_one, dates, chunksize=2), 1):
            fits[d0] = R
            if i % 20 == 0:
                print("   fit %d/%d (%.1f min)" % (i, len(dates), (time.time() - t0) / 60),
                      flush=True)
    pickle.dump(fits, open(CACHE, "wb"), protocol=4)
    print("fits done in %.1f min -> %s (%.0f MB)"
          % ((time.time() - t0) / 60, CACHE, os.path.getsize(CACHE) / 1e6), flush=True)

t1 = time.time()
P, Y, D = [], [], []
for i, ev in enumerate(usable, 1):
    out = RU.simulate(fits[ev["date"]], ev["field"], n_sims=SIMS, seed=SEED,
                      cut_n=RU.cut_rule(ev["name"], ev["date"], n_field=len(ev["field"])),
                      shape_slope=RU.shape_slopes(ev["name"]))
    if not out:
        continue
    pos, grp, _f = V.realised(ev)
    made = set(ev.get("made_cut") or [])
    ss = set(out)
    for nm in out:
        P.append([(out[nm] or {}).get(k) or 0.0 for k, _N, _t in MK])
        Y.append([V.y_for(k, N, t, nm, pos, grp, made, ss) or 0.0 for k, N, t in MK])
        D.append(int(str(ev["date"])[:4]))
    if i % 50 == 0:
        print("   sim %d/%d (%.1f min)" % (i, len(usable), (time.time() - t1) / 60), flush=True)
P = np.array(P, np.float64); Y = np.array(Y, np.float64); D = np.array(D)
print("sims done in %.1f min, %d rows\n" % ((time.time() - t1) / 60, len(P)), flush=True)


def slope(p, y):
    x = np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))
    b, a = 1.0, 0.0
    for _ in range(60):                       # Newton on the logistic
        z = 1 / (1 + np.exp(-(a + b * x)))
        g = np.array([(y - z).sum(), ((y - z) * x).sum()])
        w = z * (1 - z)
        H = np.array([[w.sum(), (w * x).sum()], [(w * x).sum(), (w * x * x).sum()]])
        try:
            s = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        a, b = a + s[0], b + s[1]
        if abs(s).max() < 1e-10:
            break
    return b


for sel, lbl in ((D < 2026, "TRAIN 2023-25"), (D >= 2026, "2026 HOLDOUT")):
    print("=" * 74)
    print("%s — CURRENT MODEL (n=%d rows)" % (lbl, sel.sum()))
    print("=" * 74)
    print("   %-12s %8s %10s %11s %9s %9s" % ("market", "base", "Brier", "BrierSkill",
                                              "LogLoss", "slope"))
    for mi, (k, _N, _t) in enumerate(MK):
        p, y = P[sel, mi], Y[sel, mi]
        base = y.mean()
        br = ((p - y) ** 2).mean()
        bb = ((base - y) ** 2).mean()
        q = np.clip(p, EPS, 1 - EPS)
        ll = -(y * np.log(q) + (1 - y) * np.log(1 - q)).mean()
        print("   %-12s %8.4f %10.5f %11.4f %9.5f %9.3f"
              % (k, base, br, 1 - br / bb, ll, slope(p, y)))
    print()
