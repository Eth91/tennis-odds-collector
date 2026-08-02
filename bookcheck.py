import sqlite3, sys; sys.path.insert(0,".")
import wnba_props_db as PDB
db = PDB.props_db(); print("  props db:", db)
c = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
print("\n  === Puoch points rows, last day, by book ===")
q = ("SELECT COALESCE(book,'fd'), line, side, odds, collected_at, COALESCE(live,0) "
     "FROM fd_lines WHERE sport='wnba' AND player LIKE ? AND stat='points' "
     "AND collected_at > datetime('now','-1 day') ORDER BY collected_at DESC LIMIT 20")
rows = c.execute(q, ("%Puoch%",)).fetchall()
for r in rows:
    print("    %-4s o%-6s %-6s %-8s %s live=%s" % r)
if not rows: print("    (none)")
print("\n  === newest snapshot per book (the cadence gap) ===")
for r in c.execute("SELECT COALESCE(book,'fd'), MAX(collected_at), COUNT(*) FROM fd_lines "
                   "WHERE sport='wnba' AND collected_at > datetime('now','-1 day') GROUP BY 1"):
    print("    %-4s newest=%s  rows=%d" % r)
print("\n  === what posted_props() actually returns for her now ===")
import wnba_tonight as T
print("   ", T.posted_props("Nyadiew Puoch"))
