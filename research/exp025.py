"""EXP-025 IS THE BASELINE BROKEN? A main line must hit ~47-48% overs after vig. EXP-024
measured 40.5%. Either the collapse is not finding main lines, or the pool is contaminated by
players who were quoted and then did not play (a scratch is an automatic under). Until this
resolves to ~47%, EXP-024's +12.0pp measures the defect, not the flag."""
import sqlite3, sys, math
from collections import defaultdict, Counter
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L
fd = sqlite3.connect("file:wnba_lines.sqlite?mode=ro", uri=True, timeout=60)
clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
lo, hi = clv.execute("SELECT MIN(date),MAX(date) FROM clv WHERE actual IS NOT NULL").fetchone()

print("A. COVERAGE -- how many player-stat-days does fd_lines actually carry per day?")
per = fd.execute("SELECT substr(collected_at,1,10) d, COUNT(DISTINCT player||'|'||stat) "
                 "FROM fd_lines WHERE sport='wnba' AND substr(collected_at,1,10) BETWEEN ? AND ? "
                 "AND stat IN ('points','rebounds','assists') GROUP BY d ORDER BY d", (lo, hi)).fetchall()
vals = [n for _, n in per]
print(f"   {len(per)} days, player-stat combos/day: min {min(vals)} median "
      f"{sorted(vals)[len(vals)//2]} max {max(vals)}")
print(f"   days with <20 combos: {sum(1 for v in vals if v < 20)}/{len(vals)} "
      f"-- a real slate is 60-150, so low days are PARTIAL CAPTURE, not quiet slates")

print("\nB. WHERE THE ROWS GO -- reason each main line was dropped")
cur = fd.execute("SELECT substr(collected_at,1,10) d, player, stat, line, odds "
                 "FROM fd_lines WHERE sport='wnba' AND side='over' AND (live IS NULL OR live=0) "
                 "AND odds IS NOT NULL AND substr(collected_at,1,10) BETWEEN ? AND ? "
                 "AND stat IN ('points','rebounds','assists')", (lo, hi))
best = {}
for d, player, stat, line, odds in cur:
    if line is None: continue
    k = (d, str(player).lower(), stat); g = abs(float(odds) - 2.0)
    if k not in best or g < best[k][0]: best[k] = (g, float(line))
why = Counter(); graded = []
boxes = {}
def box(d):
    if d not in boxes:
        b = L.box_actuals(d); boxes[d] = b if (b and L.box_complete(d)) else None
    return boxes[d]
for (d, pl, stat), (_, line) in best.items():
    b = box(d)
    if not b: why["no/incomplete box for the date"] += 1; continue
    hit = next((v for k, v in b.items() if pl in str(k).lower()), None)
    if hit is None: why["player absent from box (DNP or name mismatch)"] += 1; continue
    if hit.get(stat) is None: why["stat missing"] += 1; continue
    mn = hit.get("minutes") or hit.get("min") or hit.get("mins")
    why["GRADED"] += 1
    graded.append((float(hit[stat]) > line, float(mn) if mn is not None else None, line, stat))
for k, v in why.most_common(): print(f"   {k:48s} {v:5d}")

print("\nC. DOES A MINUTES FILTER RESTORE ~47%? (a scratch is an automatic under)")
have = [g for g in graded if g[1] is not None]
print(f"   minutes available on {len(have)}/{len(graded)} graded rows")
if have:
    for lab, f in (("all", lambda m: True), (">=1 min", lambda m: m >= 1),
                   (">=10 min", lambda m: m >= 10), (">=20 min", lambda m: m >= 20)):
        s = [g for g in have if f(g[1])]
        if len(s) >= 25:
            print(f"   {lab:9s} over% {sum(1 for x in s if x[0])/len(s)*100:5.1f}%  (n={len(s)})")
else:
    print("   box_actuals carries no minutes field -- cannot test the scratch hypothesis this way")
    print(f"   fallback: over% among graded rows where the stat is 0 vs >0")
    z = [g for g in graded if g[0] is False]
    print(f"   graded rows n={len(graded)}, over% {sum(1 for x in graded if x[0])/len(graded)*100:.1f}%")

print("\nD. IS THE 'NEAREST EVEN MONEY' RULE FINDING MAIN LINES? price distribution of the picks")
picks = sorted(g for g, _ in best.values())
print(f"   |odds-2.00| at the chosen rung: median {picks[len(picks)//2]:.3f}  "
      f"p90 {picks[int(len(picks)*0.9)]:.3f}  max {picks[-1]:.3f}")
print(f"   rungs where even the BEST price is >0.5 from even: "
      f"{sum(1 for g in picks if g > 0.5)}/{len(picks)} -- these player-stats have NO main line "
      f"in the capture and should be dropped, not collapsed to a longshot")
