"""Independent check on RHO, using the quantity it actually controls.

RHO is the share of a player's round variance that is player-WEEK form. It barely touches a
single round (per-round variance is sig^2 either way, by construction) but it dominates the
spread of a FOUR-ROUND TOTAL, because the week effect is common to all four rounds:

    Var(72-hole total | player) = 16*RHO*sig^2 + 4*(1-RHO)*sig^2

At RHO=0.25 that is 4.75x the round variance; at RHO=0.055 it is 4.17x. So the honest test is
to measure the actual spread of 72-hole totals around what each player was expected to shoot,
and see which RHO reproduces it. This matters for real money: the 72-hole total spread is
exactly what sets cut lines, top-N tails, and 72-hole matchup prices.

The player's expected total is taken from an AS-OF fit (ratings from before the event), so no
result being measured is inside the estimate.
"""
import math
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

SEASON = 2026            # the holdout season
con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= ? ORDER BY d", ("%d-01-01" % SEASON,)).fetchall()
con.close()
rows_all = RU.all_rows()

resid = []          # (total - 4*rating) for players with all four rounds
per_round = []      # single-round residuals, to get sig^2 on the same sample
for eid, d0 in evs:
    con = sqlite3.connect(RU.DB)
    rr = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? AND score>0",
                     (eid,)).fetchall()
    con.close()
    by_rnd = defaultdict(list)
    for pl, rnd, sc in rr:
        by_rnd[rnd].append((pl, sc))
    fm = {r: st.mean(s for _p, s in v) for r, v in by_rnd.items() if len(v) >= 20}
    if len(fm) < 4:
        continue
    R, _ = RU.fit(asof=d0, rows=rows_all)
    Rn = {RU.norm(k): v for k, v in R.items()}
    got = defaultdict(dict)
    for pl, rnd, sc in rr:
        if rnd in fm:
            got[RU.norm(pl)][rnd] = sc - fm[rnd]
    for pl, d in got.items():
        r = Rn.get(pl)
        if not r:
            continue
        for _rnd, v in d.items():
            per_round.append(v - r[0])
        if all(k in d for k in (1, 2, 3, 4)):
            resid.append(sum(d[k] for k in (1, 2, 3, 4)) - 4 * r[0])

if len(resid) < 100:
    raise SystemExit("not enough completed 4-round players (%d)" % len(resid))

sig2 = st.pvariance(per_round)
obs_var = st.pvariance(resid)
print("holdout season %d: %d players with all four rounds, %d single rounds"
      % (SEASON, len(resid), len(per_round)))
print("per-round residual variance sig^2 = %.3f  (sd %.3f)" % (sig2, math.sqrt(sig2)))
print("OBSERVED 72-hole total residual variance = %.2f  (sd %.2f)"
      % (obs_var, math.sqrt(obs_var)))
print()
print("  RHO      predicted total var   predicted sd   error vs observed")
best = None
for rho in (0.0, 0.055, 0.10, 0.15, 0.20, 0.25, 0.30):
    pv = 16 * rho * sig2 + 4 * (1 - rho) * sig2
    err = abs(pv - obs_var)
    mark = ""
    if rho == 0.25:
        mark = "  <- old assumed"
    if abs(rho - 0.055) < 1e-9:
        mark = "  <- measured by ANOVA"
    print("  %.3f    %18.2f   %12.2f   %+14.2f%s"
          % (rho, pv, math.sqrt(pv), pv - obs_var, mark))
    if best is None or err < best[1]:
        best = (rho, err)
# solve for the RHO that reproduces the observed variance exactly
implied = (obs_var - 4 * sig2) / (12 * sig2)
print()
print("RHO implied by the observed spread = %.3f" % implied)
print("closest grid value = %.3f" % best[0])
print()
if abs(implied - 0.055) < abs(implied - 0.25):
    print("VERDICT: the observed 72-hole spread is closer to the MEASURED RHO than to 0.25 —")
    print("         the old value inflated 72-hole variance, pushing matchup prices toward")
    print("         50/50 and fattening the top-N tails.")
else:
    print("VERDICT: the observed spread favours the OLD RHO — do not apply the ANOVA value.")
