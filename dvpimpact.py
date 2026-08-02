import sqlite3, sys; sys.path.insert(0,".")
import wnba_slip as S, wnba_dvp as DVP, wnba_wowy as W
from wnba_tonight import PROP_STATS
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
allr=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
g=[r for r in allr if r.get("result") in ("over","under") and r.get("odds")]
sel,_=S.current_selection([r for r in g if str(r.get("side"))=="over"], commit=False)
uni=[r for r in sel if str(r.get("confidence")) in ("confirmed","likely")]
ps=W.players()
COMBO={"pra","pts_ast","pts_reb","reb_ast"}
combo=[r for r in uni if r.get("stat") in COMBO]
print("=== impact of the combo DvP fix on the selected universe ===")
print("   combo bets affected: %d of %d" % (len(combo), len(uni)))
flip=0; shown=0
for r in combo:
    p=ps.get(r["player"]) or {}; pos=p.get("position") or p.get("pos"); opp=r.get("opp")
    k=PROP_STATS.get(r["stat"])
    if not (pos and opp and k): continue
    d=DVP.dvp(opp,pos,k); pm=float(r.get("proj_min") or 30)
    nudge=d*pm; ea=float(r.get("elev_avg") or 0); ln=float(r["line"])
    gap=ea-ln
    would_flip = (gap>=0) != ((gap+nudge)>=0)
    if would_flip: flip+=1
    if shown<8:
        print("   %-18s %-8s line %-5s elev %-6s gap %+6.2f  dvp %+0.4f/min -> %+5.2f  %s"
              % (r["player"][:18],r["stat"],ln,ea,gap,d,nudge,"SIDE FLIPS" if would_flip else ""))
        shown+=1
print("\n   bets whose SIDE would flip: %d of %d  (DvP only decides side; it never moves EV)" % (flip,len(combo)))
print("\n=== tonight's Mabrey ===")
import datetime as dt
for r in c.execute("SELECT * FROM predictions WHERE pred_date>=? AND player='Marina Mabrey'",(dt.date.today().isoformat(),)):
    r=dict(r); pos=(ps.get("Marina Mabrey") or {}).get("position") or (ps.get("Marina Mabrey") or {}).get("pos")
    d=DVP.dvp(r["opp"],pos,PROP_STATS.get(r["stat"]))
    pm=float(r.get("proj_min") or 30)
    print("   %-8s o%-6s elev %-6s -> %.2f after DvP (%+0.2f)  side stays %s"
          % (r["stat"],r["line"],r["elev_avg"],float(r["elev_avg"])+d*pm,d*pm,
             "over" if float(r["elev_avg"])+d*pm>=float(r["line"]) else "UNDER"))
