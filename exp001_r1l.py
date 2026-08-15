#!/usr/bin/env python3
"""EXP-001 — first market-relative test on real closes: St Jude 1st Round Leader.

WHY THIS MARKET, TODAY. Top-N/Win closes exist for St Jude but the event does not finish until
Sunday, so 0 of them are gradeable. 1st Round Leader IS gradeable: R1 completed 2026-08-13 and we
hold 69 tee-gated closes captured at 12:05, five minutes before the 12:10 first tee.

WHAT IS BEING TESTED (Lane B, not Lane A): does the model's R1-leader probability beat the
DEVIGGED CLOSE, graded on the realised R1? Forecast accuracy is already established; this asks
whether it is worth money at a real price.

TEMPORAL INTEGRITY: ratings fit asof 2026-08-13 use rounds strictly BEFORE that date, so R1 is not
in the training set. The close is 12:05, the tee is 12:10 — the price was available at prediction
time. No information from R1 enters the prediction.

SETTLEMENT: five players tied at 65. FanDuel settles round-leader as a DEAD HEAT, so the realised
value is 1/5 for each of them, not 1. Grading it 0/1 would manufacture a large fake error for the
book AND for the model.

⚠️ n = 69 runners from ONE event and ONE market. Under the charter's multiple-testing rule this is
a FIRST OBSERVATION, not evidence of edge. It cannot establish anything on its own; it can only
fail loudly, which is still worth knowing.
"""
import math
import sqlite3
from collections import defaultdict

import pga_ruler as RU
import pga_sim as PS

EV = "%St Jude%"
ASOF = "2026-08-13"
EPS = 1e-9

mc = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
closes = {}
for run, od, ts in mc.execute(
        "SELECT runner, close_odds, close_ts FROM moves WHERE event LIKE ? AND market=? "
        "AND close_odds IS NOT NULL", (EV, "1st Round Leader")):
    closes[RU.norm(run)] = (float(od), ts)
mc.close()
print("closes: %d, captured %s" % (len(closes), sorted(t for _o, t in closes.values())[-1]))

con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
eid = (con.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                   ("%St. Jude%", "2026%")).fetchone()
       or con.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                      ("%St Jude%", "2026%")).fetchone())[0]
r1 = {p: float(s) for p, s in con.execute(
    "SELECT player, score FROM rounds WHERE event_id=? AND rnd=1", (eid,))}
field = [p for p in r1]
con.close()
low = min(r1.values())
winners = [p for p, s in r1.items() if s == low]
print("R1: %d players, low %g by %d — dead heat share %.4f each"
      % (len(r1), low, len(winners), 1.0 / len(winners)))

R, _g = PS.ratings_asof(ASOF)
fp = [p for p in field if PS.lookup(R, p) is not None]
res = PS.simulate(fp, n=40000, seed=41, ratings=R, cut_n=None, spread=1.30)
lead = res.leader(1, ties=True)

rows = []
for p in fp:
    k = RU.norm(p)
    if k not in closes:
        continue
    od, _ts = closes[k]
    if od <= 1.0:
        continue
    y = (1.0 / len(winners)) if p in winners else 0.0
    rows.append((p, float(lead.get(p, 0.0)), od, y))
imp_tot = sum(1.0 / od for _p, _m, od, _y in rows)
print("matched %d runners | book overround %.3f (%.1f%% hold)"
      % (len(rows), imp_tot, 100 * (imp_tot - 1) / imp_tot))

ll_m = ll_b = 0.0
ev_sum = 0.0
flags = []
for p, pm, od, y in rows:
    pb = (1.0 / od) / imp_tot                      # devigged close
    qm = min(max(pm, EPS), 1 - EPS)
    qb = min(max(pb, EPS), 1 - EPS)
    ll_m += -(y * math.log(qm) + (1 - y) * math.log(1 - qm))
    ll_b += -(y * math.log(qb) + (1 - y) * math.log(1 - qb))
    e = pm * od - 1.0
    ev_sum += e
    if e >= 0.03 and 1.15 <= (pm / max(pb, EPS)) <= 2.0:
        flags.append((p, pm, pb, od, e, y))
n = len(rows)
print("\n=== FORECAST vs BOOK (log-loss, lower better) ===")
print("   model %.5f   book %.5f   gap %+.1f pts  -> %s"
      % (ll_m / n, ll_b / n, (ll_m - ll_b) / n * 100,
         "MODEL BETTER" if ll_m < ll_b else "BOOK BETTER"))

print("\n=== WOULD THE LIVE GATE HAVE FLAGGED ANYTHING? (EV>=3%, ratio 1.15-2.0) ===")
if not flags:
    print("   0 flags — nothing clears the live thresholds")
else:
    stake = pnl = 0.0
    for p, pm, pb, od, e, y in sorted(flags, key=lambda x: -x[4]):
        ret = (od - 1.0) * y - (1.0 - y)      # dead-heat aware
        stake += 1.0
        pnl += ret
        print("   %-22s model %.4f fair %.4f @%-6.2f EV %+5.1f%%  result %+.2fu"
              % (p[:22], pm, pb, od, 100 * e, ret))
    print("   %d bets, %+.2fu, ROI %+.1f%%" % (len(flags), pnl, 100 * pnl / stake))

print("\n=== the five co-leaders, model vs book ===")
for p in sorted(winners):
    k = RU.norm(p)
    if k in closes and p in lead:
        od = closes[k][0]
        print("   %-22s model %.4f  book-fair %.4f  @%.2f"
              % (p[:22], lead[p], (1.0 / od) / imp_tot, od))
print("\n⚠️ n=69 from ONE event, ONE market. First observation, not evidence.")
