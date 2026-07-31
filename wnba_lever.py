"""On the BOARD'S OWN universe, what would each candidate gate do to the headline?

Answers "could it be better" in the only currency that matters: the record the board reports,
recomputed with one rule added at a time. Reported with a day-clustered interval, and with the
number of bets it costs — a gate that lifts hit rate by cutting volume is a trade, not a free win.
"""
import random, sqlite3
from collections import defaultdict
import wnba_slip as SL, wnba_wowy as W

BET_ROLES={"confirmed","likely"}
con=sqlite3.connect("wnba_ledger.sqlite")
cols=[d[1] for d in con.execute("PRAGMA table_info(predictions)")]
g=[dict(zip(cols,r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()
overs=[r for r in g if r["result"] in ("over","under") and (r["side"] or "over")=="over"
       and (r.get("tier") or "firm")!="n1"]
dec,_=SL.current_selection(overs)

ids=W.roster_ids() or {}
_c={}
def lg(n):
    if n not in _c:
        p=ids.get(n)
        try:_c[n]=W.game_log(p) if p else []
        except Exception:_c[n]=[]
    return _c[n]
def nw(r):
    d=str(r.get("pred_date"))[:10]
    bl=[x for x in lg(r.get("player")) if (x.get("date") or "")[:10]<d]
    outs=[x.strip() for x in str(r.get("out_player") or "").split(",") if x.strip()]
    ol=[[x for x in lg(o) if (x.get("date") or "")[:10]<d] for o in outs]
    ol=[o for o in ol if o]
    if not bl or not ol: return None
    try: return (W.wowy_multi(bl,ol) if len(ol)>1 else W.wowy(bl,ol[0])).get("n_without")
    except Exception: return None
for r in dec: r["_nw"]=nw(r)

def ret(r): return (float(r.get("odds") or 0)-1) if r["result"]==(r["side"] or "over") else -1.0
def boot(rows,iters=2000):
    byd=defaultdict(list)
    for r in rows: byd[str(r.get("pred_date"))[:10]].append(ret(r))
    ks=list(byd)
    if len(ks)<2: return None
    rng=random.Random(7); s2=[]
    for _ in range(iters):
        s=[x for k in rng.choices(ks,k=len(ks)) for x in byd[k]]
        if s: s2.append(sum(s)/len(s))
    s2.sort(); return s2[int(.025*len(s2))],s2[int(.975*len(s2))]
def show(lab,rows,base=None):
    n=len(rows)
    if not n: print("  %-40s (none)"%lab); return
    w=sum(1 for r in rows if r["result"]==(r["side"] or "over")); u=sum(ret(r) for r in rows)
    ci=boot(rows)
    d="" if base is None else "  (%+d bets, %+.2fu)"%(n-base[0],u-base[1])
    print("  %-40s %3d %2d-%-2d %6.1f%% %+7.2fu %+7.1f%%  %s%s"%(lab,n,w,n-w,100*w/n,u,100*u/n,
        ("CI %+.0f%%..%+.0f%%"%(100*ci[0],100*ci[1])) if ci else "CI n/a",d))
    return (n,u)

print("  %-40s %3s %6s %7s %8s %8s"%("variant","n","record","hit%","units","ROI"))
base=show("BOARD TODAY (no role gate)",dec)
role=[r for r in dec if str(r.get("confidence")) in BET_ROLES]
show("+ role gate (what the bot bets)",role,base)
show("+ role gate + drop n>=3",[r for r in role if (r.get("_nw") or 0)<3],base)
show("+ drop n>=3 only",[r for r in dec if (r.get("_nw") or 0)<3],base)
print()
show("  for reference: n>=3 alone",[r for r in dec if (r.get("_nw") or 0)>=3])
show("  for reference: n<=2 alone",[r for r in dec if r.get("_nw") is not None and r["_nw"]<3])
print("\n  A gate that lifts hit% by cutting most of the volume is a trade. The bets column is")
print("  the price; on TT that price is the thing that matters most, on WNBA volume is cheaper.")
