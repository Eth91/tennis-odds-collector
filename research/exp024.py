"""EXP-024 BASE-RATE, DONE PROPERLY. EXP-023's market pool was contaminated by the ALT LADDER:
market over% fell monotonically with line level inside every stat (assists 62.9->13.2%), which
is what you see when one player's 2.5 main line also appears as 4.5/5.5/6.5 rungs that almost
never hit. Comparing our selections to that pool compares main lines against longshots.

FIX: reduce the market to ONE MAIN LINE per (date, player, stat) -- the rung with over-odds
closest to even money. That definition is outcome-independent, so it cannot launder the result."""
import sqlite3, sys, math
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L

fd = sqlite3.connect("file:wnba_lines.sqlite?mode=ro", uri=True, timeout=60)
samp = [r[0] for r in fd.execute(
    "SELECT odds FROM fd_lines WHERE sport='wnba' AND odds IS NOT NULL LIMIT 200")]
dec = sum(1 for o in samp if 1.01 <= float(o) <= 15) > len(samp) * 0.8
print(f"odds format detected: {'DECIMAL' if dec else 'AMERICAN'}")
def to_dec(o):
    o = float(o)
    if dec: return o
    return 1 + (o/100 if o > 0 else 100/abs(o))

clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
lo, hi = clv.execute("SELECT MIN(date),MAX(date) FROM clv WHERE actual IS NOT NULL").fetchone()
flagkeys = {(d, str(p).lower(), s) for d, p, s in clv.execute(
    "SELECT date,player,stat FROM clv WHERE flag_line IS NOT NULL AND actual IS NOT NULL")}

# last pre-game over quote per (date, player, stat, line), then keep the rung nearest even money
cur = fd.execute(
    "SELECT substr(collected_at,1,10) d, player, stat, line, odds, MAX(collected_at) "
    "FROM fd_lines WHERE sport='wnba' AND side='over' AND (live IS NULL OR live=0) "
    "AND odds IS NOT NULL AND substr(collected_at,1,10) BETWEEN ? AND ? "
    "AND stat IN ('points','rebounds','assists') GROUP BY d,player,stat,line", (lo, hi))
best = {}
for d, player, stat, line, odds, _ in cur:
    if line is None: continue
    try: dd = to_dec(odds)
    except Exception: continue
    k = (d, str(player).lower(), stat)
    gap = abs(dd - 2.0)
    if k not in best or gap < best[k][0]:
        best[k] = (gap, float(line), dd)
print(f"{len(best)} main lines (one per date/player/stat) after collapsing the ladder")

boxes = {}
def box(d):
    if d not in boxes:
        b = L.box_actuals(d)
        boxes[d] = b if (b and L.box_complete(d)) else None
    return boxes[d]

mkt = defaultdict(list); nonflag = defaultdict(list); ungr = 0
for (d, pl, stat), (_, line, dd) in best.items():
    b = box(d)
    if not b: ungr += 1; continue
    hit = next((v for k, v in b.items() if pl in str(k).lower()), None)
    if hit is None: ungr += 1; continue
    act = hit.get(stat)
    if act is None: ungr += 1; continue
    won = 1 if float(act) > line else 0
    mkt[stat].append(won); mkt["ALL"].append(won)
    if (d, pl, stat) not in flagkeys:
        nonflag[stat].append(won); nonflag["ALL"].append(won)
print(f"{ungr} main lines ungradable (skipped, never defaulted)\n")

flag = defaultdict(list)
for d, p, s, fl, act in clv.execute(
        "SELECT date,player,stat,flag_line,actual FROM clv WHERE flag_line IS NOT NULL "
        "AND actual IS NOT NULL AND flag_over IS NOT NULL"):
    w = 1 if float(act) > float(fl) else 0
    flag[s].append(w); flag["ALL"].append(w)
def pct(v): return sum(v)/len(v)*100 if v else float("nan")
def z2(a, b):
    if not a or not b: return 0.0, 0.0
    pa, pb = sum(a)/len(a), sum(b)/len(b)
    pp = (sum(a)+sum(b))/(len(a)+len(b))
    se = math.sqrt(pp*(1-pp)*(1/len(a)+1/len(b))) if 0 < pp < 1 else 0
    return (pa-pb)*100, ((pa-pb)/se if se else 0)
print("MAIN LINES ONLY -- an over at a main line is roughly a coin flip by construction,")
print("so the honest benchmark is ~50%, and the flag must beat the NON-FLAGGED main lines.\n")
print(f"{'stat':10s} {'FLAGGED':>18s} {'MAIN-LINE MARKET':>20s} {'NON-FLAGGED MAIN':>20s} {'gap':>18s}")
for s in ("ALL", "points", "rebounds", "assists"):
    f, m, nf = flag.get(s, []), mkt.get(s, []), nonflag.get(s, [])
    if not f or not m: continue
    d, z = z2(f, nf)
    print(f"{s:10s} {pct(f):8.1f}% (n={len(f):4d}) {pct(m):10.1f}% (n={len(m):5d}) "
          f"{pct(nf):10.1f}% (n={len(nf):5d}) {d:+8.1f}pp z={z:+5.2f}")
print("\nSANITY -- if the main-line collapse worked, over% should now be FLAT across line levels,")
print("not the monotone decline EXP-023 saw (that decline WAS the ladder):")
lvl = defaultdict(list)
for (d, pl, stat), (_, line, dd) in best.items():
    b = box(d)
    if not b: continue
    hit = next((v for k, v in b.items() if pl in str(k).lower()), None)
    if hit is None or hit.get(stat) is None: continue
    lvl[(stat, "low" if line <= 4.5 else ("mid" if line <= 9.5 else "high"))].append(
        1 if float(hit[stat]) > line else 0)
for k in sorted(lvl):
    if len(lvl[k]) >= 30: print(f"  {k[0]:9s} {k[1]:5s}: {pct(lvl[k]):5.1f}% (n={len(lvl[k]):4d})")
