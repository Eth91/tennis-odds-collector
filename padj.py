import sqlite3, math, statistics as st, sys; sys.path.insert(0,".")
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
R=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
R=[r for r in R if r.get("result") in ("over","under") and r.get("ev") is not None
   and r.get("odds") and r.get("proj_hit") is not None and (r.get("side") or "over")=="over"]
for r in R: r["p_adj"]=(float(r["ev"])+1.0)/float(r["odds"])
print("=== proj_hit (stored, RAW) vs p_adj (what EV is actually built from) — n=%d ===" % len(R))
for field in ("proj_hit","p_adj"):
    print("\n  --- %s ---" % field)
    print("    %-12s %5s %9s %9s" % ("bucket","n","predicted","actual"))
    for lo,hi in ((0,.55),(.55,.62),(.62,.70),(.70,.80),(.80,1.01)):
        b=[r for r in R if lo<=r[field]<hi]
        if len(b)<5: continue
        pr=sum(r[field] for r in b)/len(b); ac=sum(1 for r in b if r["result"]==r["side"])/len(b)
        print("    %-12s %5d %8.1f%% %8.1f%%  %s" % ("%.0f-%.0f%%"%(100*lo,100*hi),len(b),100*pr,100*ac,
              "over" if ac<pr-.05 else ("under" if ac>pr+.05 else "OK")))
    xs=[r[field] for r in R]; ys=[1.0 if r["result"]==r["side"] else 0.0 for r in R]
    mx,my=sum(xs)/len(xs),sum(ys)/len(ys)
    num=sum((a-mx)*(b-my) for a,b in zip(xs,ys))
    den=math.sqrt(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))
    print("    mean predicted %.3f vs actual %.3f   corr=%+.3f" % (mx,my,num/den if den else 0))
