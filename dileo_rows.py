import sqlite3
c = sqlite3.connect("wnba_ledger.sqlite")
c.row_factory = sqlite3.Row
print("  every DiLeo row in the ledger:")
q = ("SELECT pred_date,stat,line,odds,d_min,tier,confidence,result,graded "
     "FROM predictions WHERE player LIKE ? ORDER BY pred_date")
for r in c.execute(q, ("%DiLeo%",)):
    print("    %s %-8s o%-6s odds=%-8s d_min=%-5s tier=%-6s conf=%-9s res=%-6s graded=%s"
          % tuple(r))
c.close()
