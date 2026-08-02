"""What does played=1 actually measure? It is a MANUAL mark, not a record of what was bet."""
import os, sqlite3
from collections import Counter
import wnba_slip as SL

print("=== wnba_played.txt — the source of the flag ===")
p = SL.PLAYED_MARKS
print("  path: %s   exists=%s" % (p, p.exists()))
if p.exists():
    lines = [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]
    print("  %d mark lines" % len(lines))
    for l in lines:
        print("    %s" % l)

print("\n=== what the ledger therefore counts as 'real money' ===")
c = sqlite3.connect("wnba_ledger.sqlite")
rows = list(c.execute("SELECT pred_date,player,stat,line,odds,result,graded FROM predictions "
                      "WHERE played=1 ORDER BY pred_date"))
print("  played=1 rows: %d" % len(rows))
by = Counter(r[0] for r in rows)
print("  dates covered: %s" % dict(by))

print("\n=== versus how many bets the model CARDED per day over the same window ===")
print("  %-12s %8s %8s" % ("date", "carded", "marked"))
for (d,) in c.execute("SELECT DISTINCT pred_date FROM predictions WHERE pred_date>='2026-07-15' "
                      "ORDER BY pred_date"):
    n = c.execute("SELECT COUNT(*) FROM predictions WHERE pred_date=? AND side='over'", (d,)).fetchone()[0]
    m = c.execute("SELECT COUNT(*) FROM predictions WHERE pred_date=? AND played=1", (d,)).fetchone()[0]
    print("  %-12s %8d %8d%s" % (d, n, m, "   <- nothing marked" if m == 0 and n else ""))
c.close()
