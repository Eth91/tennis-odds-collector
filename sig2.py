import sys, random, statistics as st; sys.path.insert(0,".")
exec(open("variant_bt.py").read().split('if __name__')[0])
import sqlite3
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
allrows=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
g=[r for r in allrows if r.get("result") in ("over","under") and r.get("odds")]
import wnba_slip as S
sel,_=S.current_selection([r for r in g if str(r.get("side"))=="over"], commit=False)
uni=[r for r in sel if str(r.get("confidence")) in ("confirmed","likely") and r.get("actual") is not None
     and r.get("elev_avg") is not None and r.get("season_avg") and r.get("line") is not None]
ps=W.players(); cache={}
def psig(r):
    k=(r["player"],r["stat"],str(r["pred_date"])[:10])
    if k in cache: return cache[k]
    out=None; key=STATKEY.get(r["stat"])
    if key and r["player"] in ps:
        try:
            lg=[x for x in W.game_log(ps[r["player"]]["id"]) if str(x.get("date"))[:10]<k[2] and (x.get("min") or 0)>0]
            v=[x.get(key) or 0 for x in lg]
            if len(v)>=6: out=st.pstdev(v)
        except Exception: out=None
    cache[k]=out; return out
def isig(r):
    p=min(max(r.get("proj_hit") or .5,.02),.98); z=_ppf(p)
    return abs((r["elev_avg"]-r["line"])/z) if abs(z)>1e-6 else 4.0
def u(rows): return sum((float(r["odds"])-1.0) if r["result"]==r["side"] else -1.0 for r in rows)
keep=[r for r in uni if p_over(r["elev_avg"], psig(r) or isig(r)*1.8, float(r["line"]))*float(r["odds"])-1.0>=OVER_EV_MIN]
print("=== per-player sigma vs baseline, day-clustered bootstrap ===")
print("   baseline %d bets %+.2fu   |   variant %d bets %+.2fu   |   diff %+.2fu"
      % (len(uni), u(uni), len(keep), u(keep), u(keep)-u(uni)))
from collections import defaultdict
days=defaultdict(lambda:([],[]))
kid={id(r) for r in keep}
for r in uni:
    d=str(r["pred_date"])[:10]; days[d][0].append(r)
    if id(r) in kid: days[d][1].append(r)
ks=list(days); random.seed(5); diffs=[]
for _ in range(4000):
    s=[days[random.choice(ks)] for _ in ks]
    B=[x for d in s for x in d[0]]; V=[x for d in s for x in d[1]]
    if B and V: diffs.append(u(V)-u(B))
diffs.sort()
print("   95%% CI on the unit difference: [%+.2f, %+.2f]  over %d slates" % (diffs[100], diffs[3900], len(ks)))
print("   -> %s" % ("variant significantly better" if diffs[100]>0 else
                    "indistinguishable — not enough to justify changing a working model"))
