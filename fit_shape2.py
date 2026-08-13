#!/usr/bin/env python3
"""Fit SHAPE_SLOPE — v2, after v1 was OOM-killed at 200/218 with nothing saved.

THREE THINGS V1 GOT WRONG, all of which cost the whole 35-minute run:

1. IT HELD EVERYTHING AS NESTED PYTHON DICTS. 218 events x ~140 players x 8 markets of
   {player: {market: float}} is hundreds of MB in object overhead on a 956 MB box that was also
   running a backfill. The same data as float32 arrays is under 1 MB. Stored that way now.

2. IT PERSISTED NOTHING UNTIL THE END. A crash at 200/218 threw away every simulation. The sim
   pass now checkpoints to sims.npz, and a rerun with an existing checkpoint SKIPS simulating
   entirely -- so changing the grid costs seconds, not 40 minutes.

3. THE SWEEP WAS PURE-PYTHON AND ~1e9 exp() CALLS. `RU._recal_shape` bisects 200 times per
   (event, market, slope), summing over the field in Python each time. Across a 33-point grid,
   8 markets and 3 splits that is hours. Replaced with a vectorised equivalent -- and ASSERTED
   equal to the shipped operator to 1e-12 on real output, because a look-alike that silently
   differs would fit the wrong quantity and look perfectly healthy.

ESTIMAND UNCHANGED, and it is the point: the shipped 1.30 is the LOG-LOSS-OPTIMAL stretch measured
THROUGH the sum-preserving recal (`fix_tail_and_threshold.py`: "1.30 taken: top-10 optimum"), NOT
a calibration slope. Majors and non-majors are fitted separately -- 1.30 was a majors-only optimum
(9 events) installed globally over 214, which is the whole defect. 2026 is an untouched holdout.
"""
import datetime as dt
import math
import os
import sys
import time

import numpy as np

import pga_ruler as RU
import pga_sim_validate as V

SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
SEED = 7
CKPT = "shape_sims.npz"
MARKETS = [("win", 1, False), ("top5", 5, False), ("top10", 10, False), ("top20", 20, False),
           ("win_ties", 1, True), ("top5_ties", 5, True), ("top10_ties", 10, True),
           ("top20_ties", 20, True)]
COARSE = [round(1.0 + 0.05 * i, 3) for i in range(15)]          # 1.00 .. 1.70
MAJORS = ("masters", "pga championship", "u.s. open", "us open", "the open")
EPS = 1e-9


def is_major(n):
    n = " ".join(str(n or "").lower().split())
    return any(m in n for m in MAJORS)


# ── vectorised stretch, asserted identical to the shipped operator ────────────────────────────
def stretch(p, s):
    """Stretch log-odds by s, re-solving one intercept so the field SUM is preserved exactly.

    Same contract as RU._recal_shape. 60 bisection steps on [-40,40] resolves the intercept to
    ~7e-17; the shipped code uses 200, which changes nothing and costs 3x.
    """
    if abs(s - 1.0) < 1e-12 or p.size < 10:
        return p.copy()
    q = np.clip(p, EPS, 1 - EPS)
    lg = np.log(q / (1 - q))
    target = float(p.sum())
    lo, hi = -40.0, 40.0
    for _ in range(60):
        c = 0.5 * (lo + hi)
        if float((1.0 / (1.0 + np.exp(-(s * lg + c)))).sum()) > target:
            hi = c
        else:
            lo = c
    return 1.0 / (1.0 + np.exp(-(s * lg + 0.5 * (lo + hi))))


def _selftest():
    """Prove `stretch` IS the shipped operator before trusting a single fitted number."""
    rng = np.random.default_rng(3)
    p = np.sort(rng.random(120)) * 0.4 + 0.001
    for s in (1.15, 1.30, 1.55):
        out = {"p%d" % i: {"top10": float(v)} for i, v in enumerate(p)}
        RU._recal_shape(out, ("top10",), slope=s)
        ref = np.array([out["p%d" % i]["top10"] for i in range(len(p))])
        mine = stretch(p, s)
        err = float(np.max(np.abs(ref - mine)))
        assert err < 1e-12, "stretch != _recal_shape at s=%s (max err %.3e)" % (s, err)
        assert abs(float(mine.sum()) - float(p.sum())) < 1e-9, "field total not preserved"
    print("selftest: vectorised stretch == RU._recal_shape to <1e-12, total preserved", flush=True)


_selftest()

# ── simulate once, checkpointed ───────────────────────────────────────────────────────────────
if os.path.exists(CKPT):
    z = np.load(CKPT, allow_pickle=False)
    P, Y, OFF, DATE_I, MAJ = z["P"], z["Y"], z["OFF"], z["DATE"], z["MAJ"]
    print("loaded checkpoint %s: %d events, %d rows" % (CKPT, len(OFF) - 1, P.shape[0]), flush=True)
