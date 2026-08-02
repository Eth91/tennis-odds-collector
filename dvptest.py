import sqlite3, sys, math, statistics as st; sys.path.insert(0,".")
import wnba_slip as S
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
allr=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
g=[r for r in allr if r.get("result") in ("over","under") and r.get("odds")]
sel,_=S.current_selection([r for r in g if str(r.get("side"))=="over"], commit=False)
uni=[r for r in sel if str(r.get("confidence")) in ("confirmed","likely")]
print("=== TIER records on the selected universe (n=%d) ===" % len(uni))
favs=S.fav_keys([r for r in g if (r.get("side") or "over")=="over"])
from collections import defaultdict
byt=defaultdict(list)
for r in uni: byt[S.tier_of(r,(r["pred_date"],r["player"],r["stat"]) in favs)].append(r)
for t in ("A","B","C"):
    b=byt.get(t,[])
    if not b: print("   %s: none" % t); continue
    w=sum(1 for r in b if r["result"]==r["side"])
    u=sum((float(r["odds"])-1.0) if r["result"]==r["side"] else -1.0 for r in b)
    print("   TIER %s: %2d-%-2d  hit %5.1f%%  units %+6.2f  ROI %+6.1f%%" % (t,w,len(b)-w,100*w/len(b),u,100*u/len(b)))

print("\n=== DVP: does the opponent's position-defence actually predict the outcome? ===")
try:
    import wnba_dvp as DVP
except Exception as e:
    print("   no dvp module:", e); raise SystemExit
import wnba_wowy as W
ps=W.players()
vals=[]
for r in uni:
    opp=r.get("opp"); pos=(ps.get(r["player"]) or {}).get("position") or (ps.get(r["player"]) or {}).get("pos")
    stat=r.get("stat")
    if not opp or not pos: continue
    try: d=DVP.dvp(opp,pos,stat)
    except Exception: continue
    if d is None: continue
    vals.append((d, 1.0 if r["result"]==r["side"] else 0.0, r))
print("   bets with a DvP value: %d of %d" % (len(vals), len(uni)))
if len(vals)>=12:
    xs=[v[0] for v in vals]; ys=[v[1] for v in vals]
    mx,my=st.mean(xs),st.mean(ys)
    num=sum((a-mx)*(b-my) for a,b in zip(xs,ys)); den=math.sqrt(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))
    print("   corr(DvP, won) = %+.3f" % (num/den if den else 0))
    med=st.median(xs)
    for lab,sub in (("favourable half (DvP high)",[v for v in vals if v[0]>med]),
                    ("tough half (DvP low)",[v for v in vals if v[0]<=med])):
        w=sum(1 for v in sub if v[1]); u=sum((float(v[2]["odds"])-1.0) if v[1] else -1.0 for v in sub)
        print("   %-28s %2d-%-2d hit %5.1f%%  units %+6.2f" % (lab,w,len(sub)-w,100*w/len(sub),u))
