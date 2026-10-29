#!/usr/bin/env python3
"""Grade the `gated` table — the bets a gate SUPPRESSED.

WHY THIS EXISTS. wnba_ledger.py creates `gated` with result/actual/graded columns and
wnba_alert.py's comment states the point plainly: "the only question that matters about a filter
('were the bets it killed actually losers?') could not be asked without reconstructing it".
But NOTHING ever wrote those columns. 68 suppressed bets sat ungraded from 2026-08-02 onward, so
the question the table exists to answer was unanswerable for a month. This is the house-style
failure: infrastructure that looks alive (rows accumulate) while the payload never happens.

⚠️ FAIL CLOSED, same rules as the firm ledger:
  * only grade when the date's box score is COMPLETE — absence from a partial parse is a failed
    fetch, not a DNP (that bug once voided two real losses out of the record)
  * resolve names with box_lookup (exact -> normalised -> UNIQUE substring); ambiguity returns
    None and the row is left ungraded rather than guessed
  * a push (actual == line) is recorded as 'push', never as a win or a loss
  * idempotent: only touches rows with graded=0
"""
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wnba_ledger as L                                              # noqa: E402

DB = HERE / "wnba_ledger.sqlite"


def main(apply=True):
    con = sqlite3.connect(DB, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT rowid, * FROM gated WHERE graded=0 OR graded IS NULL")]
    print(f"ungraded gated rows: {len(rows)}")
    boxes, skip = {}, {}
    done = 0
    for r in rows:
        d = str(r["pred_date"])
        if d not in boxes:
            b = L.box_actuals(d)
            boxes[d] = b if (b and L.box_complete(d)) else None
        box = boxes[d]
        if not box:
            skip["box missing/incomplete"] = skip.get("box missing/incomplete", 0) + 1
            continue
        hit = L.box_lookup(box, r["player"])
        if hit is None:
            skip["player unresolvable (left ungraded, never guessed)"] = \
                skip.get("player unresolvable (left ungraded, never guessed)", 0) + 1
            continue
        act = hit.get(r["stat"])
        if act is None:
            skip["stat missing"] = skip.get("stat missing", 0) + 1
            continue
        act = float(act)
        line = float(r["line"])
        res = "push" if act == line else ("over" if act > line else "under")
        if apply:
            con.execute("UPDATE gated SET result=?, actual=?, graded=1 WHERE rowid=?",
                        (res, act, r["rowid"]))
        done += 1
    if apply:
        con.commit()
    print(f"graded {done}   skipped {skip}")
    con.close()


if __name__ == "__main__":
    main(apply="--dry" not in sys.argv)
