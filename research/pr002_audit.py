"""§40 AUDIT of PR-002's apparent +10.83%. Four specific ways it could be an artifact:
 1. NOT SIGNIFICANT — clustered t is +0.88. My bar tested ROI>=8% but never required significance.
 2. BEST-OF-3 SELECTION — I picked the winning bucket of t12/t10/t8 post hoc; the bar never
    pre-specified WHICH lead.
 3. THE THESIS IS MONOTONE DECAY — t12 should beat t10 should beat t8. Forward it is -8.4/+10.8/+1.3.
 4. HIT RATE IS ~40% — profit would then rest on a few longshots, not on being right."""
import sqlite3, statistics as st, math
from collections import defaultdict
c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/research/pr002_shadow.sqlite?mode=ro",
                    uri=True, timeout=60)
c.row_factory = sqlite3.Row
g = [dict(r) for r in c.execute("SELECT * FROM shadow WHERE graded=1 AND actual IS NOT NULL")]
for r in g: r["_w"] = 1 if float(r["actual"]) > float(r["line"]) else 0
t10 = [r for r in g if r["bucket"] == "t10"]
u = [(float(r["price"])-1.0) if r["_w"] else -1.0 for r in t10]
print(f"t10: n={len(t10)}  units {sum(u):+.2f}  ROI {sum(u)/len(u)*100:+.2f}%")
print(f"  mean price {st.mean([float(r['price']) for r in t10]):.2f}  "
      f"hit {sum(r['_w'] for r in t10)/len(t10)*100:.1f}%  "
      f"breakeven {100/st.mean([float(r['price']) for r in t10]):.1f}%")
su = sorted(u, reverse=True)
print(f"\n=== 4. IS IT A FEW LONGSHOTS? ===")
print(f"  top 5 winners: {[f'{x:+.2f}' for x in su[:5]]}  = {sum(su[:5]):+.2f}u of {sum(u):+.2f}u total")
print(f"  -> top 5 bets are {sum(su[:5])/sum(u)*100:.0f}% of all profit" if sum(u) else "")
trim = su[5:]
print(f"  after removing the 5 biggest wins: {sum(trim):+.2f}u  ROI {sum(trim)/len(trim)*100:+.2f}%")
print(f"\n=== 1. SIGNIFICANCE, clustered by slate ===")
by = defaultdict(list)
for r, x in zip(t10, u): by[r["slate"]].append(x)
per = [sum(v)/len(v) for v in by.values()]
m = st.mean(per); se = st.pstdev(per)/math.sqrt(len(per))
print(f"  {len(per)} slates   ROI {m*100:+.2f}%  SE {se*100:.2f}pp  t={m/se:+.2f}")
print(f"  95% CI: [{(m-1.96*se)*100:+.1f}%, {(m+1.96*se)*100:+.1f}%]  -> contains zero: "
      f"{'YES' if (m-1.96*se) < 0 < (m+1.96*se) else 'no'}")
print(f"  per-slate ROI: {[f'{x*100:+.0f}' for x in sorted(per, reverse=True)]}")
print(f"\n=== 3. IS THE DECAY MONOTONE? (the actual PR-002 thesis) ===")
for bk in ("t12", "t10", "t8"):
    s = [r for r in g if r["bucket"] == bk]
    uu = [(float(r["price"])-1.0) if r["_w"] else -1.0 for r in s]
    print(f"  {bk}: ROI {sum(uu)/len(uu)*100:+7.2f}%   (thesis needs t12 > t10 > t8)")
print("  -> monotone?  NO — t12 is the WORST bucket, the reverse of the registered claim")
print(f"\n=== 2. BEST-OF-3 penalty ===")
print(f"  picking the best of 3 buckets inflates; with 3 draws the max is biased upward by")
print(f"  roughly 0.85*SE = {0.85*se*100:.1f}pp, which is most of the {m*100:.1f}% headline.")
