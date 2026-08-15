"""EXP-022 IS PR-003 JUST PR-001 IN DISGUISE? PR-001 penalises low vacated production. If a
2-out cascade simply vacates LESS per out -- because the second out is often a marginal player
-- then the two pre-registrations are ONE effect counted twice, and PR-003 must be withdrawn.
This is a redundancy check on the clv population; it tunes neither promotion bar (both are
forward-only, and neither is inspected here)."""
import sqlite3, math, statistics as st, sys, os
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT * FROM clv WHERE flag_line IS NOT NULL AND actual IS NOT NULL AND flag_over IS NOT NULL")]
import wnba_wowy as W
pl = W.players()
mins = {}
for n, v in pl.items():
    m = v.get("min")
    if m: mins[n.lower()] = float(m)
def look(name):
    k = name.strip().lower()
    if k in mins: return mins[k]
    for kk, vv in mins.items():
        if k and (k in kk or kk in k): return vv
    return None
resolved = miss = 0
for r in rows:
    outs = [x.strip() for x in (r["out_player"] or "").split(",") if x.strip()]
    r["ncas"] = len(outs)
    ms = [look(o) for o in outs]
    r["vac_min"] = sum(m for m in ms if m is not None) if any(m is not None for m in ms) else None
    r["all_res"] = all(m is not None for m in ms) and bool(outs)
    resolved += 1 if r["all_res"] else 0; miss += 0 if r["all_res"] else 1
    r["won"] = float(r["actual"]) > float(r["flag_line"])
print(f"out-player minutes resolved on {resolved}/{resolved+miss} rows "
      f"({miss} rows have an unresolvable out and are EXCLUDED, never defaulted to 0)\n")
use = [r for r in rows if r["all_res"]]
def hit(rs): return sum(1 for r in rs if r["won"])/len(rs)*100 if rs else 0
def z2(a, b):
    if not a or not b: return 0, 0
    pa, pb = hit(a)/100, hit(b)/100
    pp = (sum(1 for r in a if r["won"])+sum(1 for r in b if r["won"]))/(len(a)+len(b))
    se = math.sqrt(pp*(1-pp)*(1/len(a)+1/len(b))) if 0 < pp < 1 else 0
    return (pa-pb)*100, ((pa-pb)/se if se else 0)
print("STEP 1 -- do 2-out cascades vacate less TOTAL minutes than the rest?")
for k in (1, 2, 3):
    sel = [r for r in use if (r["ncas"] == k if k < 3 else r["ncas"] >= 3)]
    if len(sel) < 20: continue
    vm = [r["vac_min"] for r in sel]
    print(f"  {k}{'+' if k>=3 else ' '} out  n={len(sel):3d}  vacated min: mean {st.mean(vm):5.1f} "
          f"median {st.median(vm):5.1f}   hit {hit(sel):5.1f}%")
print("\nSTEP 2 -- THE DECISIVE TEST: does the 2-out penalty survive INSIDE a vacated-minutes stratum?")
vals = sorted(r["vac_min"] for r in use); n = len(vals)
terts = (vals[n//3], vals[2*n//3])
print(f"  tertile cuts at {terts[0]:.1f} and {terts[1]:.1f} vacated minutes")
signs = []
for lbl, keep in (("LOW  vac", lambda v: v <= terts[0]),
                  ("MID  vac", lambda v: terts[0] < v <= terts[1]),
                  ("HIGH vac", lambda v: v > terts[1])):
    a = [r for r in use if r["ncas"] == 2 and keep(r["vac_min"])]
    b = [r for r in use if r["ncas"] != 2 and keep(r["vac_min"])]
    if len(a) < 15 or len(b) < 15:
        print(f"  {lbl}: thin (n={len(a)}/{len(b)})"); continue
    d, z = z2(a, b); signs.append(d < 0)
    print(f"  {lbl}: 2out {hit(a):5.1f}% (n={len(a):3d})  rest {hit(b):5.1f}% (n={len(b):3d})"
          f"   gap {d:+6.1f}pp  z={z:+5.2f}")
print(f"  -> penalty negative in {sum(signs)}/{len(signs)} vacated-minutes strata")
print("\nSTEP 3 -- and the CONVERSE: does vacated minutes predict on its own, holding out-count fixed?")
for k, lbl in ((1, "1 out"), (2, "2 out")):
    sel = [r for r in use if r["ncas"] == k]
    if len(sel) < 60: continue
    m = st.median(r["vac_min"] for r in sel)
    a = [r for r in sel if r["vac_min"] > m]; b = [r for r in sel if r["vac_min"] <= m]
    d, z = z2(a, b)
    print(f"  within {lbl}: high-vac {hit(a):5.1f}% (n={len(a):3d}) vs low-vac {hit(b):5.1f}% "
          f"(n={len(b):3d})  gap {d:+6.1f}pp  z={z:+5.2f}")
