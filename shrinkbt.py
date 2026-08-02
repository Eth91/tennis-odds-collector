import sqlite3, sys, random, statistics as st; sys.path.insert(0,".")
import wnba_slip as S
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
allr=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
g=[r for r in allr if r.get("result") in ("over","under") and r.get("odds")]
sel,_=S.current_selection([r for r in g if str(r.get("side"))=="over"], commit=False)
uni=[r for r in sel if str(r.get("confidence")) in ("confirmed","likely")
     and r.get("ev") is not None and r.get("proj_hit") is not None and r.get("n_elev")]
print("selected universe: %d\n" % len(uni))
def u(rows): return sum((float(r["odds"])-1.0) if r["result"]==r["side"] else -1.0 for r in rows)
def rec(rows):
    w=sum(1 for r in rows if r["result"]==r["side"]); return w, len(rows)-w
# recover the shrink actually used, then re-run the EV bar at other k values
import re
K0=None
for ln in open("wnba_tonight.py"):
    m=re.search(r"shrink_k\s*=\s*([0-9.]+)", ln)
    if m: K0=float(m.group(1)); break
print("current shrink_k in source: %s\n" % K0)
print("  %-18s %8s %6s %9s %8s" % ("shrink_k","bets","W-L","units","ROI"))
for k in (K0 or 4, 6, 8, 12, 16, 24):
    kept=[]
    for r in uni:
        n=float(r["n_elev"] or 1); hit=float(r["proj_hit"]); dec=float(r["odds"])
        p=(hit*n + (1.0/dec)*k)/(n+k)
        if p*dec-1.0 >= 0.10: kept.append(r)
    if not kept: print("  %-18s %8d" % (k,0)); continue
    w,l=rec(kept)
    print("  %-18s %8d %3d-%-3d %+8.2f %+7.1f%%" % (("%.0f%s"%(k," (current)" if k==K0 else "")),len(kept),w,l,u(kept),100*u(kept)/len(kept)))
