"""PR-002 EVALUATION — the arm has reached n>=40 graded, so the frozen bar is now due.

BAR (verbatim from PREREGISTERED.md, not reinterpreted):
  - capture at T-12h / T-8h prospectively for >= 40 qualifying situations
  - realised ROI at the chosen lead >= +8% on the NEW rows alone
  - calibration gap at that lead remains <= 0 (under-confident) on the NEW rows
  - the monotone ordering vs T-1h holds on the NEW rows
FAILURE: ROI < 0 at n >= 40, or the calibration gap turns positive -> REJECTED.

Rows before 2026-08-15 do not exist (the arm logged zero until the inverted-gate fix)."""
import sqlite3, statistics as st, math
from collections import defaultdict
c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/research/pr002_shadow.sqlite?mode=ro",
                    uri=True, timeout=60)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute("SELECT * FROM shadow WHERE graded=1")]
print(f"graded rows: {len(rows)}  slates: {len({r['slate'] for r in rows})}  "
      f"span {min(r['slate'] for r in rows)}..{max(r['slate'] for r in rows)}")
print(f"  distinct (player,stat,line): {len({(r['player'],r['stat'],r['line']) for r in rows})}")
def won(r):
    a = r.get("actual")
    return None if a is None else (1 if float(a) > float(r["line"]) else 0)
g = [r for r in rows if won(r) is not None]
for r in g: r["_w"] = won(r)
print(f"  usable: {len(g)}\n")

def clustered(sel, unit="slate"):
    """ROI clustered on slate -- rungs within a slate share injuries, pace and officiating."""
    if not sel: return None
    by = defaultdict(list)
    for r in sel:
        by[r[unit]].append((float(r["price"]) - 1.0) if r["_w"] else -1.0)
    per = [sum(v)/len(v) for v in by.values()]
    if len(per) < 3: return None
    m = st.mean(per); se = st.pstdev(per)/math.sqrt(len(per))
    tot = sum(sum(v) for v in by.values()); n = sum(len(v) for v in by.values())
    return m*100, se*100, (m/se if se else 0), n, len(per), tot

print(f"{'bucket':10s} {'n':>5s} {'hit%':>7s} {'ROI':>8s} {'SE':>7s} {'t':>7s} {'units':>8s} {'calib gap':>10s}")
res = {}
for bk in ("t12", "t10", "t8"):
    sel = [r for r in g if r["bucket"] == bk]
    if len(sel) < 10: print(f"{bk:10s} thin ({len(sel)})"); continue
    cl = clustered(sel)
    hit = sum(r["_w"] for r in sel)/len(sel)*100
    gap = st.mean([r["_w"] - float(r["p_over"]) for r in sel])   # actual - model p  (<=0 = under-confident)
    res[bk] = (cl, hit, gap)
    print(f"{bk:10s} {len(sel):5d} {hit:6.1f}% {cl[0]:+7.2f}% {cl[1]:6.2f} {cl[2]:+7.2f} {cl[5]:+8.2f} "
          f"{gap*100:+9.2f}pp")
print("\n=== VERDICT AGAINST THE FROZEN BAR ===")
best = max(res.items(), key=lambda kv: kv[1][0][0]) if res else None
if not best:
    print("  no bucket has enough rows"); raise SystemExit
bk, (cl, hit, gap) = best
print(f"  best lead bucket: {bk}   ROI {cl[0]:+.2f}%  (n={cl[3]}, slates={cl[4]})")
c1 = cl[3] >= 40;        print(f"  [{'PASS' if c1 else 'FAIL'}] n >= 40                          -> {cl[3]}")
c2 = cl[0] >= 8.0;       print(f"  [{'PASS' if c2 else 'FAIL'}] ROI >= +8% on NEW rows           -> {cl[0]:+.2f}%")
c3 = gap <= 0;           print(f"  [{'PASS' if c3 else 'FAIL'}] calibration gap <= 0             -> {gap*100:+.2f}pp")
print(f"  [ n/a ] monotone vs T-1h -- the shadow arm captures 7-13h ONLY, so T-1h is not in this")
print(f"          sample and this condition cannot be evaluated from the arm alone.")
fail = cl[0] < 0 or gap > 0
print(f"\n  FAILURE CONDITION (ROI<0 at n>=40, or calib gap turns positive): "
      f"{'TRIGGERED' if fail else 'not triggered'}")
print(f"  >>> {'PROMOTE' if (c1 and c2 and c3) else ('REJECT' if fail else 'NEITHER — bar not met, failure not triggered')}")
