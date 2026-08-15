"""EXP-003: is EV ranking CONVICTION or just PRICE?
EV = p_adj*dec - 1. Decompose which term drives the high-EV bucket.
Falsifier: if high-EV bets have the SAME p_adj but LONGER dec, EV is a price proxy and
cannot rank hit-rate -- which would fully explain the observed flat ranking."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlite3
import wnba_slip as S
con = sqlite3.connect("file:wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute("SELECT * FROM predictions")]
keep, _ = S.current_selection(rows)
g = [r for r in keep if r["result"] in ("over", "under")]
won = lambda r: r["result"] == (r["side"] or "over")
print(f"n={len(g)} tracked graded\n")
print(f"{'EV bucket':12s} {'n':>3s} {'hit%':>6s} {'ROI%':>7s} {'avg p_adj':>10s} {'avg dec':>8s} {'impl%':>7s}")
print("-"*62)
for lo, hi, lbl in ((0.10,0.20,"0.10-0.20"), (0.20,0.30,"0.20-0.30"), (0.30,9,"0.30+")):
    v=[r for r in g if r.get("ev") is not None and lo<=float(r["ev"])<hi]
    if not v: continue
    w=sum(1 for r in v if won(r)); u=sum((float(r["odds"])-1)if won(r)else -1 for r in v)
    ph=[float(r["proj_hit"]) for r in v if r.get("proj_hit") is not None]
    dec=sum(float(r["odds"]) for r in v)/len(v)
    print(f"{lbl:12s} {len(v):3d} {w/len(v)*100:6.1f} {u/len(v)*100:7.1f} "
          f"{(sum(ph)/len(ph) if ph else 0):10.3f} {dec:8.2f} {100/dec:7.1f}")
print("\n=== the decomposition ===")
import statistics as st
lo_ev=[r for r in g if r.get("ev") and float(r["ev"])<0.20]
hi_ev=[r for r in g if r.get("ev") and float(r["ev"])>=0.30]
for lbl,v in (("EV<0.20",lo_ev),("EV>=0.30",hi_ev)):
    if not v: continue
    ph=[float(r["proj_hit"]) for r in v if r.get("proj_hit") is not None]
    d=[float(r["odds"]) for r in v]
    print(f"  {lbl:9s} n={len(v):3d}  p_adj {st.mean(ph) if ph else 0:.3f}  dec {st.mean(d):.2f}")
if lo_ev and hi_ev:
    pl=[float(r["proj_hit"]) for r in lo_ev if r.get("proj_hit")]
    ph2=[float(r["proj_hit"]) for r in hi_ev if r.get("proj_hit")]
    dl=st.mean([float(r["odds"]) for r in lo_ev]); dh=st.mean([float(r["odds"]) for r in hi_ev])
    dp=(st.mean(ph2)-st.mean(pl)) if (pl and ph2) else 0
    print(f"\n  moving low->high EV: p_adj {dp:+.3f}   dec {dh-dl:+.2f}")
    print("  -> EV is driven by " + ("PRICE (dec), not conviction" if abs(dh-dl)>0.25 and abs(dp)<0.06
          else "conviction (p_adj)" if abs(dp)>=0.06 else "neither cleanly"))
