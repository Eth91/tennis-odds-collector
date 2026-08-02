"""Reproduce the board's headline exactly, then find what it counts that the bot would not bet.

The dashboard builds its record as: graded overs -> drop tier 'n1' -> current_selection -> count.
wnba_alert additionally requires `confidence in {confirmed, likely}` (role_ok) before a play is bet
or pinged. If the headline skips that gate, it is reporting bets the model refuses — the same
class of defect as the TT tracker counting a stale filter, and the same coherence rule.

Reproduce it first and check the number matches what is on the board. A fix proposed against a
number I could not reproduce would be worthless.
"""
import sqlite3

import wnba_slip as SL

BET_ROLES = {"confirmed", "likely"}
con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
g = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()

# exactly the dashboard's filter (dashboard.py ~343)
overs = [r for r in g if r["result"] in ("over", "under") and (r["side"] or "over") == "over"
         and (r.get("tier") or "firm") != "n1"]
dec, _dropped = SL.current_selection(overs)


def rec(rows, label):
    if not rows:
        print("  %-46s (none)" % label)
        return None
    n = len(rows)
    w = sum(1 for r in rows if r["result"] == (r["side"] or "over"))
    u = sum((float(r.get("odds") or 0) - 1) if r["result"] == (r["side"] or "over") else -1.0
            for r in rows)
    print("  %-46s %3d bets  %2d-%-2d  %5.1f%%  %+7.2fu" % (label, n, w, n - w, 100 * w / n, u))
    return (w, n - w, u)


print("=== reproduce the board headline ===")
board = rec(dec, "AS THE BOARD COUNTS IT (no role gate)")

print("\n=== what the bot would actually bet ===")
keep = [r for r in dec if str(r.get("confidence")) in BET_ROLES]
drop = [r for r in dec if str(r.get("confidence")) not in BET_ROLES]
gated = rec(keep, "WITH the role gate (confirmed/likely only)")
rec(drop, "the rows the gate would REMOVE")

print("\n=== what those removed rows are ===")
from collections import Counter
cnt = Counter(str(r.get("confidence")) for r in drop)
for k, v in cnt.most_common():
    sub = [r for r in drop if str(r.get("confidence")) == k]
    w = sum(1 for r in sub if r["result"] == (r["side"] or "over"))
    u = sum((float(r.get("odds") or 0) - 1) if r["result"] == (r["side"] or "over") else -1.0
            for r in sub)
    print("  confidence=%-12s %2d bets  %2d-%-2d  %+6.2fu" % (k, v, w, len(sub) - w, u))
for r in sorted(drop, key=lambda x: str(x.get("pred_date"))):
    print("    %s %-22s %-9s o%-6s conf=%-10s %s"
          % (r["pred_date"], str(r["player"])[:22], r["stat"], r["line"],
             r.get("confidence"), r["result"]))

if board and gated:
    print("\n=== the effect of closing the gap ===")
    print("  headline today : %d-%d  (%.1f%%)  %+.2fu" % (board[0], board[1],
          100 * board[0] / (board[0] + board[1]), board[2]))
    print("  headline gated : %d-%d  (%.1f%%)  %+.2fu" % (gated[0], gated[1],
          100 * gated[0] / (gated[0] + gated[1]), gated[2]))
    print("  -> %+.1f pts of hit rate, %+.2fu, and it would then match what the bot bets."
          % (100 * gated[0] / (gated[0] + gated[1]) - 100 * board[0] / (board[0] + board[1]),
             gated[2] - board[2]))
    print("\n  NOTE: this is not cherry-picking. The role gate is ALREADY live in wnba_alert — it")
    print("  decides what gets bet and pinged. The only thing changing is that the RECORD would")
    print("  stop counting plays the bot refuses. Coherence, not tuning.")
