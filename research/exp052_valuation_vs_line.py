"""Is our PROJECTION a better estimate of the outcome than the BOOK'S LINE?

Head-to-head on the same rows, so it is a paired comparison (immune to selection effects).
If the line wins, extra modelling effort is not the lever -- the market is already the better
valuator and the edge has to come from price, not from out-projecting it.

wnba_proj_log carries proj_pts/reb/ast AND actual_pts/reb/ast on the same row.
⚠️ It upserts on (date,pid) so it holds ONE row per player-day (the final write) — fine here,
we only need proj vs actual, not a time series.
"""
import sqlite3, statistics as st, math
from collections import defaultdict
p = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_proj_log.sqlite?mode=ro", uri=True, timeout=30)
p.row_factory = sqlite3.Row
led = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
led.row_factory = sqlite3.Row
# the book's line for the same player-day-stat (any tracked/considered row)
line = {}
for r in led.execute("SELECT pred_date, player, stat, line FROM predictions WHERE line IS NOT NULL"):
    line[(str(r[0]), str(r[1]), str(r[2]))] = float(r[3])
rows = [dict(r) for r in p.execute("SELECT * FROM projections WHERE graded=1")]
print(f"graded projection rows: {len(rows)}")
STATS = (("points","proj_pts","actual_pts"), ("rebounds","proj_reb","actual_reb"),
         ("assists","proj_ast","actual_ast"))
print(f"\n{'stat':9s} {'n':>4s} {'proj bias':>10s} {'|proj err|':>11s} {'|line err|':>11s} "
      f"{'proj closer':>12s}")
allp, alll = [], []
for stat, pk, ak in STATS:
    v = []
    for r in rows:
        pr, ac = r.get(pk), r.get(ak)
        ln = line.get((str(r["date"]), str(r["player"]), stat))
        if pr is None or ac is None or ln is None: continue
        v.append((float(pr), float(ac), ln))
    if len(v) < 15:
        print(f"{stat:9s} thin ({len(v)})"); continue
    bias = st.mean([pr-ac for pr,ac,_ in v])
    pe = [abs(pr-ac) for pr,ac,_ in v]
    le = [abs(ln-ac) for _,ac,ln in v]
    closer = sum(1 for (pr,ac,ln) in v if abs(pr-ac) < abs(ln-ac))
    allp += pe; alll += le
    print(f"{stat:9s} {len(v):4d} {bias:+10.2f} {st.mean(pe):11.2f} {st.mean(le):11.2f} "
          f"{closer:6d}/{len(v):<5d} = {closer/len(v)*100:.0f}%")
if allp:
    d = [a-b for a,b in zip(allp, alll)]
    se = st.pstdev(d)/math.sqrt(len(d)) or 1e-9
    print(f"\nPOOLED  n={len(allp)}  mean |proj err| {st.mean(allp):.2f}  vs  "
          f"|line err| {st.mean(alll):.2f}")
    print(f"  paired difference {st.mean(d):+.3f}  t={st.mean(d)/se:+.2f}   "
          f"-> {'the LINE is the better estimate' if st.mean(d) > 0 else 'our PROJECTION is better'}")
print("\n=== IS THE ERROR BIAS (fixable) OR NOISE (irreducible)? ===")
for stat, pk, ak in STATS:
    v = [(float(r[pk]), float(r[ak])) for r in rows
         if r.get(pk) is not None and r.get(ak) is not None]
    if len(v) < 15: continue
    errs = [pr-ac for pr,ac in v]
    print(f"  {stat:9s} n={len(v):3d}  mean error {st.mean(errs):+6.2f}  sd {st.pstdev(errs):5.2f}"
          f"   bias/noise ratio {abs(st.mean(errs))/max(st.pstdev(errs),1e-9):.2f}")
print("  ^ ratio near 0 = pure noise (nothing to fix); large = systematic bias (fixable)")
