import sqlite3, sys, math; sys.path.insert(0,".")
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
rows=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
rows=[r for r in rows if r.get("result") in ("over","under") and r.get("actual") is not None]
print("graded with a realized value: %d\n" % len(rows))

print("=== A. the POINT projection (elev_avg) ===")
er=[r["actual"]-r["elev_avg"] for r in rows if r.get("elev_avg") is not None]
er.sort(); n=len(er)
mean=sum(er)/n; med=er[n//2]
mae=sum(abs(x) for x in er)/n
sd=math.sqrt(sum((x-mean)**2 for x in er)/n)
print("   n=%d  bias %+0.2f (median %+0.2f)  typical miss %.2f  sd %.2f" % (n,mean,med,mae,sd))
print("   realized ABOVE projection: %.1f%%  (50%% = unbiased)" % (100*sum(1 for x in er if x>0)/n))
print("   |miss| <= 2:  %.0f%%   <= 4: %.0f%%   <= 6: %.0f%%" % tuple(
    100*sum(1 for x in er if abs(x)<=k)/n for k in (2,4,6)))

print("\n=== B. proj_hit calibration — when it says X%, does it hit X%? ===")
ph=[r for r in rows if r.get("proj_hit") is not None and (r.get("side") or "over")=="over"]
print("   %-14s %5s %9s %9s" % ("bucket","n","predicted","actual"))
for lo,hi in ((0.0,.60),(.60,.68),(.68,.75),(.75,.82),(.82,1.01)):
    b=[r for r in ph if lo<=r["proj_hit"]<hi]
    if len(b)<4: print("   %-14s %5d  (thin)" % ("%.0f-%.0f%%"%(100*lo,100*hi),len(b))); continue
    pred=sum(r["proj_hit"] for r in b)/len(b)
    act=sum(1 for r in b if r["result"]==r["side"])/len(b)
    print("   %-14s %5d %8.1f%% %8.1f%%   %s" % ("%.0f-%.0f%%"%(100*lo,100*hi),len(b),100*pred,100*act,
          "OVERCONFIDENT" if act<pred-.05 else ("under" if act>pred+.05 else "ok")))
# rank correlation: does a higher proj_hit actually win more?
import statistics
xs=[r["proj_hit"] for r in ph]; ys=[1.0 if r["result"]==r["side"] else 0.0 for r in ph]
mx,my=sum(xs)/len(xs),sum(ys)/len(ys)
num=sum((a-mx)*(b-my) for a,b in zip(xs,ys))
den=math.sqrt(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))
print("   corr(proj_hit, actually won) = %+.3f   <- 0 or negative means it carries no ranking info" % (num/den if den else 0))
