#!/usr/bin/env python3
"""Matched A/B: pga_ruler BEFORE today vs AFTER. Same fits, same events, same seed, same rows.

Everything quoted so far compared numbers from different scripts, sim counts and seeds — which is
not a comparison. This loads the pre-change module from ~/pga_ruler.py.bak_precut alongside the
live one, drives BOTH from the SAME cached ratings, and scores the SAME rows.

⚠️ THE FITS MUST BE SHARED, NOT REFITTED PER ARM. Both arms use identical rating constants
(nothing today touched HALF_LIFE_D/K_SHRINK/SIG_SHRINK/MIN_ROUNDS), so one cache serves both and
any difference is attributable to the pricing changes alone: cut rule, SHAPE_SLOPE regime split,
RANK_OFFSETS. A separate refit per arm would inject MC/ordering noise into the delta.

⚠️ CRN: identical seed per event in both arms, so the comparison is paired. A broken pairing
biases the delta toward zero and would make "no change" unfalsifiable.
"""
import datetime as dt
import hashlib
import importlib.util
import os
import pickle
import sys
import time

import numpy as np

import pga_ruler as NEW
import pga_sim_validate as V

SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
SEED = 31
MK = [("win", 1, False), ("top5", 5, False), ("top10", 10, False), ("top20", 20, False),
      ("win_ties", 1, True), ("top5_ties", 5, True), ("top10_ties", 10, True),
      ("top20_ties", 20, True)]
EPS = 1e-9


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


import shutil
shutil.copy(os.path.expanduser("~/pga_ruler.py.bak_precut"), "/tmp/pga_ruler_old.py")
OLD = load("/tmp/pga_ruler_old.py", "pga_ruler_old")
print("OLD has cut_rule=%s rank=%s inplay=%s | NEW has cut_rule=%s rank=%s inplay=%s"
      % (hasattr(OLD, "cut_rule"), hasattr(OLD, "RANK_OFFSETS"),
         hasattr(OLD, "IN_PLAY_SHAPE_SLOPE"), hasattr(NEW, "cut_rule"),
         hasattr(NEW, "RANK_OFFSETS"), hasattr(NEW, "IN_PLAY_SHAPE_SLOPE")), flush=True)

KEY = hashlib.sha1(("%s|%s|%s|%s" % (NEW.HALF_LIFE_D, NEW.K_SHRINK, NEW.SIG_SHRINK,
                                     NEW.MIN_ROUNDS)).encode()).hexdigest()[:12]
fits = pickle.load(open("ratings_cache_%s.pkl" % KEY, "rb"))
print("loaded %d cached fits (shared by BOTH arms)" % len(fits), flush=True)

events = V.load_events()
first = min(e["date"] for e in events)
burn = (dt.date.fromisoformat(str(first)[:10]) + dt.timedelta(days=270)).isoformat()
usable = [e for e in events if e["date"] >= burn and e["struct"] in ("cut_R2", "no_cut")]

PO, PN, Y, D = [], [], [], []
t0 = time.time()
for i, ev in enumerate(usable, 1):
    R = fits.get(ev["date"])
    if R is None:
        continue
    # OLD: no cut_rule, no rank offsets, single global SHAPE_SLOPE — exactly as it shipped
    a = OLD.simulate(R, ev["field"], n_sims=SIMS, seed=SEED)
    b = NEW.simulate(R, ev["field"], n_sims=SIMS, seed=SEED,
                     cut_n=NEW.cut_rule(ev["name"], ev["date"], n_field=len(ev["field"])),
                     shape_slope=NEW.shape_slopes(ev["name"]))
    if not a or not b:
        continue
    pos, grp, _f = V.realised(ev)
    made = set(ev.get("made_cut") or [])
    ss = set(b)
    for nm in b:
        if nm not in a:
            continue
        PO.append([(a[nm] or {}).get(k) or 0.0 for k, _N, _t in MK])
        PN.append([(b[nm] or {}).get(k) or 0.0 for k, _N, _t in MK])
        Y.append([V.y_for(k, N, t, nm, pos, grp, made, ss) or 0.0 for k, N, t in MK])
        D.append(int(str(ev["date"])[:4]))
    if i % 50 == 0:
        print("   %d/%d (%.1f min)" % (i, len(usable), (time.time() - t0) / 60), flush=True)

PO = np.array(PO); PN = np.array(PN); Y = np.array(Y); D = np.array(D)
print("\n%d rows, both arms, identical\n" % len(Y), flush=True)


def stats(p, y):
    q = np.clip(p, EPS, 1 - EPS)
    br = ((p - y) ** 2).mean()
    bb = ((y.mean() - y) ** 2).mean()
    ll = -(y * np.log(q) + (1 - y) * np.log(1 - q)).mean()
    x = np.log(q / (1 - q))
    a, b = 0.0, 1.0
    for _ in range(60):
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
    return 1 - br / bb, ll, b


for sel, lbl in ((D < 2026, "TRAIN 2023-25"), (D >= 2026, "2026 HOLDOUT")):
    print("=" * 88)
    print("%s (n=%d) — OLD = pre-today, NEW = today's model. dLL<0 means TODAY IS BETTER."
          % (lbl, sel.sum()))
    print("=" * 88)
    print("   %-12s %9s %9s %11s %9s %9s %9s"
          % ("market", "skl OLD", "skl NEW", "dLogLoss", "slp OLD", "slp NEW", "verdict"))
    better = 0
    for mi, (k, _N, _t) in enumerate(MK):
        so, lo, bo = stats(PO[sel, mi], Y[sel, mi])
        sn, ln, bn = stats(PN[sel, mi], Y[sel, mi])
        better += (ln < lo)
        print("   %-12s %9.4f %9.4f %+11.5f %9.3f %9.3f %9s"
              % (k, so, sn, ln - lo, bo, bn, "NEW" if ln < lo else "old"))
    print("   TODAY wins %d of %d markets by log-loss" % (better, len(MK)))
    print()
