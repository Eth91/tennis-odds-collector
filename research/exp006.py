"""EXP-006 ROBUSTNESS of the `vac` signal. Two specific ways it dies:
 (a) COLLINEARITY -- vac may just be proj_min re-expressed; test vac WITHIN proj_min strata.
 (b) PLAYER CONCENTRATION -- 6 of 10 forward losses came from 2 players; leave-one-player-out.
Either failure downgrades it to REJECTED/INVALID rather than a real ranker."""
import sys, os, sqlite3, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wnba_slip as S
con = sqlite3.connect("file:wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute("SELECT * FROM predictions")]
keep, _ = S.current_selection(rows)
g = [r for r in keep if r["result"] in ("over","under") and r.get("vac") is not None]
won = lambda r: 1 if r["result"]==(r["side"] or "over") else 0
def rec(s):
    if not s: return (0,0.0,0.0)
    w=sum(won(r) for r in s); u=sum((float(r["odds"])-1) if won(r) else -1 for r in s)
    return len(s), w/len(s)*100, u/len(s)*100
VMED = st.median([float(r["vac"]) for r in g])
print(f"n={len(g)} with vac; median vac={VMED:.1f}\n")

print("(a) COLLINEARITY — does vac still rank WITHIN each proj_min stratum?")
pm = [r for r in g if r.get("proj_min") is not None]
PMED = st.median([float(r["proj_min"]) for r in pm])
for lbl, sel in (("proj_min LOW", lambda r: float(r["proj_min"])<=PMED),
                 ("proj_min HIGH", lambda r: float(r["proj_min"])>PMED)):
    sub=[r for r in pm if sel(r)]
    lo=[r for r in sub if float(r["vac"])<=VMED]; hi=[r for r in sub if float(r["vac"])>VMED]
    nl,hl,rl=rec(lo); nh,hh,rh=rec(hi)
    print(f"  {lbl:14s} vac LOW n={nl:2d} {hl:5.1f}% | vac HIGH n={nh:2d} {hh:5.1f}%  "
          f"gap {hh-hl:+6.1f}pp {'(survives)' if nh>=4 and nl>=4 and hh>hl else '(thin/flat)'}")
print(f"\n  corr(vac, proj_min) check:")
xs=[float(r['vac']) for r in pm]; ys=[float(r['proj_min']) for r in pm]
mx,my=st.mean(xs),st.mean(ys)
num=sum((a-mx)*(b-my) for a,b in zip(xs,ys))
den=(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))**0.5
print(f"    r = {num/den:+.3f}  -> {'largely INDEPENDENT' if abs(num/den)<0.4 else 'COLLINEAR'}")

print("\n(b) PLAYER CONCENTRATION — leave-one-player-out on the vac gap")
players = sorted({r["player"] for r in g})
gaps=[]
for p in players:
    sub=[r for r in g if r["player"]!=p]
    lo=[r for r in sub if float(r["vac"])<=VMED]; hi=[r for r in sub if float(r["vac"])>VMED]
    if len(lo)<8 or len(hi)<8: continue
    _,hl,_=rec(lo); _,hh,_=rec(hi); gaps.append((hh-hl,p))
gaps.sort()
full_lo=[r for r in g if float(r["vac"])<=VMED]; full_hi=[r for r in g if float(r["vac"])>VMED]
_,fl,_=rec(full_lo); _,fh,_=rec(full_hi)
print(f"  full-sample gap: {fh-fl:+.1f}pp")
print(f"  LOO range: {gaps[0][0]:+.1f}pp (drop {gaps[0][1][:18]}) .. {gaps[-1][0]:+.1f}pp (drop {gaps[-1][1][:18]})")
print(f"  -> {'ROBUST: no single player carries it' if gaps[0][0] > 5 else 'FRAGILE: one player drives it'}")
