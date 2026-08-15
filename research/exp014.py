"""EXP-014 SITUATION -> CLV. Target is MARKET-RELATIVE, not win/loss.
clv_line = close_line - flag_line; positive = the market moved toward our OVER, i.e. we were
early on real information. 891 rows vs 85 graded bets = ~10x the power.
No p_adj/proj_hit anywhere as a selector. `proj` is used ONLY as a control to prove
independence."""
import sys, os, sqlite3, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT * FROM clv WHERE close_line IS NOT NULL AND flag_line IS NOT NULL")]
for r in rows:
    r["clv"] = float(r["close_line"]) - float(r["flag_line"])
    r["ncascade"] = len([x for x in (r["out_player"] or "").split(",") if x.strip()])
    try: r["hour"] = int(str(r["flagged_at"])[11:13])
    except Exception: r["hour"] = None
n = len(rows)
allclv = [r["clv"] for r in rows]
print(f"n={n}   mean CLV_line = {st.mean(allclv):+.3f}   median {st.median(allclv):+.2f}   "
      f"pos {sum(1 for x in allclv if x>0)/n*100:.1f}% / neg {sum(1 for x in allclv if x<0)/n*100:.1f}%\n")

def grp(key, label, minn=25):
    print(f"-- {label} --")
    buckets = {}
    for r in rows:
        k = key(r)
        if k is None: continue
        buckets.setdefault(k, []).append(r["clv"])
    for k in sorted(buckets, key=lambda x: str(x)):
        v = buckets[k]
        if len(v) < minn: continue
        se = st.pstdev(v)/len(v)**0.5 if len(v)>1 else 0
        print(f"   {str(k):16s} n={len(v):4d}  mean CLV {st.mean(v):+.3f} +/- {se:.3f}  "
              f"pos {sum(1 for x in v if x>0)/len(v)*100:5.1f}%")
    print()

grp(lambda r: r["ncascade"], "CASCADE COMPLEXITY (number of players out)")
grp(lambda r: r["stat"], "MARKET")
grp(lambda r: r["tier"], "TIER")
grp(lambda r: "early <12h UTC" if (r["hour"] is not None and r["hour"] < 12) else
             ("late >=12h UTC" if r["hour"] is not None else None), "FLAG HOUR (proxy for lead time)")
print("-- INDEPENDENCE CHECK: is CLV explained by the projection itself? --")
pv = [(float(r["proj"]), r["clv"]) for r in rows if r.get("proj") is not None]
mp, mc = st.mean([x[0] for x in pv]), st.mean([x[1] for x in pv])
num = sum((a-mp)*(b-mc) for a, b in pv)
den = (sum((a-mp)**2 for a, _ in pv)*sum((b-mc)**2 for _, b in pv))**0.5
print(f"   corr(proj, clv) = {num/den:+.3f} over n={len(pv)}")
print("   -> " + ("projection explains CLV; situation effects must be residualised"
      if abs(num/den) > 0.2 else "projection barely explains CLV; situation effects stand alone"))
