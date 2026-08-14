#!/usr/bin/env python3
"""How well does the sim UPDATE once rounds are posted? Pre / after-R1 / after-R2 / after-R3.

Pre-tournament calibration is already measured and good. That says nothing about conditioning:
a model can be honest about a blank slate and still badly mis-weight new information — too
sticky (ignores a 65) or too jumpy (crowns the R1 leader). The failure is invisible in the
pre-tournament numbers because it only exists once there is something to condition on.

FOUR STAGES, one ratings fit per event (the fit is ~90% of the cost and is IDENTICAL across
stages — it is as-of the event start in every case, so nothing leaks backwards from later rounds).
`progress` carries only rounds already played, so stage k sees exactly what a bettor saw.

⚠️ _recal_shape IS SKIPPED IN-PLAY by design ("SHAPE_SLOPE was fitted on pre-tournament sims").
So stages 1-3 are RAW sim output while stage 0 is stretched. That is a real difference in what is
being scored and it is why stage 0 is reported separately rather than as the first point of a
smooth curve.

THE SHARPEST TEST is the 54-hole leader's conversion rate. Historically a 54-hole leader wins
roughly a third of the time; a model that says 60% is over-reacting to three rounds, one that
says 15% is ignoring them.
"""
import datetime as dt
import os
import sys
import time
from collections import defaultdict

import numpy as np

import pga_ruler as RU
import pga_sim_validate as V

SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
SEED = 19
CKPT = "inplay_calib.npz"
MK = ["win", "top5", "top10", "top20"]
NEED = {"win": 1, "top5": 5, "top10": 10, "top20": 20}
EPS = 1e-9

if os.path.exists(CKPT):
    z = np.load(CKPT)
    P, Y, ST, EVI = z["P"], z["Y"], z["ST"], z["EVI"]
    print("loaded checkpoint: %d rows" % P.shape[0], flush=True)
else:
    events = V.load_events()
    all_rows = RU.all_rows()
    first = min(e["date"] for e in events)
    burn = (dt.date.fromisoformat(str(first)[:10]) + dt.timedelta(days=270)).isoformat()
    usable = [e for e in events if e["date"] >= burn and e["struct"] in ("cut_R2", "no_cut")]
    print("scoring %d events x 4 stages, sims=%d" % (len(usable), SIMS), flush=True)
    Pl, Yl, STl, EVl = [], [], [], []
    t0 = time.time()
    for i, ev in enumerate(usable, 1):
        d0, eid = ev["date"], ev["eid"]
        train = V._train_rows(all_rows, d0)
        V.assert_no_leak(train, eid, d0)
        R_raw, _ = RU.fit(asof=d0, rows=train)          # ONE fit, shared by all four stages
        R = {RU.norm(k): v for k, v in R_raw.items()}
        cut_n = RU.cut_rule(ev["name"], d0, n_field=len(ev["field"]))
        shp = RU.shape_slopes(ev["name"])
        pos, grp, _f = V.realised(ev)
        made = set(ev.get("made_cut") or [])
        # per-player scores by round, for building `progress`
        byr = defaultdict(dict)
        for p, rnd, sc in RU._rounds_for(eid) if hasattr(RU, "_rounds_for") else []:
            byr[p][rnd] = sc
        if not byr:
            import sqlite3
            c = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
            for p, rnd, sc in c.execute(
                    "SELECT player, rnd, score FROM rounds WHERE event_id=?", (eid,)):
                byr[p][int(rnd)] = float(sc)
            c.close()
        for stage in (0, 1, 2, 3):
            prog = None
            if stage:
                prog = {p: [v[r] for r in range(1, stage + 1) if r in v]
                        for p, v in byr.items()}
                prog = {p: s for p, s in prog.items() if len(s) == stage}
                if not prog:
                    continue
            out = RU.simulate(R, ev["field"], n_sims=SIMS, seed=SEED, cut_n=cut_n,
                              shape_slope=(shp if stage == 0 else None),
                              progress=prog)
            if not out:
                continue
            simset = set(out)
            for nm in out:
                Pl.append([(out[nm] or {}).get(k) or 0.0 for k in MK])
                Yl.append([V.y_for(k, NEED[k], False, nm, pos, grp, made, simset) or 0.0
                           for k in MK])
                STl.append(stage)
                EVl.append(i)
        if i % 20 == 0:
            print("   ... %d/%d  (%.1f min)" % (i, len(usable), (time.time() - t0) / 60),
                  flush=True)
            np.savez_compressed(CKPT + ".part", P=np.array(Pl, np.float32),
                                Y=np.array(Yl, np.float32), ST=np.array(STl, np.int8),
                                EVI=np.array(EVl, np.int32))
    P = np.array(Pl, np.float32); Y = np.array(Yl, np.float32)
    ST = np.array(STl, np.int8); EVI = np.array(EVl, np.int32)
    np.savez_compressed(CKPT, P=P, Y=Y, ST=ST, EVI=EVI)
    print("\ndone in %.1f min -> %s" % ((time.time() - t0) / 60, CKPT), flush=True)

