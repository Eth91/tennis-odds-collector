"""Repair rows voided as DNPs for players who ARE in a complete box score.

These predate the box_complete() guard added 2026-08-13, which stops NEW occurrences but never
repaired the existing damage. Same class as the two rows regraded earlier: an unmatched/partial
box lookup reported as a confident "did not play".

FAIL CLOSED: only repairs a row when the date's box is COMPLETE and the player is present with a
real value for that exact stat. Anything else is left voided -- a void is the safe state.
Run with --apply to write; default is a dry run."""
import sys, sqlite3
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L
APPLY = "--apply" in sys.argv
db = "/home/ubuntu/tennis-odds-collector/wnba_ledger.sqlite"
con = sqlite3.connect(db, timeout=60)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute("SELECT rowid,* FROM predictions WHERE result='void'")]
print(f"{len(rows)} voided rows to inspect  ({'APPLY' if APPLY else 'DRY RUN'})\n")
fix, keep = [], []
for r in rows:
    d = r["pred_date"]
    bx = L.box_actuals(d)
    if not bx or not L.box_complete(d):
        keep.append((r, "box missing/incomplete -> stay void")); continue
    pa = bx.get(r["player"]) or bx.get(str(r["player"]).lower().replace(".", ""))
    if pa is None:
        keep.append((r, "player genuinely absent from a COMPLETE box -> real DNP")); continue
    act = pa.get(r["stat"])
    if act is None:
        keep.append((r, f"no '{r['stat']}' value in box -> stay void")); continue
    res = "over" if float(act) > float(r["line"]) else "under"
    fix.append((r, float(act), res))
print("=== WOULD REPAIR ===")
for r, act, res in fix:
    won = res == "over"
    u = (float(r["odds"]) - 1.0) if won else -1.0
    print(f"  {r['pred_date']}  {str(r['player'])[:20]:20s} {str(r['stat'])[:8]:8s} "
          f"{float(r['line']):5.1f} @ {float(r['odds']):.2f}  actual {act:5.1f} -> {res.upper():5s} "
          f"({u:+.2f}u)")
print(f"\n=== LEFT VOID ({len(keep)}) ===")
for r, why in keep:
    print(f"  {r['pred_date']}  {str(r['player'])[:20]:20s} {str(r['stat'])[:8]:8s}  {why}")
if APPLY and fix:
    for r, act, res in fix:
        con.execute("UPDATE predictions SET result=?, actual=?, played=1, graded=1 WHERE rowid=?",
                    (res, act, r["rowid"]))
    con.commit()
    print(f"\napplied {len(fix)} repairs")
con.close()
