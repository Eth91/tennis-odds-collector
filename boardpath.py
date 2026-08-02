import sqlite3, datetime as dt, sys, traceback; sys.path.insert(0,".")
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
# mimic what the dashboard feeds it: ALL ungraded/upcoming rows, not just >= today
allrows=[dict(r) for r in c.execute("SELECT * FROM predictions")]
today=dt.date.today().isoformat()
up=[r for r in allrows if str(r.get("pred_date"))[:10] >= today]
print("  rows >= today: %d   |  all rows: %d" % (len(up), len(allrows)))
import wnba_slip as _SLB
for label, rows in (("today-only", up), ("ALL rows", allrows)):
    ov=[r for r in rows if (r.get("side") or "over")=="over"]
    try:
        keep=_SLB.current_selection(ov)[0]
        k={(r["pred_date"],r["player"],r["stat"],r["line"]) for r in keep}
        tod=[r for r in keep if str(r["pred_date"])[:10]>=today]
        print("\n  [%s] current_selection OK -> %d kept, %d for today:" % (label,len(keep),len(tod)))
        for r in sorted(tod,key=lambda x:x["player"]):
            print("      %-4s %-18s %-8s o%s" % (r["team"],r["player"],r["stat"],r["line"]))
    except Exception:
        print("\n  [%s] current_selection RAISED -> dashboard's bare except swallows it" % label)
        traceback.print_exc(limit=3)
