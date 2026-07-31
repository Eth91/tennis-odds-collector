"""Does OUR model see what PropsCash sees — IND tough on centres, soft on forwards?

The screenshots claim IND ranks 7th vs C (25% L10 hit rate, -5.92 vs line) and 13th vs F (50%,
-0.3). If real, that is a genuine argument for Carleton over DiLeo and cuts against everything the
role-expansion analysis says.

We already carry a DvP term, but deliberately small: prop_edges does
    elev_avg += dvp(opp, pos, stat) * proj_min
with the comment that the backtest showed it marginal, so it "breaks ties / orders overs by matchup
but never overrides the validated under model".

Three questions, in order:
  1. What does our DvP actually say for IND vs C and IND vs F on points?
  2. How many points does that move each projection — is it decisive or decorative?
  3. Does DvP have any predictive value in OUR graded record? A vendor's positional hit-rate is a
     different statistic from our coefficient, and 5-6 games is a very short sample.
"""
import sqlite3
from collections import defaultdict

import wnba_dvp as DVP

print("=== 1. our DvP coefficient (stat-units per MINUTE; + = opponent allows more) ===")
tbl = DVP.dvp_table()
print("  tables available:", sorted(tbl)[:12])
for pos in ("C", "F", "G"):
    c = DVP.dvp("IND", pos, "pts")
    note = DVP.matchup_note("IND", pos, "pts")
    print("  IND vs %-2s pts: coef %+0.5f/min   note=%s" % (pos, c, note))

print("\n  where IND ranks among all teams, per position (lower coef = tougher):")
for pos in ("C", "F", "G"):
    key = "pts|%s" % DVP._PG.get(pos, pos)
    d = tbl.get(key, {})
    if not d:
        print("    %s: no table" % pos)
        continue
    order = sorted(d.items(), key=lambda kv: kv[1])
    rank = [t for t, _ in order].index("IND") + 1 if "IND" in d else None
    print("    %s: IND is %s of %d  (toughest %s ... softest %s)"
          % (pos, rank, len(order), order[0][0], order[-1][0]))

print("\n=== 2. how many POINTS does that move each projection? ===")
for name, pos, pmin in (("Megan DiLeo", "C", 27.0), ("Bridget Carleton", "F", 31.0)):
    c = DVP.dvp("IND", pos, "pts")
    print("  %-18s pos %s  proj_min %.0f  ->  DvP adjustment %+.2f points"
          % (name, pos, pmin, c * pmin))
print("  (this is ADDED to elev_avg before the line comparison)")

print("\n=== 3. does DvP predict anything in OUR graded record? ===")
con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
g = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()
import wnba_slip as SL
overs = [r for r in g if r["result"] in ("over", "under") and (r["side"] or "over") == "over"
         and (r.get("tier") or "firm") != "n1"]
dec, _ = SL.current_selection(overs)
U = [r for r in dec if str(r.get("confidence")) in {"confirmed", "likely"} or r.get("played")]

# recover each bet's DvP coefficient from opp + position
try:
    import wnba_wowy as W
    pl = W.players()
except Exception:                                                  # noqa: BLE001
    pl = {}
buck = defaultdict(list)
for r in U:
    pos = (pl.get(r.get("player")) or {}).get("position")
    opp = r.get("opp")
    stat = {"points": "pts", "rebounds": "reb", "assists": "ast"}.get(r.get("stat"))
    if not (pos and opp and stat):
        continue
    c = DVP.dvp(opp, pos, stat)
    note = DVP.matchup_note(opp, pos, stat)
    buck[note or "neutral"].append(r)


def ret(r):
    return (float(r.get("odds") or 0) - 1) if r["result"] == (r["side"] or "over") else -1.0


print("  %-12s %4s %8s %7s %9s" % ("matchup", "n", "record", "hit%", "units"))
for k in ("soft", "neutral", "tough"):
    v = buck.get(k) or []
    if not v:
        print("  %-12s (none)" % k)
        continue
    w = sum(1 for r in v if r["result"] == (r["side"] or "over"))
    print("  %-12s %4d %4d-%-3d %6.1f%% %+8.2fu"
          % (k, len(v), w, len(v) - w, 100 * w / len(v), sum(ret(r) for r in v)))
print("\n  'tough' = our DvP puts the opponent in the toughest 3 for that position+stat;")
print("  'soft' = the softest 3. If tough matchups lose and soft ones win, the vendor's")
print("  positional read is measuring something real that we under-weight.")
