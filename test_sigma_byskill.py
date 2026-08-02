"""Is sigma over-shrunk for ELITE players? The hypothesis behind every "too timid" slope.

Every tournament market measured slope >1 (1.22-1.56), meaning the sim under-separates the top of
the field. One candidate cause: SIG_SHRINK=78 pulls every player's sd toward the global 2.9, but
Scheffler's own sd is 2.51. Over-assigning volatility to the best players shrinks their apparent
edge, which would produce exactly that under-separation.

Test: bin players by RATING (not by sample size, which is what the earlier test did and why it
missed this), and compare the sigma we ASSIGN against the sd they actually realize out of sample.
If elite players realize a materially tighter sd than we assign, the hypothesis holds and the fix
is to let sigma vary with skill instead of collapsing toward the field.

Out of sample by construction: sigma comes from an as-of fit, realized sd from the event itself.
"""
import os
import shutil
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_sig.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP

con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2025-01-01' ORDER BY d").fetchall()
con.close()
rows_all = RU.all_rows()

# collect (rating, assigned_sigma, realized_residual) per player-round, out of sample
recs = []
for eid, d0 in evs:
    R, gsd = RU.fit(asof=d0, rows=rows_all)
    Rn = {RU.norm(k): v for k, v in R.items()}
    con = sqlite3.connect(RU.DB)
    rr = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? AND score>0",
                     (eid,)).fetchall()
    con.close()
    by = defaultdict(list)
    for pl, rnd, sc in rr:
        by[rnd].append((RU.norm(pl), sc))
    for rnd, lst in by.items():
        if len(lst) < 40:
            continue
        fm = st.mean(s for _p, s in lst)
        for pl, sc in lst:
            v = Rn.get(pl)
            if v and v[1] > 0:
                recs.append((v[0], v[1], (sc - fm) - v[0]))     # rating, sigma, residual

print("out-of-sample player-rounds: %d over %d events" % (len(recs), len(evs)))
if len(recs) < 2000:
    raise SystemExit("too few")

recs.sort()
NB = 6
sz = len(recs) // NB
print()
print("  binned by RATING (best first). 'realized sd' is the sd of the residual around our own")
print("  prediction, so a well-set sigma matches it and z-sd lands on 1.00.")
print()
print("  %-16s %7s %10s %11s %8s   %s" % ("rating bin", "n", "assigned", "realized", "z-sd",
                                          "reads as"))
out = []
for i in range(NB):
    ch = recs[i * sz:(i + 1) * sz] if i < NB - 1 else recs[i * sz:]
    if len(ch) < 100:
        continue
    rat = st.mean(c[0] for c in ch)
    sig = st.mean(c[1] for c in ch)
    real = st.pstdev([c[2] for c in ch])
    zsd = st.pstdev([c[2] / c[1] for c in ch])
    verdict = ("sigma TOO WIDE" if zsd < 0.95 else
               "sigma TOO NARROW" if zsd > 1.05 else "ok")
    out.append((rat, sig, real, zsd))
    print("  %-16s %7d %10.3f %11.3f %8.3f   %s"
          % ("%+.2f str/rd" % rat, len(ch), sig, real, zsd, verdict))
print()
if out:
    top, bot = out[0], out[-1]
    print("  ELITE bin:  rating %+.2f  assigned sigma %.3f  realized %.3f  (%+.3f)"
          % (top[0], top[1], top[2], top[2] - top[1]))
    print("  WEAKEST bin: rating %+.2f  assigned sigma %.3f  realized %.3f  (%+.3f)"
          % (bot[0], bot[1], bot[2], bot[2] - bot[1]))
    print()
    spread_assigned = bot[1] - top[1]
    spread_real = bot[2] - top[2]
    print("  sigma spread across skill:  we assign %.3f, reality shows %.3f" %
          (spread_assigned, spread_real))
    if spread_real > spread_assigned + 0.05:
        print("  -> HYPOTHESIS HOLDS: reality separates volatility by skill MORE than we do.")
        print("     Letting sigma vary with skill should sharpen the favourites and pull the")
        print("     tournament slopes down toward 1.0.")
    elif abs(top[2] - top[1]) < 0.06:
        print("  -> HYPOTHESIS FAILS: elite sigma is already about right, so over-shrunk sigma")
        print("     is NOT what makes the tournament markets read too timid. Look elsewhere")
        print("     (candidate: the sim's round-to-round independence, i.e. RHO).")
    else:
        print("  -> MIXED: see the per-bin z-sd column for where it actually goes wrong.")
