#!/usr/bin/env python3
"""Measure the player-week effect DIRECTLY from scores. No model, no fitted target.

rho is the share of a player's round-to-round variance that is shared across the event — form.
Two fits disagree by 12x (pga_ruler ships 0.05; the cut-line calibration wants ~0.6), so measure
the thing itself instead of arbitrating between them.

⚠️ ROUNDS 1 AND 2 ONLY. pga_ruler's own constant note records getting a NEGATIVE rho as "an
artefact of cut selection, since only cut-makers have four rounds" — conditioning on survival
induces negative dependence, because a bad R1 must be offset by a good R2 to be in the sample at
all. Every starter has R1 and R2, so this window is selection-free.

resid[p,r] = score[p,r] - fieldmean[r] - mu[p]
  - subtracting the ROUND's field mean removes conditions (the common shock, i.e. tau);
  - subtracting the player's AS-OF rating removes talent — without it, good players score well in
    both rounds and the correlation just measures skill, not form.
rho = corr(resid[p,1], resid[p,2]) pooled across events.
"""
import datetime as dt
import sqlite3
import sys
import time
from collections import defaultdict

import numpy as np

import pga_ruler as RU
import pga_sim as PS
import pga_sim_validate as V

NEV = int(sys.argv[1]) if len(sys.argv) > 1 else 80

events = V.load_events()
all_rows = RU.all_rows()
first = min(e["date"] for e in events)
burn = (dt.date.fromisoformat(str(first)[:10]) + dt.timedelta(days=270)).isoformat()
usable = [e for e in events if e["date"] >= burn]
step = max(1, len(usable) // NEV)
usable = usable[::step][:NEV]
print("events: %d" % len(usable), flush=True)

con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
A, B, per_ev = [], [], []
t0 = time.time()
for i, ev in enumerate(usable, 1):
    byp = defaultdict(dict)
    for p, r, s in con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?",
                              (ev["eid"],)):
        byp[p][int(r)] = float(s)
    pl = [p for p, v in byp.items() if 1 in v and 2 in v]
    if len(pl) < 50:
        continue
    R, _g = PS.ratings_asof(ev["date"], rows=V._train_rows(all_rows, ev["date"]))
    rows = []
    for p in pl:
        r = PS.lookup(R, p)
        if r:
            rows.append((byp[p][1], byp[p][2], r[0]))
    if len(rows) < 40:
        continue
    s1 = np.array([x[0] for x in rows]); s2 = np.array([x[1] for x in rows])
    mu = np.array([x[2] for x in rows])
    r1 = s1 - s1.mean() - mu                    # round mean removes conditions; mu removes talent
    r2 = s2 - s2.mean() - mu
    A.append(r1); B.append(r2)
    if len(rows) >= 60:
        per_ev.append(float(np.corrcoef(r1, r2)[0, 1]))
    if i % 20 == 0:
        print("   ... %d/%d (%.1f min)" % (i, len(usable), (time.time() - t0) / 60), flush=True)
con.close()

a = np.concatenate(A); b = np.concatenate(B)
rho = float(np.corrcoef(a, b)[0, 1])
n = a.size
se = (1 - rho ** 2) / max(1, np.sqrt(n - 3))
print("\n" + "=" * 66)
print("MEASURED PLAYER-WEEK CORRELATION (R1 vs R2, selection-free)")
print("=" * 66)
print("   pooled rho = %+.4f   n = %d player-events   ~SE %.4f" % (rho, n, se))
print("   95%% CI approx [%+.4f, %+.4f]" % (rho - 1.96 * se, rho + 1.96 * se))
if per_ev:
    pe = np.array(per_ev)
    print("   per-event rho: median %+.3f  mean %+.3f  IQR [%+.3f, %+.3f]  (%d events)"
          % (np.median(pe), pe.mean(), np.percentile(pe, 25), np.percentile(pe, 75), pe.size))

print("\n   PLACEBO — shuffle players between the two rounds; true rho must vanish")
rng = np.random.default_rng(7)
sh = []
for x, y in zip(A, B):
    idx = rng.permutation(len(y))
    sh.append(float(np.corrcoef(x, y[idx])[0, 1]) if len(y) > 3 else 0.0)
print("   shuffled rho: mean %+.4f  (should be ~0)" % float(np.mean(sh)))

print("\n   pga_ruler ships RHO = %.2f" % RU.RHO)
print("   cut-line calibration wanted ~0.60")
