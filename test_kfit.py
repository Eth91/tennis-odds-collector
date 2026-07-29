"""Out-of-sample test of PERSONAL COURSE FIT — the change from K_FIT 8 to ~105 is 13x, and
course history is the most over-claimed edge in golf, so the closed-form answer deserves a
direct predictive check rather than trust.

Design (strictly out of sample, and it needs no model at all):
  For every player-course cell, split that player's rounds at that course by DATE. Estimate
  the course-fit deviation from the EARLY half, then measure how much of it actually shows up
  in the LATE half. Regressing late deviation on early deviation gives the honest shrinkage
  weight directly: slope = n/(n+k), so k = n*(1-slope)/slope.

  A slope near 1 would mean course fit is real and persistent (K_FIT should be small). A slope
  near 0 means the early deviation is noise (K_FIT should be huge, i.e. the term is off).

This is the same question the empirical-Bayes formula answers, asked a completely different
way, so agreement between the two is real evidence and disagreement is a warning.
"""
import sqlite3
import statistics as st
from collections import defaultdict

import pga_calib as CAL
import pga_ruler as RU

res = CAL.residuals()
con = sqlite3.connect(RU.DB)
evname = dict(con.execute("SELECT event_id, event FROM rounds GROUP BY event_id"))
con.close()

# player baseline over ALL their rounds (both halves) — this is a deliberate simplification:
# it slightly favours the "course fit is real" hypothesis, so an unfavourable result is safe
pl_all = defaultdict(list)
for pl, _e, _d, _r, rel in res:
    pl_all[pl].append(rel)
base = {p: st.mean(v) for p, v in pl_all.items() if len(v) >= 20}

cells = defaultdict(list)
for pl, eid, date, _r, rel in res:
    if pl in base:
        cells[(pl, str(evname.get(eid, "")).lower())].append((date, rel))

xs, ys, ns = [], [], []
for (pl, _c), v in cells.items():
    if len(v) < 8:                      # need enough to split and still say anything
        continue
    v.sort()
    h = len(v) // 2
    early = [r for _d, r in v[:h]]
    late = [r for _d, r in v[h:]]
    xs.append(st.mean(early) - base[pl])
    ys.append(st.mean(late) - base[pl])
    ns.append(h)

print("cells with >=8 rounds at one course: %d" % len(xs))
if len(xs) < 40:
    raise SystemExit("not enough cells")

mx, my = st.mean(xs), st.mean(ys)
den = sum((x - mx) ** 2 for x in xs)
slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0
sx, sy = st.pstdev(xs), st.pstdev(ys)
r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)) / (sx * sy) if sx and sy else 0
nbar = st.mean(ns)
print("early deviation sd %.3f str, late deviation sd %.3f str" % (sx, sy))
print("regression of LATE on EARLY: slope %+.4f   r %+.3f   (mean n per half %.1f)"
      % (slope, r, nbar))
if slope > 0.01:
    k_implied = nbar * (1 - slope) / slope
    print("=> implied K_FIT = n*(1-slope)/slope = %.1f pseudo-rounds" % k_implied)
else:
    print("=> slope is ~0: an early course deviation does NOT predict the late one at all;")
    print("   personal course fit is indistinguishable from noise -> K_FIT effectively OFF")
print()
print("closed-form empirical Bayes said K_FIT = 104.8 (true affinity sd 0.267 str)")
print("current code uses K_FIT = 8.0, i.e. it trusts %.0f%% of a 4-round course deviation"
      % (100 * 4 / (4 + 8)))
print("at the measured value it would trust %.1f%%" % (100 * 4 / (4 + 104.8)))
