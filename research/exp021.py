"""EXP-021 WHY would 2 outs be worse than 3? Candidate mechanism: with 2 outs the model's
WOWY base is thinner (it needs both-out games) while the minutes are still spread across the
full rotation -- so it extrapolates. If that is the story, the penalty should SHRINK once
sample depth is controlled. If the penalty is untouched by every control, there is no
mechanism and PR-003 stays a bare pattern."""
import sqlite3, math, statistics as st
c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
cols = {r[1] for r in c.execute("PRAGMA table_info(clv)")}
rows = [dict(r) for r in c.execute(
    "SELECT * FROM clv WHERE flag_line IS NOT NULL AND actual IS NOT NULL AND flag_over IS NOT NULL")]
for r in rows:
    r["won"] = float(r["actual"]) > float(r["flag_line"])
    r["ncas"] = len([x for x in (r["out_player"] or "").split(",") if x.strip()])
    r["grp"] = "2out" if r["ncas"] == 2 else "rest"
def hit(rs): return sum(1 for r in rs if r["won"])/len(rs)*100 if rs else 0
def z2(a, b):
    if not a or not b: return 0, 0
    pa, pb = hit(a)/100, hit(b)/100
    pp = (sum(1 for r in a if r["won"])+sum(1 for r in b if r["won"]))/(len(a)+len(b))
    se = math.sqrt(pp*(1-pp)*(1/len(a)+1/len(b))) if 0 < pp < 1 else 0
    return (pa-pb)*100, ((pa-pb)/se if se else 0)
two = [r for r in rows if r["grp"]=="2out"]; oth = [r for r in rows if r["grp"]=="rest"]
print(f"available controls: {sorted(cols & {'proj','p_adj','vac','lead_hrs','n_without','proj_min','edge','price'})}\n")
print("STEP 1 -- do 2-out situations DIFFER on the model's own inputs? (a confound needs a difference)")
for f in ("proj", "p_adj", "vac", "proj_min", "edge", "lead_hrs", "n_without"):
    if f not in cols: continue
    a = [float(r[f]) for r in two if r.get(f) is not None]
    b = [float(r[f]) for r in oth if r.get(f) is not None]
    if len(a) < 20 or len(b) < 20: continue
    pooled = math.sqrt((st.pvariance(a)+st.pvariance(b))/2) or 1e-9
    print(f"  {f:10s} 2out {st.mean(a):7.3f} (n={len(a):3d})  rest {st.mean(b):7.3f} (n={len(b):3d})"
          f"  std-diff {(st.mean(a)-st.mean(b))/pooled:+.2f}")
print("\nSTEP 2 -- does the penalty SURVIVE stratifying on each control? (median split, within-stratum)")
for f in ("proj", "p_adj", "vac", "proj_min", "edge", "lead_hrs"):
    if f not in cols: continue
    vals = [float(r[f]) for r in rows if r.get(f) is not None]
    if len(vals) < 100: continue
    med = st.median(vals)
    out = []
    for lbl, keep in (("lo", lambda v: v <= med), ("hi", lambda v: v > med)):
        a = [r for r in two if r.get(f) is not None and keep(float(r[f]))]
        b = [r for r in oth if r.get(f) is not None and keep(float(r[f]))]
        if len(a) < 15 or len(b) < 15: out.append(f"{lbl} thin"); continue
        d, z = z2(a, b)
        out.append(f"{lbl} {d:+6.1f}pp (z={z:+5.2f}, n={len(a)}/{len(b)})")
    print(f"  within {f:10s} " + "  |  ".join(out))
print("\nSTEP 3 -- is it just WHO is out? (2-out cascades may over-represent certain teams)")
from collections import Counter
tk = "team" if "team" in cols else ("event" if "event" in cols else None)
if tk:
    ct = Counter(r[tk] for r in two if r.get(tk)); co = Counter(r[tk] for r in oth if r.get(tk))
    shared = [t for t in ct if ct[t] >= 20 and co.get(t, 0) >= 20]
    print(f"  {len(shared)} team(s) with >=20 rows on BOTH sides -- within-team is the clean test")
    signs = []
    for t in sorted(shared):
        a = [r for r in two if r.get(tk)==t]; b=[r for r in oth if r.get(tk)==t]
        d, z = z2(a, b); signs.append(d < 0)
        print(f"    {str(t)[:22]:22s} 2out {hit(a):5.1f}% (n={len(a):3d})  rest {hit(b):5.1f}% (n={len(b):3d})  {d:+6.1f}pp")
    if signs: print(f"  -> negative in {sum(signs)}/{len(signs)} teams")
else:
    print("  no team/event column")
