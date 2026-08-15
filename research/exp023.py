"""EXP-023 BASE-RATE THE FLAG. Our flagged overs hit 48.9% on 845 rows. That number is
meaningless until it is compared with the over-rate of ALL WNBA props in the same window. If
the market's overs also land near 49%, the beneficiary flag adds nothing on the wide pool.
Standing rule: always base-rate a hit% before calling it skill.

Fail-closed: a date whose box score is incomplete is SKIPPED entirely, never partially graded --
absence from a partial parse is a failed fetch, not a DNP."""
import sqlite3, sys, math, statistics as st
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L

clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
lo, hi = clv.execute("SELECT MIN(date),MAX(date) FROM clv WHERE actual IS NOT NULL").fetchone()
print(f"comparison window {lo} .. {hi}\n")
flag = defaultdict(list)
for d, p, s, fl, act in clv.execute(
        "SELECT date,player,stat,flag_line,actual FROM clv WHERE flag_line IS NOT NULL "
        "AND actual IS NOT NULL AND flag_over IS NOT NULL"):
    flag[s].append(float(act) > float(fl))
    flag["ALL"].append(float(act) > float(fl))
flagkeys = {(d, str(p).lower(), s) for d, p, s in clv.execute(
    "SELECT date,player,stat FROM clv WHERE flag_line IS NOT NULL AND actual IS NOT NULL")}

fd = sqlite3.connect("file:wnba_lines.sqlite?mode=ro", uri=True, timeout=60)
q = ("SELECT substr(collected_at,1,10) d, player, stat, line, MAX(collected_at) "
     "FROM fd_lines WHERE sport='wnba' AND side='over' AND (live IS NULL OR live=0) "
     "AND substr(collected_at,1,10) BETWEEN ? AND ? AND stat IN ('points','rebounds','assists') "
     "GROUP BY d, player, stat, line")
rows = fd.execute(q, (lo, hi)).fetchall()
print(f"{len(rows)} distinct (date, player, stat, line) pre-game over quotes in window")

boxes, skipped = {}, set()
def box(d):
    if d not in boxes:
        b = L.box_actuals(d)
        boxes[d] = b if (b and L.box_complete(d)) else None
        if boxes[d] is None: skipped.add(d)
    return boxes[d]

base = defaultdict(list); basenf = defaultdict(list); bylvl = defaultdict(list)
ungraded = 0
for d, player, stat, line, _ in rows:
    b = box(d)
    if not b: ungraded += 1; continue
    hit = next((v for k, v in b.items() if str(player).lower() in str(k).lower()), None)
    if hit is None: ungraded += 1; continue
    act = hit.get(stat)
    if act is None or line is None: ungraded += 1; continue
    won = float(act) > float(line)
    base[stat].append(won); base["ALL"].append(won)
    bylvl[(stat, round(float(line) * 2) / 2)].append(won)
    if (d, str(player).lower(), stat) not in flagkeys:
        basenf[stat].append(won); basenf["ALL"].append(won)
print(f"skipped {len(skipped)} date(s) with an incomplete/absent box; {ungraded} quotes ungradable\n")

def pct(v): return sum(v)/len(v)*100 if v else float("nan")
def z2(a, b):
    if not a or not b: return 0.0, 0.0
    pa, pb = sum(a)/len(a), sum(b)/len(b)
    pp = (sum(a)+sum(b))/(len(a)+len(b))
    se = math.sqrt(pp*(1-pp)*(1/len(a)+1/len(b))) if 0 < pp < 1 else 0
    return (pa-pb)*100, ((pa-pb)/se if se else 0)
print(f"{'stat':10s} {'FLAGGED over%':>16s} {'MARKET-WIDE over%':>20s} {'NON-FLAGGED':>18s} {'gap vs non-flagged':>20s}")
for s in ("ALL", "points", "rebounds", "assists"):
    f, m, nf = flag.get(s, []), base.get(s, []), basenf.get(s, [])
    if not f or not m: continue
    d, z = z2([1 if x else 0 for x in f], [1 if x else 0 for x in nf])
    print(f"{s:10s} {pct(f):9.1f}% (n={len(f):4d}) {pct(m):11.1f}% (n={len(m):6d}) "
          f"{pct(nf):9.1f}% (n={len(nf):6d}) {d:+9.1f}pp  z={z:+5.2f}")
print("\nLINE-LEVEL MATCHED -- the flag picks certain line levels; compare inside each")
lv = defaultdict(list)
for d, p, s, fl, act in clv.execute(
        "SELECT date,player,stat,flag_line,actual FROM clv WHERE flag_line IS NOT NULL "
        "AND actual IS NOT NULL AND flag_over IS NOT NULL"):
    lv[(s, round(float(fl) * 2) / 2)].append(float(act) > float(fl))
tot_f = tot_m = 0; wf = wm = 0.0
for k, fv in sorted(lv.items()):
    mv = bylvl.get(k, [])
    if len(fv) < 10 or len(mv) < 30: continue
    wf += sum(fv); tot_f += len(fv); wm += pct(mv)/100*len(fv); tot_m += len(fv)
    print(f"  {k[0]:9s} {k[1]:5.1f}: flagged {pct(fv):5.1f}% (n={len(fv):3d})  market {pct(mv):5.1f}% (n={len(mv):5d})")
if tot_f:
    print(f"\n  LINE-MATCHED TOTAL: flagged {wf/tot_f*100:.1f}% vs market-expected {wm/tot_m*100:.1f}% "
          f"on the SAME line mix  ->  {wf/tot_f*100 - wm/tot_m*100:+.1f}pp")
