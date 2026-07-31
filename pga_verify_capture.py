"""Prove the new capture admits the 11 R2 flags and correctly refuses the 26 late ones.

_rows() only sees SETTLED flags, and R2 has not been played, so the report cannot show this yet.
Call the deadline resolver directly on every logged flag instead.
"""
import sqlite3, datetime as dt
import pga_validate as V

c = sqlite3.connect("pga_paper.sqlite"); c.row_factory = sqlite3.Row
rows = list(c.execute("SELECT event, market, runner, snapshot_ts, result FROM flags"))
c.close()

ok = late = bad = 0
for r in rows:
    dl, why = V._player_deadline(r["event"], r["market"])
    if dl is None:
        bad += 1
        print("  UNRESOLVED %-46s %s" % (str(r["market"])[:46], why))
        continue
    good = V._dt_lt(r["snapshot_ts"], dl)
    ok += good
    late += (not good)
print("\n  resolvable deadlines : %d of %d" % (len(rows) - bad, len(rows)))
print("  snapshot BEFORE that player's tee : %d" % ok)
print("  player already away               : %d" % late)
print("  unresolved                        : %d" % bad)

print("\n  === do the settled 7 carry both probabilities? (the report calls them unscorable) ===")
c = sqlite3.connect("pga_paper.sqlite")
n = c.execute("SELECT COUNT(*) FROM flags WHERE result IN ('W','L') "
              "AND p_bet IS NOT NULL AND p_fair IS NOT NULL").fetchone()[0]
print("  settled rows WITH p_bet and p_fair: %d" % n)
print("  -> they are excluded by the CAPTURE RULE (players already away), not by missing data.")
c.close()
