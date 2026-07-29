"""Undo my over-aggressive purge: merge the pre-purge backup back in.

The purge heuristic (line <= 40% of the player's max line) was wrong -- it treated legitimate
ALTERNATE rungs as quarter lines and deleted 29,003 rows across ALL history, not just the
last day. It was also unnecessary: posted_props() only reads rows within FRESH_MIN of the
player's newest stamp, so once the FIXED collector stops writing quarter rows they fall out
of the window on their own.
"""
import sqlite3

cur = sqlite3.connect("fanduel_props.sqlite")
before = cur.execute("SELECT COUNT(*) FROM fd_lines").fetchone()[0]
cur.execute("ATTACH DATABASE '/home/ubuntu/db_safe_final/fanduel_props.sqlite' AS bak")
cur.execute("INSERT OR IGNORE INTO fd_lines "
            "(collected_at,sport,event,player,stat,line,side,odds,book) "
            "SELECT collected_at,sport,event,player,stat,line,side,odds,book FROM bak.fd_lines")
cur.commit()
after = cur.execute("SELECT COUNT(*) FROM fd_lines").fetchone()[0]
print("rows: %d -> %d  (recovered %d)" % (before, after, after - before))
print("latest wnba stamp:", cur.execute(
    "SELECT MAX(collected_at) FROM fd_lines WHERE sport='wnba'").fetchone()[0])
cur.execute("DETACH DATABASE bak")
cur.close()
