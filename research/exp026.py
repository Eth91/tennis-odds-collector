"""EXP-026 BASE-RATE THE FLAG, on a line archive that actually spans real days.

EXP-023/024 are VOID: they ran on a 3-day rolling buffer treated as a month. This runs on
research/line_archive.sqlite (11 days reconstructed from the daily backups).

THE SANITY GATE COMES FIRST. A main line must hit ~47-48% overs after vig. If the market's
main-line over% does not land near that, the baseline is broken and NO comparison below is
reportable -- that is exactly how EXP-024 produced a confident +12.0pp out of a defect."""
import sqlite3, sys, math
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L

ar = sqlite3.connect("file:research/line_archive.sqlite?mode=ro", uri=True, timeout=60)
LO, HI = "2026-08-05", "2026-08-14"          # archive span minus today (ungraded)
best = {}
for d, player, stat, line, odds in ar.execute(
        "SELECT d,player,stat,line,odds FROM q WHERE side='over' AND d BETWEEN ? AND ?", (LO, HI)):
    k = (d, str(player).lower(), stat); g = abs(float(odds) - 2.0)
    if k not in best or g < best[k][0]:
        best[k] = (g, float(line), float(odds))
best = {k: v for k, v in best.items() if v[0] <= 0.5}   # no main line captured -> drop, not collapse
print(f"{len(best)} main lines over {LO}..{HI} (rungs with no near-even price dropped)")

boxes = {}
def box(d):
    if d not in boxes:
        b = L.box_actuals(d); boxes[d] = b if (b and L.box_complete(d)) else None
    return boxes[d]

clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
flagkeys = {(d, str(p).lower(), s) for d, p, s in clv.execute(
    "SELECT date,player,stat FROM clv WHERE flag_line IS NOT NULL AND actual IS NOT NULL "
    "AND date BETWEEN ? AND ?", (LO, HI))}
mkt = defaultdict(list); nonflag = defaultdict(list); drop = 0
for (d, pl, stat), (_, line, odds) in best.items():
    b = box(d)
    if not b: drop += 1; continue
    hit = next((v for k, v in b.items() if pl in str(k).lower()), None)
    if hit is None or hit.get(stat) is None: drop += 1; continue
    w = 1 if float(hit[stat]) > line else 0
    mkt[stat].append(w); mkt["ALL"].append(w)
    if (d, pl, stat) not in flagkeys:
        nonflag[stat].append(w); nonflag["ALL"].append(w)
print(f"{drop} dropped (no box / player absent / stat missing) -- never defaulted to a loss\n")
def pct(v): return sum(v)/len(v)*100 if v else float("nan")

m = mkt["ALL"]
print("=== SANITY GATE ===")
print(f"market main-line over%: {pct(m):.1f}%  (n={len(m)})   expected 47-48% after vig")
ok = 43.0 <= pct(m) <= 53.0
print(f"-> baseline {'USABLE' if ok else 'STILL BROKEN -- results below are NOT reportable'}\n")

flag = defaultdict(list)
for d, p, s, fl, act in clv.execute(
        "SELECT date,player,stat,flag_line,actual FROM clv WHERE flag_line IS NOT NULL "
        "AND actual IS NOT NULL AND flag_over IS NOT NULL AND date BETWEEN ? AND ?", (LO, HI)):
    w = 1 if float(act) > float(fl) else 0
    flag[s].append(w); flag["ALL"].append(w)
def z2(a, b):
    if not a or not b: return 0.0, 0.0
    pa, pb = sum(a)/len(a), sum(b)/len(b)
    pp = (sum(a)+sum(b))/(len(a)+len(b))
    se = math.sqrt(pp*(1-pp)*(1/len(a)+1/len(b))) if 0 < pp < 1 else 0
    return (pa-pb)*100, ((pa-pb)/se if se else 0)
print(f"{'stat':10s} {'FLAGGED':>18s} {'NON-FLAGGED MAIN':>20s} {'gap':>20s}")
for s in ("ALL", "points", "rebounds", "assists"):
    f, nf = flag.get(s, []), nonflag.get(s, [])
    if len(f) < 20 or len(nf) < 20: continue
    d, z = z2(f, nf)
    print(f"{s:10s} {pct(f):8.1f}% (n={len(f):4d}) {pct(nf):10.1f}% (n={len(nf):5d}) {d:+10.1f}pp z={z:+5.2f}")
print("\nover% by line level -- should be FLAT now; a monotone slide means ladder contamination survives")
lv = defaultdict(list)
for (d, pl, stat), (_, line, odds) in best.items():
    b = box(d)
    if not b: continue
    hit = next((v for k, v in b.items() if pl in str(k).lower()), None)
    if hit is None or hit.get(stat) is None: continue
    lv["low" if line <= 4.5 else ("mid" if line <= 9.5 else "high")].append(
        1 if float(hit[stat]) > line else 0)
for k in ("low", "mid", "high"):
    if len(lv[k]) >= 25: print(f"  {k:5s}: {pct(lv[k]):5.1f}% (n={len(lv[k]):4d})")
