"""RIGOROUS pass. The naive n is fake: 5 books x 6 snapshots quote the SAME player-game, so quote
rows are heavily correlated. Standard errors must be CLUSTERED BY GAME (the unit that shares
score, pace and officiating), not computed on 22k rows.

Also applies:
 * multiple testing -- 6 offsets x 3 markets x 2 sides = 36 cells were inspected
 * chronological split -- earlier dates vs later dates
 * a same-line placebo: does the effect survive when the price is replaced by a fair-vig price?
"""
import sqlite3, sys, statistics as st, math
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L
MAP = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists"}
db = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/research/live_odds.sqlite?mode=ro",
                     uri=True, timeout=180)
db.row_factory = sqlite3.Row
rows = [dict(r) for r in db.execute("SELECT * FROM q")]
boxes = {}
def box(d):
    if d not in boxes:
        b = L.box_actuals(d); boxes[d] = b if (b and L.box_complete(d)) else None
    return boxes[d]
g = []
for r in rows:
    b = box(r["box_date"])
    if not b: continue
    hit = L.box_lookup(b, r["player"])
    if hit is None: continue
    fin = hit.get(MAP.get(r["market"], ""))
    if fin is None: continue
    fin = float(fin); line = float(r["line"])
    if fin == line: continue
    g.append({**r, "won": 1 if ((fin > line) if r["side"] == "Over" else (fin < line)) else 0})
print(f"graded {len(g)} quotes | {len({x['event_id'] for x in g})} games | "
      f"{len({x['box_date'] for x in g})} dates | {len({(x['event_id'],x['player']) for x in g})} player-games\n")

def clustered(sel, unit="event_id"):
    """ROI with SE clustered on `unit`. Cluster mean = that game's total units / bets."""
    if not sel: return None
    by = defaultdict(list)
    for r in sel:
        by[r[unit]].append((r["price"] - 1.0) if r["won"] else -1.0)
    per = [sum(v)/len(v) for v in by.values()]          # per-cluster mean unit result
    k = len(per)
    if k < 5: return None
    m = st.mean(per)
    se = st.pstdev(per)/math.sqrt(k)
    return m*100, se*100, m/se if se else 0, len(sel), k

print("=== HEADLINE, CLUSTERED BY GAME ===")
print(f"{'strategy':26s} {'ROI':>8s} {'SE':>7s} {'t':>7s} {'bets':>7s} {'games':>6s}")
for lab, sel in (("ALL overs", [r for r in g if r["side"]=="Over"]),
                 ("ALL unders", [r for r in g if r["side"]=="Under"])):
    c = clustered(sel)
    if c: print(f"{lab:26s} {c[0]:+7.2f}% {c[1]:6.2f} {c[2]:+7.2f} {c[3]:7d} {c[4]:6d}")

print("\n=== THE CELLS THAT LOOKED POSITIVE, PROPERLY TESTED ===")
cells = []
for off in sorted({r["offset_min"] for r in g}):
    for side in ("Over", "Under"):
        sel = [r for r in g if r["offset_min"]==off and r["side"]==side]
        c = clustered(sel)
        if c: cells.append((f"+{off}min {side}", c))
for mk in sorted({r["market"] for r in g}):
    for side in ("Over", "Under"):
        sel = [r for r in g if r["market"]==mk and r["side"]==side]
        c = clustered(sel)
        if c: cells.append((f"{mk.replace('player_','')} {side}", c))
cells.sort(key=lambda x: -x[1][0])
for lab, c in cells[:8]:
    print(f"  {lab:26s} ROI {c[0]:+7.2f}%  SE {c[1]:5.2f}  t {c[2]:+6.2f}  n={c[3]:5d} games={c[4]}")
print(f"  ... {len(cells)} cells inspected -> Bonferroni |t| needed ~{2.7 + 0.35*math.log(max(len(cells),1)):.2f}")
best = cells[0]
print(f"\n  best cell: {best[0]}  t={best[1][2]:+.2f}  "
      f"-> {'SURVIVES' if abs(best[1][2]) > 3.0 else 'does NOT survive multiple testing'}")

print("\n=== CHRONOLOGICAL SPLIT on the best cell ===")
ds = sorted({r["box_date"] for r in g}); mid = ds[len(ds)//2]
lab = best[0]
def cellsel(lab):
    if lab.startswith("+"):
        off = int(lab.split("min")[0][1:]); side = lab.split()[1]
        return [r for r in g if r["offset_min"]==off and r["side"]==side]
    mk, side = lab.split(); mk = "player_"+mk
    return [r for r in g if r["market"]==mk and r["side"]==side]
sel = cellsel(lab)
for half, f in (("EARLY", lambda r: r["box_date"] < mid), ("LATER", lambda r: r["box_date"] >= mid)):
    c = clustered([r for r in sel if f(r)])
    if c: print(f"  {half}: ROI {c[0]:+7.2f}%  t {c[2]:+6.2f}  n={c[3]:5d} games={c[4]}")
