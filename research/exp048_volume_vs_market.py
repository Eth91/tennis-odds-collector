"""Are "volume loses" and "non-points wins" the SAME finding? Every forward volume bet is a
points bet, so the two could be one effect seen twice. Cross-tabulate before registering."""
import sqlite3, sys, statistics as st, math
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_slip as S
c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute("SELECT * FROM predictions")]
overs = [r for r in rows if (r.get("side") or "over")=="over" and (r.get("tier") or "firm")!="n1"]
kept, _ = S.current_selection(overs, commit=False)
def b(r):
    res=str(r.get("result") or "").lower()
    return "VOID" if res=="void" else ("W" if res=="over" else ("L" if res=="under" else "P"))
fwd = [r for r in kept if str(r["pred_date"]) >= "2026-07-31" and b(r) in ("W","L")]
def rec(sel, lab):
    W=[r for r in sel if b(r)=="W"]; L=[r for r in sel if b(r)=="L"]
    n=len(W)+len(L)
    if not n: print(f"  {lab:38s} none"); return None
    u=sum(float(r["odds"])-1 for r in W)-len(L)
    print(f"  {lab:38s} {len(W):2d}-{len(L):<2d} {len(W)/n*100:5.1f}%  {u:+6.2f}u  ROI {u/n*100:+6.1f}%  (n={n})")
    return (len(W), n)
print("=== OVERLAP: is basis=volume entirely inside points? ===")
vol = [r for r in fwd if str(r.get("basis"))=="volume"]
print(f"  forward volume bets: {len(vol)}   of which stat=points: {sum(1 for r in vol if str(r.get('stat'))=='points')}")
print(f"  -> {'FULLY NESTED inside points' if all(str(r.get('stat'))=='points' for r in vol) else 'not nested'}")
print("\n=== 2x2 CROSS-TAB (the only way to tell them apart) ===")
pv  = rec([r for r in fwd if str(r.get("stat"))=="points" and str(r.get("basis"))=="volume"], "points  &  volume")
pnv = rec([r for r in fwd if str(r.get("stat"))=="points" and str(r.get("basis"))!="volume"], "points  &  NOT volume")
npv = rec([r for r in fwd if str(r.get("stat"))!="points" and str(r.get("basis"))=="volume"], "non-pts &  volume")
npn = rec([r for r in fwd if str(r.get("stat"))!="points" and str(r.get("basis"))!="volume"], "non-pts &  NOT volume")
print("\n  READ: if 'points & NOT volume' looks like 'non-pts & NOT volume', then MARKET does not")
print("        matter and VOLUME is the whole story. If points-not-volume is much worse, market matters too.")
def z2(a, b_):
    (w1,n1),(w2,n2) = a, b_
    p1,p2=w1/n1,w2/n2; pp=(w1+w2)/(n1+n2)
    se=math.sqrt(pp*(1-pp)*(1/n1+1/n2)) if 0<pp<1 else 1e-9
    return (p1-p2)*100,(p1-p2)/se
if pnv and npn:
    d,z = z2(npn, pnv)
    print(f"\n  non-points vs points, BOTH excluding volume: {d:+.1f}pp  z={z:+.2f}"
          f"  -> {'market still matters' if abs(z)>1.96 else 'NO residual market effect'}")
if pv and pnv:
    d,z = z2(pnv, pv)
    print(f"  within POINTS, not-volume vs volume:         {d:+.1f}pp  z={z:+.2f}"
          f"  -> {'volume is the driver' if abs(z)>1.96 else 'not significant alone'}")
