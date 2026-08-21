"""Grade in-play quotes against FINAL box scores and measure ROI.

⚠️ GUARDS, because a big positive here would be the fourth manufactured edge this project has seen:
 * grade only when the box is COMPLETE (partial parse -> refuse, never treat absence as a zero)
 * robust name matching via wnba_ledger.box_lookup (exact -> normalised -> UNIQUE substring)
 * report the BASE RATE (over-rate) before any ROI claim
 * pay the price ACTUALLY POSTED at that snapshot -- no best-of, no re-reading
 * a push (final == line) is a stake return, not a win
"""
import sqlite3, sys, statistics as st, math
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L
MAP = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists"}
db = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/research/live_odds.sqlite?mode=ro",
                     uri=True, timeout=120)
db.row_factory = sqlite3.Row
rows = [dict(r) for r in db.execute("SELECT * FROM q")]
print(f"stored quotes: {len(rows)}")
print(f"  events {len({r['event_id'] for r in rows})}  dates {len({r['box_date'] for r in rows})}")
boxes, incomplete = {}, set()
def box(d):
    if d not in boxes:
        b = L.box_actuals(d)
        ok = bool(b) and L.box_complete(d)
        boxes[d] = b if ok else None
        if not ok: incomplete.add(d)
    return boxes[d]
graded, skip = [], defaultdict(int)
for r in rows:
    b = box(r["box_date"])
    if not b: skip["box missing/incomplete"] += 1; continue
    hit = L.box_lookup(b, r["player"])
    if hit is None: skip["player not resolvable in box"] += 1; continue
    stat = MAP.get(r["market"])
    fin = hit.get(stat) if stat else None
    if fin is None: skip["stat missing"] += 1; continue
    fin = float(fin); line = float(r["line"])
    if fin == line: skip["push (stake returned)"] += 1; continue
    won = (fin > line) if r["side"] == "Over" else (fin < line)
    graded.append({**r, "final": fin, "won": 1 if won else 0})
print(f"  graded {len(graded)}   skipped {dict(skip)}")
print(f"  dates with incomplete box (excluded): {sorted(incomplete)[:6]}")
if not graded: raise SystemExit
def roi(sel):
    if not sel: return None, None, 0
    u = sum((r["price"] - 1.0) if r["won"] else -1.0 for r in sel)
    return u, u / len(sel) * 100, len(sel)
print("\n=== BASE RATE FIRST (before any ROI claim) ===")
ov = [r for r in graded if r["side"] == "Over"]
print(f"  over quotes {len(ov)}: hit {sum(r['won'] for r in ov)/len(ov)*100:.1f}%   "
      f"mean price {st.mean([r['price'] for r in ov]):.3f} -> breakeven {100/st.mean([r['price'] for r in ov]):.1f}%")
un = [r for r in graded if r["side"] == "Under"]
print(f"  under quotes {len(un)}: hit {sum(r['won'] for r in un)/len(un)*100:.1f}%   "
      f"mean price {st.mean([r['price'] for r in un]):.3f} -> breakeven {100/st.mean([r['price'] for r in un]):.1f}%")
print("\n=== NAIVE STRATEGIES (flat stake, price as posted) ===")
for lab, sel in (("ALL overs", ov), ("ALL unders", un)):
    u, r_, n = roi(sel)
    se = math.sqrt(n) * 1.0
    print(f"  {lab:12s} n={n:5d}  {u:+9.2f}u  ROI {r_:+6.2f}%   (+/-{100/math.sqrt(n):.2f}pp 1SE approx)")
print("\n=== BY GAME MINUTE (offset from tip) ===")
for off in sorted({r["offset_min"] for r in graded}):
    s = [r for r in graded if r["offset_min"] == off]
    o = [r for r in s if r["side"] == "Over"]; un2 = [r for r in s if r["side"] == "Under"]
    _, ro, no = roi(o); _, ru, nu = roi(un2)
    print(f"  +{off:3d} min  overs n={no:4d} ROI {ro:+6.2f}%   unders n={nu:4d} ROI {ru:+6.2f}%")
print("\n=== BY MARKET ===")
for mk in sorted({r["market"] for r in graded}):
    s = [r for r in graded if r["market"] == mk]
    o = [r for r in s if r["side"] == "Over"]; un2 = [r for r in s if r["side"] == "Under"]
    _, ro, no = roi(o); _, ru, nu = roi(un2)
    print(f"  {mk:17s} overs n={no:4d} ROI {ro:+6.2f}%   unders n={nu:4d} ROI {ru:+6.2f}%")
print("\n=== BY BOOK ===")
for bk in sorted({r["book"] for r in graded}):
    s = [r for r in graded if r["book"] == bk]
    u, r_, n = roi(s)
    if n >= 50: print(f"  {bk:16s} n={n:5d}  ROI {r_:+6.2f}%")
