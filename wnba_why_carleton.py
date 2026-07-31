"""The cap fix should keep DiLeo, yet the board still shows Carleton. Find which stage overrides it."""
import sqlite3
import wnba_slip as SL

D = "2026-07-31"
con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
rows = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE pred_date=?", (D,))]
print("  ledger rows for %s:" % D)
for r in rows:
    print("    %-20s %-8s o%-6s odds=%-8s ev=%-7s d_min=%-5s conf=%s"
          % (r["player"], r["stat"], r["line"], r["odds"], r.get("ev"), r.get("d_min"),
             r.get("confidence")))
print("\n  SELECTION LOG (the sticky incumbents):")
for r in con.execute("SELECT * FROM selections WHERE pred_date=?", (D,)):
    print("   ", r)
con.close()

kept, dropped = SL.current_selection(rows)
print("\n  current_selection KEEPS:")
for r in kept:
    print("    %-20s %-8s o%s" % (r["player"], r["stat"], r["line"]))
print("  current_selection DROPS:")
for r, why in dropped or []:
    print("    %-20s %-8s o%-6s <- %s" % (r["player"], r["stat"], r["line"], why))

print("\n  ranking key = (min odds, 0 if d_min in 3-8 else 1, -max ev)")
for who in ("Bridget Carleton", "Megan DiLeo"):
    g = [r for r in rows if r["player"] == who]
    if not g:
        continue
    dm = g[0].get("d_min")
    print("    %-20s odds=%.4f  band=%d  ev=%.3f  -> (%.4f, %d, %+.3f)"
          % (who, min(float(x["odds"]) for x in g),
             0 if (dm is not None and 3 <= dm <= 8) else 1,
             max(x.get("ev") or 0 for x in g),
             min(float(x["odds"]) for x in g),
             0 if (dm is not None and 3 <= dm <= 8) else 1,
             -max(x.get("ev") or 0 for x in g)))
print("\n  SWAP_MARGIN =", SL.SWAP_MARGIN, "— an incumbent holds unless beaten by this much EV")
