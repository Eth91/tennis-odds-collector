"""EXP-007 ECONOMIC SIZE of a vac gate + honest multiple-testing correction.
IN-SAMPLE by construction (the threshold comes from this data) -- reported as an effect size,
NOT as an expected return."""
import sys, os, sqlite3, statistics as st, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wnba_slip as S
FWD="2026-07-31"
con=sqlite3.connect("file:wnba_ledger.sqlite?mode=ro",uri=True,timeout=30); con.row_factory=sqlite3.Row
rows=[dict(r) for r in con.execute("SELECT * FROM predictions")]
keep,_=S.current_selection(rows)
g=[r for r in keep if r["result"] in ("over","under")]
won=lambda r: r["result"]==(r["side"] or "over")
def rec(s,l):
    if not s: print(f"  {l:34s} n=0"); return 0.0
    w=sum(1 for r in s if won(r)); u=sum((float(r["odds"])-1)if won(r)else -1 for r in s)
    print(f"  {l:34s} n={len(s):3d}  {w}-{len(s)-w} = {w/len(s)*100:5.1f}%  {u:+7.2f}u  ROI {u/len(s)*100:+6.1f}%")
    return u
hasv=[r for r in g if r.get("vac") is not None]
VMED=st.median([float(r["vac"]) for r in hasv])
print(f"vac median = {VMED:.1f}   ({len(hasv)} of {len(g)} rows carry vac)\n")
print("=== ALL TRACKED (in-sample effect size) ===")
base=rec(g,"v1.8 as-is")
kept=rec([r for r in g if r.get("vac") is None or float(r["vac"])>VMED],"with vac<=median DROPPED")
drop=rec([r for r in g if r.get("vac") is not None and float(r["vac"])<=VMED],"  (the dropped cell)")
print(f"  delta: {kept-base:+.2f}u\n")
print("=== FORWARD ONLY ===")
fg=[r for r in g if r["pred_date"]>=FWD]
fb=rec(fg,"v1.8 forward")
fk=rec([r for r in fg if r.get("vac") is None or float(r["vac"])>VMED],"forward, vac<=median DROPPED")
rec([r for r in fg if r.get("vac") is not None and float(r["vac"])<=VMED],"  (the dropped cell)")
print(f"  delta: {fk-fb:+.2f}u")
print("\n=== MULTIPLE-TESTING CORRECTION ===")
n=len(hasv); lo=[r for r in hasv if float(r["vac"])<=VMED]; hi=[r for r in hasv if float(r["vac"])>VMED]
p1=sum(1 for r in lo if won(r))/len(lo); p2=sum(1 for r in hi if won(r))/len(hi)
pp=(sum(1 for r in lo if won(r))+sum(1 for r in hi if won(r)))/n
se=math.sqrt(pp*(1-pp)*(1/len(lo)+1/len(hi)))
z=(p2-p1)/se if se else 0
print(f"  two-proportion z = {z:.2f} (gap {(p2-p1)*100:+.1f}pp, n={len(lo)}/{len(hi)})")
print(f"  15 fields were screened -> Bonferroni alpha = 0.05/15 = 0.0033, |z| needed ~2.94")
print(f"  -> {'SURVIVES Bonferroni' if abs(z)>2.94 else 'does NOT survive Bonferroni on this n'}")
