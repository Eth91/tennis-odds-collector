"""Settle SIG_SHRINK by splitting the calibration test on SAMPLE SIZE.

The aggregate test was inconclusive: sd(z) = 1.0005 at SIG_SHRINK=20 vs 0.9875 at 78, both
calibrated. But that aggregate is dominated by high-volume players, who supply most rounds and
whose own sd is well estimated — for them the two settings barely differ.

The change should matter for THIN-SAMPLE players. A sample sd from n rounds has sampling noise
about sigma/sqrt(2n): at n=300 that is 0.11, comfortably under the measured true spread of
player sd (0.23), so trusting own-sd is fine; at n=25 it is 0.40, nearly double the real
spread, so own-sd is mostly noise and must be shrunk hard. SIG_SHRINK=20 gives an n=25 player
56% weight on his own sd; 78 gives 24%.

So: sd(z) by sample-size bucket. If the thin buckets are better calibrated at 78 and the fat
buckets are unchanged, the measured value is right and the aggregate test was simply blind.
"""
import os
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

RU.DB = os.path.expanduser("~/pga_model_snap.sqlite")   # immune to the loop rewriting the repo copy

con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2026-01-01' ORDER BY d").fetchall()
con.close()
rows_all = RU.all_rows()

BUCKETS = [(0, 20, "thin  n<20"), (20, 60, "n 20-59"), (60, 150, "n 60-149"),
           (150, 10 ** 9, "fat  n>=150")]
res = {}
for ss in (20.0, 78.0):
    zs = defaultdict(list)
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
                if not r or r[1] <= 0:
                    continue
                z = ((sc - fm) - r[0]) / r[1]
                for lo, hi, name in BUCKETS:
                    if lo <= r[2] < hi:
                        zs[name].append(z)
                        break
    res[ss] = {k: (st.pstdev(v), len(v)) for k, v in zs.items() if len(v) >= 150}

print("  sd(z) by player sample size — 1.000 is perfectly calibrated")
print("  %-14s %10s %10s %8s   %s" % ("bucket", "SS=20", "SS=78", "n", "which is closer to 1"))
better78 = better20 = 0
for _lo, _hi, name in BUCKETS:
    a = res[20.0].get(name)
    b = res[78.0].get(name)
    if not a or not b:
        continue
    d20, d78 = abs(a[0] - 1), abs(b[0] - 1)
    win = "SS=78" if d78 < d20 else "SS=20"
    if d78 < d20:
        better78 += 1
    else:
        better20 += 1
    print("  %-14s %10.4f %10.4f %8d   %s" % (name, a[0], b[0], a[1], win))
print()
print("  buckets won: SS=78 in %d, SS=20 in %d" % (better78, better20))
print("  (the aggregate test could not see this: fat buckets carry most of the rounds and")
print("   the two settings barely differ there.)")
