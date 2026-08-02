"""Is 'DvP into the bet probability' backtestable, and does it help? Yes, and no.

Today DvP only shifts elev_avg, which picks the SIDE. Wiring it into the probability means moving
`hit` itself by the matchup. The cleanest form: shift every elevated-game value by the matchup
nudge before counting how many clear the line — i.e. re-ask "how often would she have cleared this
line against THIS defence", which is exactly what the feature claims to know.

Backtestable because everything needed is stored: the elevated sample is reconstructible from the
game log, and line/odds/actual are in the ledger. Judged on the post-selection universe in UNITS.
"""
import sqlite3, sys, math, statistics as st; sys.path.insert(0,".")
import wnba_slip as S, wnba_dvp as DVP, wnba_wowy as W
from wnba_tonight import PROP_STATS
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
allr=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
g=[r for r in allr if r.get("result") in ("over","under") and r.get("odds")]
sel,_=S.current_selection([r for r in g if str(r.get("side"))=="over"], commit=False)
uni=[r for r in sel if str(r.get("confidence")) in ("confirmed","likely")
     and r.get("proj_hit") is not None and r.get("n_elev") and r.get("proj_min")]
ps=W.players()
def u(rows): return sum((float(r["odds"])-1.0) if r["result"]==r["side"] else -1.0 for r in rows)
def sc(rows,lab):
    if not rows: print("  %-40s (none)"%lab); return
    w=sum(1 for r in rows if r["result"]==r["side"])
    print("  %-40s %2d-%-2d hit %5.1f%%  units %+6.2f  ROI %+6.1f%%"%(lab,w,len(rows)-w,100*w/len(rows),u(rows),100*u(rows)/len(rows)))
print("universe: %d\n" % len(uni))
sc(uni,"  baseline (DvP side-only, as shipped)")
# variant: move the probability by the matchup, then re-run the EV bar
for scale in (1.0, 2.0):
    kept=[]
    for r in uni:
        p=ps.get(r["player"]) or {}
        pos=p.get("position") or p.get("pos"); k=PROP_STATS.get(r["stat"])
        d=DVP.dvp(r["opp"],pos,k) if (r.get("opp") and pos and k) else 0.0
        nudge=d*float(r["proj_min"])*scale
        # shifting every sample value by `nudge` is equivalent to shifting the LINE the other way
        n=float(r["n_elev"]); hit=float(r["proj_hit"]); dec=float(r["odds"])
        # approximate the re-count: a nudge of x points moves the empirical hit by x/sd of the sample
        sd=max(float(r.get("vol") and 0 or 0) or 6.5, 1.0)
        newhit=min(max(hit + nudge/sd*0.4, 0.02), 0.98)
        padj=(newhit*n + (1.0/dec)*11)/(n+11)
        if padj*dec-1.0 >= 0.10: kept.append(r)
    sc(kept, "  DvP in probability (x%.0f)" % scale)
