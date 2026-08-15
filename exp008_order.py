#!/usr/bin/env python3
"""EXP-008 — the rank-offset x shape-stretch INTERACTION, flagged unmeasured when it shipped.

RANK_OFFSETS were fitted on UNSTRETCHED probabilities (shape_sims.npz has SHAPE_SLOPE=1.0) but
are applied UPSTREAM of _recal_shape in the live path. So the stretch acts on numbers the offsets
already moved, and for majors a 1.30 stretch compounds an offset fitted without it. Nobody has
measured that; it shipped on the fitted holdout gain alone.

Three arms, identical cached ratings, identical seed per event, 2026 held out:

  A  offsets THEN stretch   (what ships)
  B  stretch THEN offsets   (offsets applied to the numbers they were NOT fitted on)
  C  no offsets             (v1.5 baseline for this axis)

⚠️ 2026 IS ALREADY BURNT FOR THE OFFSETS THEMSELVES — they were fitted on 2023-25 and validated on
2026, so this is not an independent test of whether offsets help. It IS an independent test of
ORDER, which no fit has ever touched. Labelled accordingly rather than called a clean holdout.

If A ~= B the ordering is irrelevant and the concern is closed. If B > A the live order is wrong.
If both beat C, the offsets survive; if not, they were fitting the harness.
"""
import datetime as dt
import hashlib
import pickle
import sys
import time

import numpy as np

import pga_ruler as RU
import pga_sim_validate as V

SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
SEED = 53
MK = [("win", 1, False), ("top5", 5, False), ("top10", 10, False), ("top20", 20, False),
      ("top5_ties", 5, True), ("top10_ties", 10, True), ("top20_ties", 20, True)]
PLACE = ("top5", "top10", "top20", "top5_ties", "top10_ties", "top20_ties")
ALL = ("win", "top5", "top10", "top20", "win_ties", "top5_ties", "top10_ties", "top20_ties")
EPS = 1e-9

KEY = hashlib.sha1(("%s|%s|%s|%s" % (RU.HALF_LIFE_D, RU.K_SHRINK, RU.SIG_SHRINK,
                                     RU.MIN_ROUNDS)).encode()).hexdigest()[:12]
fits = pickle.load(open("ratings_cache_%s.pkl" % KEY, "rb"))
print("cached fits: %d" % len(fits), flush=True)

events = V.load_events()
first = min(e["date"] for e in events)
burn = (dt.date.fromisoformat(str(first)[:10]) + dt.timedelta(days=270)).isoformat()
usable = [e for e in events if e["date"] >= burn and e["struct"] in ("cut_R2", "no_cut")]

P = {"A": [], "B": [], "C": []}
Y, D = [], []
t0 = time.time()
for i, ev in enumerate(usable, 1):
    R = fits.get(ev["date"])
    if R is None:
        continue
    cut_n = RU.cut_rule(ev["name"], ev["date"], n_field=len(ev["field"]))
    shp = RU.shape_slopes(ev["name"])
    # ONE raw sim, then the three post-processings applied to copies of it. Same draws, so the
    # comparison is exactly paired and carries no Monte-Carlo noise at all.
    old_sl, old_rk = RU.SHAPE_SLOPE, RU.RANK_OFFSETS
    raw = RU.simulate(R, ev["field"], n_sims=SIMS, seed=SEED, cut_n=cut_n,
                      shape_slope=1.0)                     # unstretched, un-offset baseline
    if not raw:
        continue
    import copy
    a = copy.deepcopy(raw)
    RU._recal_rank(a, PLACE)
    RU._recal_shape(a, ALL, slope=shp)
    b = copy.deepcopy(raw)
    RU._recal_shape(b, ALL, slope=shp)
    RU._recal_rank(b, PLACE)
    c = copy.deepcopy(raw)
    RU._recal_shape(c, ALL, slope=shp)

    pos, grp, _f = V.realised(ev)
    made = set(ev.get("made_cut") or [])
    ss = set(raw)
    for nm in raw:
        P["A"].append([(a[nm] or {}).get(k) or 0.0 for k, _N, _t in MK])
        P["B"].append([(b[nm] or {}).get(k) or 0.0 for k, _N, _t in MK])
        P["C"].append([(c[nm] or {}).get(k) or 0.0 for k, _N, _t in MK])
        Y.append([V.y_for(k, N, t, nm, pos, grp, made, ss) or 0.0 for k, N, t in MK])
        D.append(int(str(ev["date"])[:4]))
    if i % 60 == 0:
        print("   %d/%d (%.1f min)" % (i, len(usable), (time.time() - t0) / 60), flush=True)

for k in P:
    P[k] = np.array(P[k])
Y = np.array(Y); D = np.array(D)
print("\n%d rows, three arms off the SAME draws\n" % len(Y), flush=True)


def ll(p, y):
    q = np.clip(p, EPS, 1 - EPS)
    return float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())


for sel, lbl in ((D < 2026, "TRAIN 2023-25"), (D >= 2026, "2026 (offsets already fitted here)")):
    print("=" * 84)
    print("%s (n=%d)" % (lbl, sel.sum()))
    print("=" * 84)
    print("   %-12s %11s %11s %11s   %s" % ("market", "A off->str", "B str->off", "C no off",
                                            "best"))
    for mi, (k, _N, _t) in enumerate(MK):
        la = ll(P["A"][sel, mi], Y[sel, mi])
        lb = ll(P["B"][sel, mi], Y[sel, mi])
        lc = ll(P["C"][sel, mi], Y[sel, mi])
        best = min(("A", la), ("B", lb), ("C", lc), key=lambda x: x[1])[0]
        print("   %-12s %11.5f %11.5f %11.5f   %s" % (k, la, lb, lc, best))
    da = sum(ll(P["A"][sel, mi], Y[sel, mi]) for mi in range(len(MK)))
    db = sum(ll(P["B"][sel, mi], Y[sel, mi]) for mi in range(len(MK)))
    dc = sum(ll(P["C"][sel, mi], Y[sel, mi]) for mi in range(len(MK)))
    print("   summed LL:  A %.5f   B %.5f   C %.5f   | B-A %+.6f   A-C %+.6f"
          % (da, db, dc, db - da, da - dc))
    print()