else:
    events = V.load_events()
    all_rows = RU.all_rows()
    first = min(e["date"] for e in events)
    burn = (dt.date.fromisoformat(str(first)[:10]) + dt.timedelta(days=270)).isoformat()
    usable = [e for e in events if e["date"] >= burn and e["struct"] in ("cut_R2", "no_cut")]
    print("simulating %d events, sims=%d" % (len(usable), SIMS), flush=True)
    Pl, Yl, OFF, DATE_I, MAJ = [], [], [0], [], []
    t0 = time.time()
    old = RU.SHAPE_SLOPE
    RU.SHAPE_SLOPE = 1.0                     # store UNSTRETCHED; the sweep applies the stretch
    try:
        for i, ev in enumerate(usable, 1):
            d0, eid = ev["date"], ev["eid"]
            train = V._train_rows(all_rows, d0)
            V.assert_no_leak(train, eid, d0)
            R_raw, _ = RU.fit(asof=d0, rows=train)
            out = RU.simulate({RU.norm(k): v for k, v in R_raw.items()}, ev["field"],
                              n_sims=SIMS, seed=SEED)
            if not out:
                continue
            pos, grp, _f = V.realised(ev)
            made = set(ev.get("made_cut") or [])
            simset = set(out)
            names = list(out)
            pm = np.zeros((len(names), len(MARKETS)), dtype=np.float32)
            ym = np.zeros((len(names), len(MARKETS)), dtype=np.float32)
            for a, nm in enumerate(names):
                for b, (key, N, ties) in enumerate(MARKETS):
                    pm[a, b] = (out[nm] or {}).get(key) or 0.0
                    ym[a, b] = V.y_for(key, N, ties, nm, pos, grp, made, simset) or 0.0
            Pl.append(pm)
            Yl.append(ym)
            OFF.append(OFF[-1] + len(names))
            DATE_I.append(int(str(d0)[:4]))
            MAJ.append(1 if is_major(ev["name"]) else 0)
            if i % 20 == 0:
                print("   ... %d/%d  (%.1f min)" % (i, len(usable), (time.time() - t0) / 60),
                      flush=True)
                np.savez_compressed(CKPT + ".part", P=np.vstack(Pl), Y=np.vstack(Yl),
                                    OFF=np.array(OFF), DATE=np.array(DATE_I), MAJ=np.array(MAJ))
    finally:
        RU.SHAPE_SLOPE = old
    P, Y = np.vstack(Pl), np.vstack(Yl)
    OFF, DATE_I, MAJ = np.array(OFF), np.array(DATE_I), np.array(MAJ)
    np.savez_compressed(CKPT, P=P, Y=Y, OFF=OFF, DATE=DATE_I, MAJ=MAJ)
    if os.path.exists(CKPT + ".part.npz"):
        os.unlink(CKPT + ".part.npz")
    print("\nsimulated %d events in %.1f min -> %s (%.1f MB)"
          % (len(OFF) - 1, (time.time() - t0) / 60, CKPT,
             os.path.getsize(CKPT) / 1e6), flush=True)

NEV = len(OFF) - 1


def ll(idx, s, mi):
    tot = n = 0.0
    for e in idx:
        a, b = OFF[e], OFF[e + 1]
        p = stretch(P[a:b, mi].astype(np.float64), s)
        y = Y[a:b, mi].astype(np.float64)
        q = np.clip(p, EPS, 1 - EPS)
        tot += float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).sum())
        n += (b - a)
    return tot / n if n else None


def best(idx, mi):
    """Coarse pass, then a fine refinement around the winner. Reports both."""
    c = [(s, ll(idx, s, mi)) for s in COARSE]
    s0 = min(c, key=lambda x: x[1])[0]
    fine = [round(s0 - 0.05 + 0.01 * i, 3) for i in range(11)]
    f = [(s, ll(idx, s, mi)) for s in fine if s >= 1.0]
    return min(c + f, key=lambda x: x[1])


train = [e for e in range(NEV) if DATE_I[e] < 2026]
hold = [e for e in range(NEV) if DATE_I[e] >= 2026]
print("\nTRAIN %d events (<2026)   HOLDOUT %d events (2026)" % (len(train), len(hold)), flush=True)

fitted = {}
for label, idx in (("NON-MAJOR", [e for e in train if not MAJ[e]]),
                   ("MAJOR", [e for e in train if MAJ[e]]),
                   ("ALL", train)):
    if not idx:
        continue
    print("\n=== TRAIN: %s (n=%d events) ===" % (label, len(idx)))
    print("   %-12s %8s %10s %10s %10s" % ("market", "s*", "LL(s*)", "LL(1.30)", "LL(1.00)"))
    for mi, (key, _N, _t) in enumerate(MARKETS):
        s, v = best(idx, mi)
        fitted.setdefault(label, {})[key] = s
        print("   %-12s %8.3f %10.5f %10.5f %10.5f"
              % (key, s, v, ll(idx, 1.30, mi), ll(idx, 1.00, mi)), flush=True)

if hold:
    print("\n" + "=" * 76)
    print("2026 HOLDOUT — untouched during fitting. Negative delta = the fitted s WINS.")
    print("=" * 76)
    print("   %-12s %7s %11s %11s %11s   %s"
          % ("market", "s*", "LL(s*)", "LL(1.30)", "delta", "verdict"))
    w = t = 0
    for mi, (key, _N, _t) in enumerate(MARKETS):
        s = fitted.get("NON-MAJOR", fitted.get("ALL", {})).get(key)
        if s is None:
            continue
        a, b = ll(hold, s, mi), ll(hold, 1.30, mi)
        t += 1
        w += (a < b)
        print("   %-12s %7.3f %11.5f %11.5f %+11.5f   %s"
              % (key, s, a, b, a - b, "s* better" if a < b else "1.30 better"))
    print("\n   fitted s beats 1.30 on %d of %d holdout markets" % (w, t))
