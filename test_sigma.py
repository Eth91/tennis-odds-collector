"""Is the per-player SIGMA calibrated after SIG_SHRINK 20 -> 78?

Sigma is not scored by the walk-forward (which only uses the rating), so the EB derivation was
its only support. Direct test: standardise every out-of-sample round,

    z = (actual field-relative score - rating) / sigma

and check the spread of z. sd(z) = 1 means sigma is right; < 1 means sigma is too WIDE (the
model is under-confident, which flattens matchup prices and fattens tails); > 1 means too
narrow, which is the dangerous direction for a bettor.

Run on 2026 (the holdout) with sigma from as-of fits, so nothing measured is in the estimate.
"""
import math
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2026-01-01' ORDER BY d").fetchall()
con.close()
rows_all = RU.all_rows()

print("  SIG_SHRINK   sd(z)    mean|z|   n rounds   verdict")
for ss in (20.0, 78.0, 150.0):
    zs = []
    for eid, d0 in evs:
        R, _ = RU.fit(asof=d0, rows=rows_all, sig_shrink=ss)
        Rn = {RU.norm(k): v for k, v in R.items()}
        con = sqlite3.connect(RU.DB)
        rr = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? AND score>0",
                         (eid,)).fetchall()
        con.close()
        by = defaultdict(list)
        for pl, rnd, sc in rr:
            by[rnd].append((pl, sc))
        for rnd, lst in by.items():
            if len(lst) < 20:
                continue
            fm = st.mean(s for _p, s in lst)
            for pl, sc in lst:
                r = Rn.get(RU.norm(pl))
                if r and r[1] > 0:
                    zs.append(((sc - fm) - r[0]) / r[1])
    if len(zs) < 200:
        print("    %.0f: too few rounds" % ss)
        continue
    sd = st.pstdev(zs)
    verdict = ("sigma too WIDE (under-confident)" if sd < 0.97
               else "sigma too NARROW (over-confident)" if sd > 1.03 else "CALIBRATED")
    tag = "  <- old" if ss == 20.0 else ("  <- measured" if ss == 78.0 else "")
    print("    %6.0f     %.4f   %.4f    %6d   %s%s"
          % (ss, sd, st.mean(abs(z) for z in zs), len(zs), verdict, tag))
