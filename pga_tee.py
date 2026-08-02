"""Is `first_tee` the EVENT's tee or the ROUND's? That decides whether the exclusion is correct.

If the settled rows are ROUND 1 markets snapshotted at 20:30 on the day R1 teed off at 11:00, the
capture rule is right and we are flagging mid-round. If they are ROUND 2 markets being compared
against ROUND 1's tee time, the rule is using the wrong reference and will exclude every
round-based market forever — a silent validation-killer.
"""
import sqlite3
c = sqlite3.connect("pga_paper.sqlite"); c.row_factory = sqlite3.Row
print("  %-52s %-9s %-21s %-21s %s" % ("market", "stream", "snapshot_ts", "first_tee", "res"))
for r in c.execute("SELECT market,stream,snapshot_ts,first_tee,result,flagged_at FROM flags "
                   "ORDER BY flagged_at"):
    print("  %-52s %-9s %-21s %-21s %s"
          % (str(r["market"])[:52], str(r["stream"]).replace("E3-", "")[:9],
             r["snapshot_ts"], r["first_tee"], r["result"] or "-"))
print("\n  distinct first_tee values: ", [r[0] for r in c.execute(
    "SELECT DISTINCT first_tee FROM flags")])
print("  round mentioned in market names:")
import re
from collections import Counter
cn = Counter()
for (m,) in c.execute("SELECT market FROM flags"):
    g = re.search(r"Round (\d)", str(m))
    cn[g.group(1) if g else "no round"] += 1
print("   ", dict(cn))
c.close()
