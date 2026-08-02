"""Two inconsistencies to pin down.

1. pga_grade_e3 reports E3-birdies-shadow 3-4-0 / -2.10u, while pga_validate's report says "No
   settled shadow bets yet." One of them is wrong about the same rows.
2. The whole Rocket Classic is excluded from the v1.0 test for "no snapshot before first tee".
   Worth knowing whether that is a one-off or will repeat every week.
"""
import sqlite3
c = sqlite3.connect("pga_paper.sqlite")
c.row_factory = sqlite3.Row
tabs = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("  tables:", tabs)
for t in tabs:
    cols = [d[1] for d in c.execute("PRAGMA table_info(%s)" % t)]
    n = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    print("\n  == %s (%d rows) ==\n     cols: %s" % (t, n, cols))
    if not n:
        continue
    if "stream" in cols:
        for r in c.execute("SELECT stream, COUNT(*) n, "
                           "SUM(result IS NOT NULL AND result!='') settled "
                           "FROM %s GROUP BY stream" % t):
            print("     %-24s rows=%-4s settled=%s" % (r["stream"], r["n"], r["settled"]))
    have = [x for x in ("p_bet", "p_fair", "snapshot_ts", "first_tee", "armed", "result", "pnl")
            if x in cols]
    if have and "result" in cols:
        q = ("SELECT %s FROM %s WHERE result IS NOT NULL AND result!='' LIMIT 10"
             % (",".join(have), t))
        print("     settled sample:")
        for r in c.execute(q):
            print("       ", dict(r))
        # how many settled rows carry BOTH probabilities (what the SPRT needs)
        if "p_bet" in cols and "p_fair" in cols:
            k = c.execute("SELECT COUNT(*) FROM %s WHERE result IS NOT NULL AND result!='' "
                          "AND p_bet IS NOT NULL AND p_fair IS NOT NULL" % t).fetchone()[0]
            print("     settled AND scorable (p_bet+p_fair present): %d" % k)
        if "snapshot_ts" in cols and "first_tee" in cols:
            b = c.execute("SELECT COUNT(*) FROM %s WHERE snapshot_ts IS NOT NULL AND first_tee "
                          "IS NOT NULL AND snapshot_ts < first_tee" % t).fetchone()[0]
            print("     rows captured BEFORE first tee: %d" % b)
c.close()
