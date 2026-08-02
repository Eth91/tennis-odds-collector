"""Does Round 2 pricing know what happened in Round 1 of THIS tournament?

Player birdie rates come from the harvested `birdie_rounds` table (recency-weighted, half-life 120d)
and the harvest runs weekly — Mondays 23:10 per crontab. If this week's R1 is not in that table,
then R2 prices a player on their historical rate with no knowledge of the 68 or the 76 they just
shot, while the book has fully absorbed it.
"""
import sqlite3
import pga_birdies as B

c = sqlite3.connect(B.DB)
print("  birdie_rounds coverage:")
for tid, tn, n, rmin, rmax in c.execute(
        "SELECT tid, tname, COUNT(*), MIN(rnd), MAX(rnd) FROM birdie_rounds "
        "GROUP BY tid ORDER BY tid DESC LIMIT 6"):
    print("    %-12s %-34s rows=%-5d rounds %s..%s" % (tid, str(tn)[:34], n, rmin, rmax))

print("\n  is THIS week's event present?")
q = list(c.execute("SELECT tid, tname, rnd, COUNT(*) FROM birdie_rounds "
                   "WHERE tname LIKE ? GROUP BY tid, rnd", ("%Rocket%",)))
if not q:
    print("    NO — the current event has no harvested rounds at all")
for tid, tn, rnd, n in q:
    print("    %-12s %-30s round %s: %d players" % (tid, str(tn)[:30], rnd, n))

print("\n  most recent harvested round of ANY event:")
r = c.execute("SELECT tid, tname, MAX(rnd) FROM birdie_rounds "
              "GROUP BY tid ORDER BY tid DESC LIMIT 1").fetchone()
print("   ", r)
c.close()

print("\n  === so what DOES change between R1 and R2 pricing? ===")
print("    player rate  : harvested history, recency-weighted (half-life 120d), refreshed WEEKLY")
print("    course factor: pga_context, prior editions of this course")
print("    wind         : live open-meteo for the round")
print("    LAM          : re-anchored on the CURRENT market's two-sided Over lines each scan")
print("  The last one is the only channel through which R1 can reach the model at all — and it is")
print("  a FIELD-level anchor, not player-specific. A player who shot 65 and one who shot 77 get")
print("  the same treatment.")
