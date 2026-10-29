"""EXP-020 is the 2-OUT CASCADE penalty real? It is the only PRE-BET-KNOWABLE situation
variable that showed a stable outcome effect. Non-monotone (1 good, 2 bad, 3+ neutral), which
is itself a warning: a genuine 'more absence = more edge' story would be monotone."""
import sys, os, sqlite3, statistics as st, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT * FROM clv WHERE flag_line IS NOT NULL AND actual IS NOT NULL AND flag_over IS NOT NULL")]
for r in rows:
    r["won"] = float(r["actual"]) > float(r["flag_line"])
    r["ncas"] = len([x for x in (r["out_player"] or "").split(",") if x.strip()])
def z2(a, b):
    if not a or not b: return 0, 0, 0
    pa = sum(1 for r in a if r["won"])/len(a); pb = sum(1 for r in b if r["won"])/len(b)
    pp = (sum(1 for r in a if r["won"])+sum(1 for r in b if r["won"]))/(len(a)+len(b))
    se = math.sqrt(pp*(1-pp)*(1/len(a)+1/len(b))) if 0 < pp < 1 else 0
    return pa-pb, (pa-pb)/se if se else 0, pp
two = [r for r in rows if r["ncas"] == 2]; oth = [r for r in rows if r["ncas"] != 2]
d, z, _ = z2(two, oth)
print(f"2-out (n={len(two)}) vs the rest (n={len(oth)}):  gap {d*100:+.1f}pp  z={z:.2f}")
print(f"  ~10 situation variables screened this axis -> Bonferroni |z| needed ~2.81")
print(f"  -> {'SURVIVES' if abs(z) > 2.81 else 'does NOT survive multiple-testing correction'}\n")
print("chronological thirds (direction must hold in ALL of them to be believable):")
ds = sorted({r["date"] for r in rows}); k = len(ds)//3
cuts = [ds[:k], ds[k:2*k], ds[2*k:]]
sign = []
for i, cs in enumerate(cuts, 1):
    s = set(cs)
    a = [r for r in two if r["date"] in s]; b = [r for r in oth if r["date"] in s]
    if len(a) < 15 or len(b) < 15:
        print(f"  T{i}: thin"); continue
    dd, zz, _ = z2(a, b)
    sign.append(dd < 0)
    print(f"  T{i} ({cs[0]}..{cs[-1]})  2-out {sum(1 for r in a if r['won'])/len(a)*100:5.1f}% (n={len(a):3d})"
          f"  rest {sum(1 for r in b if r['won'])/len(b)*100:5.1f}% (n={len(b):3d})  gap {dd*100:+6.1f}pp")
print(f"  -> negative in {sum(sign)}/{len(sign)} thirds")
print("\nIS IT A CONFOUND? 2-out cascades by market and by line level:")
for lbl, sel in (("points", lambda r: r["stat"]=="points"), ("rebounds", lambda r: r["stat"]=="rebounds"),
                 ("assists", lambda r: r["stat"]=="assists")):
    a=[r for r in two if sel(r)]; b=[r for r in oth if sel(r)]
    if len(a)>=20 and len(b)>=20:
        dd,zz,_=z2(a,b)
        print(f"  within {lbl:9s}: 2-out {sum(1 for r in a if r['won'])/len(a)*100:5.1f}% vs rest "
              f"{sum(1 for r in b if r['won'])/len(b)*100:5.1f}%  gap {dd*100:+6.1f}pp")