LBL = {0: "pre-tournament", 1: "after R1", 2: "after R2", 3: "after R3"}
print("\n" + "=" * 86)
print("DOES IT GET SHARPER AS ROUNDS LAND? (Brier skill vs that stage's own base rate)")
print("=" * 86)
print("   %-16s %8s %10s %10s %10s %10s" % ("stage", "rows", "win", "top5", "top10", "top20"))
for st in (0, 1, 2, 3):
    s = ST == st
    if s.sum() < 100:
        continue
    cells = []
    for mi in range(4):
        p, y = P[s, mi].astype(np.float64), Y[s, mi].astype(np.float64)
        br = ((p - y) ** 2).mean()
        bb = ((y.mean() - y) ** 2).mean()
        cells.append(1 - br / bb)
    print("   %-16s %8d %9.4f %10.4f %10.4f %10.4f" % (LBL[st], s.sum(), *cells))

print("\n" + "=" * 86)
print("IS THE UPDATE HONEST? predicted vs actual, win market, by stage")
print("=" * 86)
for st in (0, 1, 2, 3):
    s = ST == st
    if s.sum() < 100:
        continue
    p, y = P[s, 0].astype(np.float64), Y[s, 0].astype(np.float64)
    print("\n   %s" % LBL[st])
    for lo, hi in ((0, .02), (.02, .05), (.05, .10), (.10, .20), (.20, .40), (.40, 1.01)):
        m = (p >= lo) & (p < hi)
        if m.sum() > 25:
            print("      said %2.0f-%3.0f%%  n=%6d  pred %5.1f%%  actual %5.1f%%  gap %+5.1fpp"
                  % (100 * lo, 100 * hi, m.sum(), 100 * p[m].mean(), 100 * y[m].mean(),
                     100 * (y[m].mean() - p[m].mean())))

print("\n" + "=" * 86)
print("THE SHARP TEST — the 54-hole leader (model's top pick after R3)")
print("=" * 86)
for st in (0, 1, 2, 3):
    idx = defaultdict(list)
    for j in np.where(ST == st)[0]:
        idx[int(EVI[j])].append(j)
    hit = n = 0
    pred = []
    for _e, js in idx.items():
        if len(js) < 20:
            continue
        js = sorted(js, key=lambda j: -P[j, 0])
        hit += float(Y[js[0], 0] > 0.5)
        pred.append(float(P[js[0], 0]))
        n += 1
    if n:
        print("   %-16s top pick won %3d/%3d = %5.1f%%   model said %5.1f%%   gap %+5.1fpp"
              % (LBL[st], hit, n, 100 * hit / n, 100 * np.mean(pred),
                 100 * (hit / n - np.mean(pred))))
