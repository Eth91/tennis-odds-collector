import sys, sqlite3, datetime as dt; sys.path.insert(0,".")
import dashboard as D, wnba_tonight as T
today = dt.datetime.now(D.ET).date().isoformat()
con=sqlite3.connect(D.LEDGER); con.row_factory=sqlite3.Row
raw=[dict(r) for r in con.execute("SELECT * FROM predictions WHERE pred_date>=? AND result IS NULL ORDER BY pred_date ASC, ev DESC",(today,))]
con.close()
print("  raw query (pred_date>=today AND result IS NULL): %d rows" % len(raw))
for r in raw: print("    %-18s %-8s o%-6s result=%r" % (r["player"],r["stat"],r["line"],r["result"]))
print()
p=[r for r in raw if "Puoch" in str(r["player"])]
print("  Puoch in raw query:", bool(p))
if p:
    r=p[0]
    pp=T.posted_props(r["player"])
    print("  posted_props(Puoch):", pp.get(r["stat"]) if pp else None)
    print("  round(line,1) =", round(float(r["line"]),1), "in posted:", round(float(r["line"]),1) in (pp.get(r["stat"]) or {}))
