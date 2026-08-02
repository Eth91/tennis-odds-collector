"""Why did Carleton (B) flag AND ladder while DiLeo (A) did not flag at all?

Careful about the framing: `tier_of` only runs on rows that ARE flagged, so "DiLeo is an A play"
can only be true if she reached the prediction table. If she never flagged, she has no tier and the
question becomes WHERE in the funnel she was dropped — which is a different bug from a tier bug.
So: find both players in the raw ledger first, then read the funnel, and let the data say which.
"""
import sqlite3
import sys

DB = "wnba_ledger.sqlite"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("  tables:", tabs)

date = sys.argv[1] if len(sys.argv) > 1 else None
if not date:
    date = con.execute("SELECT MAX(pred_date) FROM predictions").fetchone()[0]
print("  slate date:", date)

cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
print("  prediction cols:", cols)

print("\n=== every row today mentioning CARLETON or DILEO (any table) ===")
for t in tabs:
    tc = [d[1] for d in con.execute("PRAGMA table_info(%s)" % t)]
    pcol = next((c for c in tc if c.lower() in ("player", "name", "player_name")), None)
    if not pcol:
        continue
    for who in ("Carleton", "DiLeo", "Dileo"):
        rows = con.execute("SELECT * FROM %s WHERE %s LIKE ?" % (t, pcol), ("%" + who + "%",)).fetchall()
        for r in rows:
            d = dict(r)
            dd = d.get("pred_date") or d.get("date") or d.get("slate_date") or ""
            if date and str(dd)[:10] != date[:10]:
                continue
            keep = {k: v for k, v in d.items() if k in
                    ("pred_date", "player", "team", "stat", "line", "odds", "ev", "d_min",
                     "tier", "bettable", "role", "conf", "side", "result", "played", "graded")}
            print("  %-16s %s" % (t, keep))

print("\n=== the full flagged board today, with tier ===")
sys.path.insert(0, ".")
try:
    import wnba_slip as WS
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM predictions WHERE pred_date=?", (date,))]
    print("  %d prediction rows" % len(rows))
    sel = WS.current_selection(date) if hasattr(WS, "current_selection") else None
    if sel is not None:
        print("  current_selection -> %d rows" % len(sel))
        fav = WS.fav_keys(sel)
        tm = WS.tier_map(sel) if hasattr(WS, "tier_map") else {}
        print("\n  %-22s %-6s %-10s %6s %6s %5s %5s %s"
              % ("player", "team", "stat", "line", "odds", "d_min", "tier", "fav?"))
        for r in sorted(sel, key=lambda x: (x.get("team") or "", x.get("player") or "")):
            k = (r.get("pred_date"), r.get("player"), r.get("stat"))
            print("  %-22s %-6s %-10s %6s %6s %5s %5s %s"
                  % (str(r.get("player"))[:22], r.get("team"), r.get("stat"),
                     r.get("line"), r.get("odds"), r.get("d_min"),
                     tm.get(k, "?"), "FAV" if k in fav else ""))
except Exception as e:
    print("  selection replay failed: %r" % (e,))
con.close()
