"""Would the 11 St Jude top-N flags survive the new slopes, priced at the REAL pre-tee close?

The flags were logged at 09:05 under SHAPE_SLOPE=1.30 global. The board is now closed (every
top-N market deadlines at the 12:10 R1 first tee), so the live screen cannot exercise the change
this week -- but the rescued 12:05 closes can, and they are the last honest price.

The gate is applied VERBATIM from pga_e3, not re-derived: PRICE_FLOOR, TN_EDGE, TN_RATIO_MIN/MAX,
EV_MIN, and the same log-odds _blend at BLEND_W. A re-implementation that drifts from the live
gate would answer a question nobody asked.
"""
import math
import sqlite3
from collections import defaultdict

import pga_e3 as E3
import pga_ruler as RU

EV = "PGA FedEx St Jude Championship 2026"
ASOF = "2026-08-13"
FAM = {"top5": ("Top 5", 5), "top10": ("Top 10", 10), "top20": ("Top 20", 20)}

R_raw, _ = RU.fit(asof=ASOF)
R = {RU.norm(k): v for k, v in R_raw.items()}
con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
eid = (con.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                   ("%St. Jude%", "2026%")).fetchone()
       or con.execute("SELECT event_id FROM rounds WHERE event LIKE ? AND date LIKE ? LIMIT 1",
                      ("%St Jude%", "2026%")).fetchone())[0]
field = [r[0] for r in con.execute("SELECT DISTINCT player FROM rounds WHERE event_id=?", (eid,))]
con.close()

cut_n = RU.cut_rule(EV, ASOF, n_field=len(field))
sims = {"OLD 1.30": RU.simulate(R, field, n_sims=20000, seed=13, cut_n=cut_n,
                                shape_slope=1.30, reps=2),
        "NEW fitted": RU.simulate(R, field, n_sims=20000, seed=13, cut_n=cut_n,
                                  shape_slope=RU.shape_slopes(EV), reps=2)}

# ---- the REAL pre-tee closes rescued into golf_moves --------------------------------------
mc = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
closes = defaultdict(dict)
for mkt, run, od, ts in mc.execute(
        "SELECT market, runner, close_odds, close_ts FROM moves "
        "WHERE event LIKE ? AND market IN (?,?,?) AND close_odds IS NOT NULL",
        ("%St Jude%", "Top 5", "Top 10", "Top 20")):
    closes[mkt][RU.norm(run)] = (float(od), ts)
mc.close()
print("rescued closes: " + " · ".join("%s=%d" % (k, len(v)) for k, v in sorted(closes.items())))
print("gate (verbatim from pga_e3): PRICE_FLOOR=%.2f TN_EDGE=%.2f RATIO=[%.2f,%.2f] EV_MIN=%.2f "
      "BLEND_W=%.2f\n" % (E3.PRICE_FLOOR, E3.TN_EDGE, E3.TN_RATIO_MIN, E3.TN_RATIO_MAX,
                          E3.EV_MIN, E3.BLEND_W))


def devig(mkt, N):
    """One-sided devig: scale implied probabilities so the market sums to its nominal count."""
    imp = {p: 1.0 / od for p, (od, _t) in closes[mkt].items()}
    tot = sum(imp.values())
    if tot <= 0:
        return {}
    return {p: v * (N / tot) for p, v in imp.items()}


print("=" * 96)
print("REPRICED AT THE 12:05 PRE-TEE CLOSE — would the gate still flag it?")
print("=" * 96)
for arm, sim in sims.items():
    kept = []
    for fam, (mkt, N) in FAM.items():
        if mkt not in closes:
            continue
        fair = devig(mkt, N)
        for pn, (od, _ts) in closes[mkt].items():
            if pn not in fair:
                continue
            ours = (sim.get(pn) or {}).get(fam)
            if ours is None:
                for k in sim:
                    if RU.norm(k) == pn:
                        ours = sim[k][fam]
                        break
            if ours is None:
                continue
            f = fair[pn]
            if f <= 0 or od <= 1.0:
                continue
            blend = E3._blend(f, ours)
            ratio = ours / f
            ev = blend * od - 1.0
            if (od >= 1.0 / E3.PRICE_FLOOR and E3.TN_RATIO_MIN <= ratio <= E3.TN_RATIO_MAX
                    and blend - f >= E3.TN_EDGE and ev >= E3.EV_MIN):
                kept.append((fam, pn, od, f, ours, blend, ev))
    print("\n%-11s -> %d flags" % (arm, len(kept)))
    for fam, pn, od, f, ours, blend, ev in sorted(kept, key=lambda x: -x[6])[:12]:
        print("   %-7s %-22s @%-6.2f  fair %.3f  model %.3f  blend %.3f  EV %+.1f%%"
              % (fam, pn[:22], od, f, ours, blend, 100 * ev))

print("\n" + "=" * 96)
print("the 11 flags actually logged at 09:05 (priced under 1.30), for reference")
print("=" * 96)
pc = sqlite3.connect("file:pga_paper.sqlite?mode=ro", uri=True, timeout=30)
for st, mk, run, od, pb, pf in pc.execute(
        "SELECT stream, market, runner, odds, p_bet, p_fair FROM flags "
        "WHERE event LIKE ? AND stream LIKE ? ORDER BY stream", ("%St Jude%", "%top%")):
    print("   %-18s %-28s %-20s @%-6s p_bet %.3f  p_fair %.3f"
          % (st, mk[:28], run[:20], od, pb or 0, pf or 0))
pc.close()
