import sqlite3, sys, math, statistics as st; sys.path.insert(0,".")
import wnba_slip as S, wnba_dvp as DVP, wnba_wowy as W
from wnba_tonight import PROP_STATS
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
allr=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
g=[r for r in allr if r.get("result") in ("over","under") and r.get("odds")]
sel,_=S.current_selection([r for r in g if str(r.get("side"))=="over"], commit=False)
uni=[r for r in sel if str(r.get("confidence")) in ("confirmed","likely")]
ps=W.players()
rows=[]
for r in uni:
    opp=r.get("opp"); p=ps.get(r["player"]) or {}
    pos=p.get("position") or p.get("pos")
    k=PROP_STATS.get(r.get("stat"))
    if not (opp and pos and k): continue
    v=DVP.dvp(opp,pos,k)
    rows.append((v,1.0 if r["result"]==r["side"] else 0.0,r,k))
live=[x for x in rows if abs(x[0])>1e-9]
dead=[x for x in rows if abs(x[0])<=1e-9]
print("=== DvP coverage on the selected universe ===")
print("   bets with a LIVE DvP value : %d" % len(live))
print("   bets where DvP returns 0   : %d  -> stats: %s" % (len(dead), sorted({x[3] for x in dead})))
def sc(b,lab):
    if not b: print("   %-30s (none)"%lab); return
    w=sum(1 for x in b if x[1]); u=sum((float(x[2]["odds"])-1.0) if x[1] else -1.0 for x in b)
    print("   %-30s %2d-%-2d hit %5.1f%%  units %+6.2f  ROI %+6.1f%%"%(lab,w,len(b)-w,100*w/len(b),u,100*u/len(b)))
if len(live)>=12:
    xs=[x[0] for x in live]; ys=[x[1] for x in live]
    mx,my=st.mean(xs),st.mean(ys)
    num=sum((a-mx)*(b-my) for a,b in zip(xs,ys)); den=math.sqrt(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))
    print("\n=== does DvP predict the outcome? (n=%d, singles only) ===" % len(live))
    print("   corr(DvP, won) = %+.3f" % (num/den if den else 0))
    med=st.median(xs)
    sc([x for x in live if x[0]>med], "favourable matchup (DvP>med)")
    sc([x for x in live if x[0]<=med],"tough matchup (DvP<=med)")
    # tercile view
    q=sorted(xs); lo,hi=q[len(q)//3], q[2*len(q)//3]
    sc([x for x in live if x[0]>=hi], "softest third")
    sc([x for x in live if x[0]<=lo], "toughest third")
