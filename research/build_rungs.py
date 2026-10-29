#!/usr/bin/env python3
"""Materialise one row per rung so PR-004 can be tested economically without re-scanning.

Each pass over tick_archive costs ~20 min on this 2-core box at load 8. Everything downstream
(entry-at-open vs entry-at-close ROI, opener-conditional information) reads this table instead.

FAIL CLOSED ON GRADING: a date whose box score is missing or INCOMPLETE is skipped entirely.
Absence from a partial parse is a failed fetch, not a DNP -- that exact bug once voided two real
losses out of the tracked record."""
import sqlite3, sys, datetime as dt
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L

tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=900)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
print(f"archive days: {days}", flush=True)

clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
names = {}
for (n,) in tick.execute("SELECT DISTINCT player FROM obs"): names.setdefault(str(n).lower(), n)
def resolve(p):
    k = str(p).lower()
    return names.get(k) or next((v for kk, v in names.items() if k and (k in kk or kk in k)), None)
flag = {}
for date, player, stat, fline, fat in clv.execute(
        "SELECT date,player,stat,flag_line,flagged_at FROM clv WHERE flagged_at IS NOT NULL "
        "AND flag_line IS NOT NULL"):
    P = resolve(player)
    if P: flag[(date, P, stat, float(fline))] = str(fat)
print(f"{len(flag)} flagged keys resolved", flush=True)

out = sqlite3.connect("/home/ubuntu/tennis-odds-collector/research/rungs.sqlite", timeout=180)
out.execute("DROP TABLE IF EXISTS rungs")
out.execute("""CREATE TABLE rungs(
    d TEXT, player TEXT, stat TEXT, line REAL,
    open_p REAL, close_p REAL, open_dec REAL, close_dec REAL, nobs INTEGER,
    t_open TEXT, flagged INTEGER, pre_market INTEGER,
    actual REAL, won INTEGER,
    PRIMARY KEY(d, player, stat, line))""")

boxes = {}
def box(d):
    if d not in boxes:
        b = L.box_actuals(d)
        boxes[d] = b if (b and L.box_complete(d)) else None
    return boxes[d]

def p_of(o):
    o = float(o); return 1.0/o if o > 1.0 else None

tot = graded = 0
for d in days:
    ser = defaultdict(list)
    for player, stat, line, ca, odds in tick.execute(
            "SELECT player, stat, line, collected_at, odds FROM obs WHERE d=? AND side='over' "
            "AND book='fd' ORDER BY player, stat, line, collected_at", (d,)):
        v = p_of(odds)
        if v is not None: ser[(player, stat, float(line))].append((str(ca), v, float(odds)))
    b = box(d)
    rows = []
    for (player, stat, line), s in ser.items():
        if len(s) < 8: continue
        k = (d, player, stat, line)
        fat = flag.get(k)
        actual = won = None
        if b:
            hit = next((v for kk, v in b.items() if str(player).lower() in str(kk).lower()), None)
            if hit is not None and hit.get(stat) is not None:
                actual = float(hit[stat]); won = 1 if actual > line else 0
        rows.append((d, player, stat, line, s[0][1], s[-1][1], s[0][2], s[-1][2], len(s),
                     s[0][0], 1 if fat else 0, 1 if (fat and fat < s[0][0]) else 0, actual, won))
        tot += 1
        graded += 1 if won is not None else 0
    out.executemany("INSERT OR REPLACE INTO rungs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    out.commit()
    print(f"  {d}: {len(rows):5d} rungs  (box {'OK' if b else 'MISSING/INCOMPLETE -> ungraded'})", flush=True)

print(f"\n=== §37 VALIDATION ===")
q = out.execute
print("  rungs           :", q("SELECT COUNT(*) FROM rungs").fetchone()[0])
print("  graded          :", q("SELECT COUNT(*) FROM rungs WHERE won IS NOT NULL").fetchone()[0])
print("  distinct days   :", q("SELECT COUNT(DISTINCT d) FROM rungs").fetchone()[0])
print("  flagged         :", q("SELECT COUNT(*) FROM rungs WHERE flagged=1").fetchone()[0])
print("  flagged+graded  :", q("SELECT COUNT(*) FROM rungs WHERE flagged=1 AND won IS NOT NULL").fetchone()[0])
print("  pre-market      :", q("SELECT COUNT(*) FROM rungs WHERE pre_market=1").fetchone()[0])
print("  pre-market+grad :", q("SELECT COUNT(*) FROM rungs WHERE pre_market=1 AND won IS NOT NULL").fetchone()[0])
print("  ungraded days   :", [r[0] for r in q("SELECT DISTINCT d FROM rungs WHERE won IS NULL "
                                              "GROUP BY d HAVING COUNT(*)=SUM(won IS NULL)")])
print("\n  SANITY: market over-rate at rungs whose OPENER is near even money (expect 47-52%)")
r = q("SELECT COUNT(*), AVG(won) FROM rungs WHERE won IS NOT NULL AND open_p BETWEEN 0.45 AND 0.55").fetchone()
print(f"    n={r[0]}  over-rate {r[1]*100:.1f}%" if r[0] else "    none")
out.close()
