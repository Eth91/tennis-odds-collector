"""EXP-011 OPTIMAL SHRINK k, temporally split.
EXP-009/010: the model's probability net of price is ANTI-predictive => shrinking HARDER toward
the book should help. p_adj = (hit*n + implied*k)/(n+k) is invertible, so recover raw hit and
re-shrink at any k. Fit k on PRE-FREEZE, report FORWARD. Never pick k on the forward data."""
import sys, os, sqlite3, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wnba_slip as S
FWD="2026-07-31"
con=sqlite3.connect("file:wnba_ledger.sqlite?mode=ro",uri=True,timeout=30); con.row_factory=sqlite3.Row
rows=[dict(r) for r in con.execute("SELECT * FROM predictions")]
keep,_=S.current_selection(rows)
won=lambda r: r["result"]==(r["side"] or "over")
g=[r for r in keep if r["result"] in ("over","under") and r.get("proj_hit") is not None
   and r.get("n_elev") and float(r["n_elev"])>0]
def raw_hit(r):
    k0 = 14.0 if str(r.get("basis"))=="projected" else 11.0
    n=float(r["n_elev"]); p=float(r["proj_hit"]); imp=1.0/float(r["odds"])
    return (p*(n+k0)-imp*k0)/n, n, imp, k0
print(f"n={len(g)} rows invertible\n")
print(f"{'k':>5s} {'PRE bets':>9s} {'PRE units':>10s} {'FWD bets':>9s} {'FWD units':>10s} {'FWD ROI':>8s}")
print("-"*58)
best=None
for k in (0,5,11,20,35,60,120,1e9):
    outp={}
    for lbl,rs in (("pre",[r for r in g if r["pred_date"]<FWD]),("fwd",[r for r in g if r["pred_date"]>=FWD])):
        bets=[]
        for r in rs:
            h,n,imp,_=raw_hit(r)
            p=(h*n+imp*k)/(n+k) if (n+k)>0 else imp
            dec=float(r["odds"]); ev=p*dec-1
            thr=0.20 if (r.get("odds_other") in (None,0,0.0)) else 0.10
            if ev>=thr: bets.append(r)
        u=sum((float(r["odds"])-1) if won(r) else -1 for r in bets)
        outp[lbl]=(len(bets),u)
    pb,pu=outp["pre"]; fb,fu=outp["fwd"]
    roi=(fu/fb*100) if fb else 0
    kl="inf" if k>1e8 else f"{k:g}"
    print(f"{kl:>5s} {pb:9d} {pu:+10.2f} {fb:9d} {fu:+10.2f} {roi:+7.1f}%")
    if best is None or pu>best[1]: best=(k,pu,fb,fu,roi)
kl="inf" if best[0]>1e8 else f"{best[0]:g}"
print(f"\n  k chosen on PRE-FREEZE only: k={kl} (pre {best[1]:+.2f}u)")
print(f"  -> its FORWARD result: {best[2]} bets, {best[3]:+.2f}u, ROI {best[4]:+.1f}%")
print(f"  (live k=11 forward is the row above for comparison)")
