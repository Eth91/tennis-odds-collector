import sqlite3
c = sqlite3.connect("wnba_ledger.sqlite")
print("TONIGHT'S LEDGER:")
for r in c.execute("SELECT COALESCE(tier,'firm'),player,stat,line,odds,ev,result,out_player "
                   "FROM predictions WHERE pred_date='2026-07-28' ORDER BY rowid"):
    print("  [%-4s] %-22s %-9s o%-5s @%-6s ev %+5.1f%%  %-8s | out: %s" % (
        r[0], r[1], r[2], r[3], r[4], (r[5] or 0)*100, r[6] or "PENDING", r[7]))
print()
print("by tier:", dict(c.execute("SELECT COALESCE(tier,'firm'),COUNT(*) FROM predictions "
                                 "WHERE pred_date='2026-07-28' GROUP BY 1").fetchall()))
