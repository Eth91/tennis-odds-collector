import sqlite3, sys; sys.path.insert(0,".")
import wnba_props_db as PDB
c=sqlite3.connect("file:%s?mode=ro"%PDB.props_db(), uri=True)
print("=== when did each Carleton points rung FIRST and LAST appear? ===")
q=("SELECT line, MIN(collected_at), MAX(collected_at), COUNT(*) FROM fd_lines "
   "WHERE sport='wnba' AND player=? AND stat='points' AND side='over' "
   "AND collected_at > datetime('now','-1 day') GROUP BY line ORDER BY line")
for line,f,l,n in c.execute(q, ("Bridget Carleton",)):
    print("   o%-6s first=%s  last=%s  seen %d" % (line, f[11:19], l[11:19], n))
print("\n=== when was she flagged? ===")
d=sqlite3.connect("wnba_ledger.sqlite"); d.row_factory=sqlite3.Row
import datetime as dt
for r in d.execute("SELECT line, odds, ev FROM predictions WHERE player=? AND pred_date>=?",
                   ("Bridget Carleton", dt.date.today().isoformat())):
    print("   flagged o%s @%s ev=%s" % (r[0],r[1],r[2]))
