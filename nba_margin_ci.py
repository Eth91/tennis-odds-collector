"""Date-clustered bootstrap CI on the surviving cells of the real-line refit."""
import random, statistics as st
import nba_margin_refit as R
from collections import defaultdict

rows = R.collect()
dates = sorted({r["date"] for r in rows})
mid = dates[len(dates)//2]

def units(v): return sum((r["price"]-1.0) if r["won"] else -1.0 for r in v)

def boot(sel, n=4000, seed=7):
    """Resample DATES with replacement -> ROI distribution (clusters = dates)."""
    byd = defaultdict(list)
    for r in sel: byd[r["date"]].append(r)
    ds = list(byd)
    if len(ds) < 10: return None
    rnd = random.Random(seed); out=[]
    for _ in range(n):
        pick=[]
        for _ in range(len(ds)): pick.extend(byd[rnd.choice(ds)])
        if pick: out.append(units(pick)/len(pick)*100)
    out.sort()
    return out[int(.025*len(out))], out[int(.975*len(out))], len(ds)

print(f"\n{'cell':<26} {'n':>6} {'dates':>6} {'hit%':>7} {'ROI':>8}   95% CI (date-clustered)")
print("-"*86)
for stat, margins in (("pts",[3.0,3.5,4.0,4.5,5.0]), ("pra",[4.5,5.0,6.5]), ("reb",[1.5,2.0])):
    for m in margins:
        for half,lab in ((lambda r: r["date"]<mid,"fit"), (lambda r: r["date"]>=mid,"hold"),
                         (lambda r: True,"ALL")):
            sel=[r for r in rows if r["stat"]==stat and r["proj"]-r["line"]>=m and half(r)]
            if len(sel)<40: continue
            roi=units(sel)/len(sel)*100
            hit=sum(r["won"] for r in sel)/len(sel)*100
            b=boot(sel)
            ci=f"[{b[0]:+6.2f}%, {b[1]:+6.2f}%]" if b else "n/a"
            nd=b[2] if b else 0
            print(f"{stat}>={m:<4} {lab:<5}{'':<9} {len(sel):6d} {nd:6d} {hit:6.1f}% {roi:+7.2f}%   {ci}")
    print()

# the null every claim must beat: bet EVERY candidate over, same universe
for stat in ("pts","pra"):
    sel=[r for r in rows if r["stat"]==stat]
    b=boot(sel)
    print(f"NULL always-over {stat}: n={len(sel)} ROI={units(sel)/len(sel)*100:+.2f}%  "
          f"CI [{b[0]:+.2f}%, {b[1]:+.2f}%]")
