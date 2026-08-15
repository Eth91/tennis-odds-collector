"""EXP-010 does the ANTI-predictive residual hold FORWARD (out-of-sample)?
EXP-009 used all 84 rows incl. the tuned pre-freeze period. If the model's disagreement with
the book is anti-predictive forward too, the edge is SITUATION SELECTION, not probability."""
import sys, os, sqlite3, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wnba_slip as S
FWD="2026-07-31"
con=sqlite3.connect("file:wnba_ledger.sqlite?mode=ro",uri=True,timeout=30); con.row_factory=sqlite3.Row
rows=[dict(r) for r in con.execute("SELECT * FROM predictions")]
keep,_=S.current_selection(rows)
won=lambda r: 1 if r["result"]==(r["side"] or "over") else 0
def analyse(g,lbl):
    if len(g)<10: print(f"{lbl}: n={len(g)} too thin"); return
    P=[float(r["proj_hit"]) for r in g]; I=[1.0/float(r["odds"]) for r in g]; Y=[won(r) for r in g]
    mi,mp=st.mean(I),st.mean(P)
    den=sum((x-mi)**2 for x in I)
    b=(sum((x-mi)*(y-mp) for x,y in zip(I,P))/den) if den else 0
    res=[p-(mp+b*(i-mi)) for p,i in zip(P,I)]
    med=st.median(res)
    print(f"\n{lbl}  (n={len(g)})")
    for t,sel in (("model BELOW book",lambda i:res[i]<=med),("model ABOVE book",lambda i:res[i]>med)):
        idx=[i for i in range(len(g)) if sel(i)]
        w=sum(Y[i] for i in idx); u=sum((float(g[i]["odds"])-1) if Y[i] else -1 for i in idx)
        print(f"   {t:18s} n={len(idx):3d}  {w}-{len(idx)-w} = {w/len(idx)*100:5.1f}%  "
              f"{u:+7.2f}u  ROI {u/len(idx)*100:+6.1f}%")
    lo=[i for i in range(len(g)) if res[i]<=med]; hi=[i for i in range(len(g)) if res[i]>med]
    gap=(sum(Y[i] for i in hi)/len(hi)-sum(Y[i] for i in lo)/len(lo))*100
    print(f"   ABOVE-minus-BELOW hit%: {gap:+.1f}pp  -> {'ANTI-predictive (holds)' if gap<0 else 'predictive (flips)'}")
g=[r for r in keep if r["result"] in ("over","under") and r.get("proj_hit") is not None]
analyse([r for r in g if r["pred_date"]<FWD],"PRE-FREEZE (in-sample)")
analyse([r for r in g if r["pred_date"]>=FWD],"FORWARD (out-of-sample)")
