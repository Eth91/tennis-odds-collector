"""EXP-009 does p_adj carry information BEYOND the market price?
If the model's probability is just the book's price wearing a hat, the ranking failure is
fundamental and no recalibration fixes it. Test: rank-corr of p_adj vs outcome, of implied vs
outcome, and of p_adj RESIDUALISED on implied (the part that is genuinely the model's own)."""
import sys, os, sqlite3, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wnba_slip as S
con=sqlite3.connect("file:wnba_ledger.sqlite?mode=ro",uri=True,timeout=30); con.row_factory=sqlite3.Row
rows=[dict(r) for r in con.execute("SELECT * FROM predictions")]
keep,_=S.current_selection(rows)
g=[r for r in keep if r["result"] in ("over","under") and r.get("proj_hit") is not None]
won=lambda r: 1 if r["result"]==(r["side"] or "over") else 0
P=[float(r["proj_hit"]) for r in g]; I=[1.0/float(r["odds"]) for r in g]; Y=[won(r) for r in g]
n=len(g); print(f"n={n}\n")
def rk(a):
    idx=sorted(range(len(a)),key=lambda i:a[i]); r=[0.0]*len(a); i=0
    while i<len(a):
        j=i
        while j+1<len(a) and a[idx[j+1]]==a[idx[i]]: j+=1
        for k in range(i,j+1): r[idx[k]]=(i+j)/2+1
        i=j+1
    return r
def corr(a,b):
    ma,mb=st.mean(a),st.mean(b)
    num=sum((x-ma)*(y-mb) for x,y in zip(a,b))
    d=(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))**0.5
    return num/d if d else 0.0
print(f"  rank-corr(p_adj, win)   = {corr(rk(P),rk(Y)):+.3f}")
print(f"  rank-corr(implied, win) = {corr(rk(I),rk(Y)):+.3f}")
print(f"  corr(p_adj, implied)    = {corr(P,I):+.3f}   <- how much of p_adj IS the price")
# residualise p_adj on implied via OLS, then correlate the residual with the outcome
mi,mp=st.mean(I),st.mean(P)
b=sum((x-mi)*(y-mp) for x,y in zip(I,P))/sum((x-mi)**2 for x in I)
res=[p-(mp+b*(i-mi)) for p,i in zip(P,I)]
print(f"  rank-corr(p_adj RESIDUAL, win) = {corr(rk(res),rk(Y)):+.3f}   <- the model's OWN part")
print("\n=== split by the residual: is the model's own disagreement with the book worth anything? ===")
med=st.median(res)
for lbl,sel in (("model BELOW book", lambda i: res[i]<=med), ("model ABOVE book", lambda i: res[i]>med)):
    idx=[i for i in range(n) if sel(i)]
    w=sum(Y[i] for i in idx); u=sum((float(g[i]["odds"])-1) if Y[i] else -1 for i in idx)
    print(f"  {lbl:18s} n={len(idx):3d}  {w}-{len(idx)-w} = {w/len(idx)*100:5.1f}%  "
          f"{u:+7.2f}u  ROI {u/len(idx)*100:+6.1f}%")
print("\n  VERDICT: " + ("p_adj adds ranking info beyond price"
      if abs(corr(rk(res),rk(Y)))>0.15 else
      "p_adj adds NO ranking info beyond price -- recalibration cannot fix the ranking"))
