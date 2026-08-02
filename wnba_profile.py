"""Judge tonight's two plays against the graded record, on the features that separate them.

Both are POR, points, volume-basis, n_without=2, same out player. The ONLY thing that differs is
role expansion:
    Carleton  d_min +0.3  d_fga +0.8   -> the 0-3 "some bump" zone
    DiLeo     d_min +4.2  d_fga +3.1   -> the 3-8 core band

So the question "is one better" reduces to: what has the 0-3 zone done versus the 3-8 band, on the
record as the board now counts it (role-gated, n1 excluded)?

Measured on the CURRENT universe, not the old one, and with the day-clustered interval — bets inside
a slate share conditions.
"""
import random, sqlite3
from collections import defaultdict
import wnba_slip as SL

BET_ROLES={"confirmed","likely"}
con=sqlite3.connect("wnba_ledger.sqlite")
cols=[d[1] for d in con.execute("PRAGMA table_info(predictions)")]
g=[dict(zip(cols,r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()
overs=[r for r in g if r["result"] in ("over","under") and (r["side"] or "over")=="over"
       and (r.get("tier") or "firm")!="n1"]
dec,_=SL.current_selection(overs)
U=[r for r in dec if str(r.get("confidence")) in BET_ROLES or r.get("played")]

def ret(r): return (float(r.get("odds") or 0)-1) if r["result"]==(r["side"] or "over") else -1.0
def boot(rows,iters=2000):
    byd=defaultdict(list)
    for r in rows: byd[str(r.get("pred_date"))[:10]].append(ret(r))
    ks=list(byd)
    if len(ks)<2: return None
    rng=random.Random(7); s=[]
    for _ in range(iters):
        v=[x for k in rng.choices(ks,k=len(ks)) for x in byd[k]]
        if v: s.append(sum(v)/len(v))
    s.sort(); return s[int(.025*len(s))],s[int(.975*len(s))]
def show(lab,rows):
    n=len(rows)
    if not n: print("  %-38s (none)"%lab); return
    w=sum(1 for r in rows if r["result"]==(r["side"] or "over")); u=sum(ret(r) for r in rows)
    ci=boot(rows)
    print("  %-38s %3d %2d-%-2d %6.1f%% %+7.2fu %+7.1f%%  %s"%(lab,n,w,n-w,100*w/n,u,100*u/n,
        ("CI %+.0f%%..%+.0f%%"%(100*ci[0],100*ci[1])) if ci else "CI n/a"))

print("  universe = the board's record as it now counts it: %d bets"%len(U))
print("  %-38s %3s %6s %7s %8s %8s"%("bucket","n","record","hit%","units","ROI"))
def band(r):
    d=r.get("d_min")
    if d is None: return "d_min missing"
    if d<0: return "d_min <0"
    if d<3: return "d_min 0-3   <- CARLETON"
    if d<=8: return "d_min 3-8   <- DILEO"
    return "d_min >8"
byb=defaultdict(list)
for r in U: byb[band(r)].append(r)
for k in ("d_min <0","d_min 0-3   <- CARLETON","d_min 3-8   <- DILEO","d_min >8","d_min missing"):
    if k in byb: show(k,byb[k])

print("\n  === POINTS only (both tonight's plays are points) ===")
P=[r for r in U if r.get("stat")=="points"]
byp=defaultdict(list)
for r in P: byp[band(r)].append(r)
for k in ("d_min <0","d_min 0-3   <- CARLETON","d_min 3-8   <- DILEO","d_min >8"):
    if k in byp: show(k,byp[k])

print("\n  === tightest comparable: points AND n_elev-style volume basis ===")
V=[r for r in P if str(r.get("basis"))=="volume"]
show("volume points, ALL bands",V)
for k in ("d_min 0-3   <- CARLETON","d_min 3-8   <- DILEO"):
    show("volume points, "+k,[r for r in V if band(r)==k])

print("\n  === the usage bar the model itself uses (d_fga > 1) ===")
show("d_fga > 1",[r for r in U if (r.get("d_fga") or 0)>1])
show("d_fga <= 1  <- CARLETON (+0.8)",[r for r in U if (r.get("d_fga") or 0)<=1])
