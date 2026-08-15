"""EXP-008 does `vac` rank inside the SUPPRESSED pool?
Volume is the #1 constraint. If vac ranks among bets the gate DROPPED, high-vac suppressed
bets may be recoverable -- growing sample without lowering EV thresholds (which EXP/R3 already
rejected). Falsifier: if suppressed high-vac performs no better than suppressed low-vac,
vac is a property of the KEPT population only and cannot expand volume."""
import sys, os, sqlite3, statistics as st, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wnba_slip as S
con=sqlite3.connect("file:wnba_ledger.sqlite?mode=ro",uri=True,timeout=30); con.row_factory=sqlite3.Row
rows=[dict(r) for r in con.execute("SELECT * FROM predictions")]
keep,_=S.current_selection(rows)
kk={(r["pred_date"],r["player"],r["stat"],r["line"]) for r in keep}
sup=[r for r in rows if (r["pred_date"],r["player"],r["stat"],r["line"]) not in kk]
won=lambda r: r["result"]==(r["side"] or "over")
def rec(s,l):
    s=[r for r in s if r["result"] in ("over","under")]
    if not s: print(f"  {l:32s} n=0"); return None
    w=sum(1 for r in s if won(r)); u=sum((float(r["odds"])-1)if won(r)else -1 for r in s)
    print(f"  {l:32s} n={len(s):3d}  {w}-{len(s)-w} = {w/len(s)*100:5.1f}%  {u:+7.2f}u  ROI {u/len(s)*100:+6.1f}%")
    return w/len(s)
VMED=14.7
print("=== SUPPRESSED pool, split by the SAME frozen vac threshold ===")
sv=[r for r in sup if r.get("vac") is not None and r["result"] in ("over","under")]
print(f"  suppressed rows carrying vac: {len(sv)}")
a=rec([r for r in sv if float(r["vac"])<=VMED],"suppressed, vac <= 14.7")
b=rec([r for r in sv if float(r["vac"])>VMED],"suppressed, vac > 14.7")
if a is not None and b is not None:
    lo=[r for r in sv if float(r["vac"])<=VMED]; hi=[r for r in sv if float(r["vac"])>VMED]
    pp=(sum(1 for r in lo if won(r))+sum(1 for r in hi if won(r)))/(len(lo)+len(hi))
    se=math.sqrt(pp*(1-pp)*(1/len(lo)+1/len(hi))) if 0<pp<1 else 0
    z=(b-a)/se if se else 0
    print(f"\n  gap {(b-a)*100:+.1f}pp, z={z:.2f}")
    print("  -> " + ("vac ALSO ranks the suppressed pool: recoverable volume" if (b-a)>0.08
          else "vac does NOT rank suppressed bets -- it is a property of the KEPT population"))
print("\n=== for reference: what the gate itself did ===")
rec(keep,"TRACKED"); rec(sup,"SUPPRESSED")
print("\n=== would high-vac SUPPRESSED bets have been profitable? ===")
rec([r for r in sv if float(r["vac"])>VMED],"the candidate recovery cell")
