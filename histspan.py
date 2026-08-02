import sqlite3, os, glob
for db in ("wnba_lines.sqlite","fanduel_props.sqlite","fanduel_props.bak.sqlite","wnba_odds_hist.sqlite"):
    p=os.path.expanduser("~/tennis-odds-collector/"+db)
    if not os.path.exists(p): print("  %-28s ABSENT" % db); continue
    try:
        c=sqlite3.connect("file:%s?mode=ro"%p, uri=True)
        tbls=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        line=""
        for t in tbls:
            cols=[d[1] for d in c.execute("PRAGMA table_info(%s)"%t)]
            if "collected_at" in cols:
                mn,mx,n=c.execute("SELECT MIN(collected_at),MAX(collected_at),COUNT(*) FROM %s"%t).fetchone()
                line += "\n      %-14s %s -> %s  (%s rows)" % (t, str(mn)[:16], str(mx)[:16], n)
        print("  %-28s %.0f MB%s" % (db, os.path.getsize(p)/1048576, line))
    except Exception as e: print("  %-28s ERR %s" % (db, str(e)[:50]))
print("\n  === does the ledger store the realized value? ===")
c=sqlite3.connect(os.path.expanduser("~/tennis-odds-collector/wnba_ledger.sqlite"))
n,na=c.execute("SELECT COUNT(*), SUM(actual IS NOT NULL) FROM predictions WHERE graded=1").fetchone()
print("   graded=%d, with `actual`=%s" % (n,na))
