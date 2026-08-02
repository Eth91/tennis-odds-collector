import sqlite3, datetime as dt, sys; sys.path.insert(0,".")
import wnba_slip as S
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
today=dt.date.today().isoformat()
rows=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE pred_date>=?",(today,))]
sel,drop=S.current_selection(rows, commit=False)
print("=== drop reasons ===")
for d in (drop or []):
    r = d[0] if isinstance(d,(tuple,list)) else d
    why = d[1] if isinstance(d,(tuple,list)) and len(d)>1 else "?"
    print("  %-18s %-8s o%-5s  ->  %s" % (r.get("player"),r.get("stat"),r.get("line"), why))
print()
print("=== TIER assignment (A/B) — where does it come from? ===")
for fn in ("_tier","tier_of","band"):
    if hasattr(S, fn): print("   wnba_slip.%s exists" % fn)
import inspect
src = inspect.getsource(S)
import re
m = re.search(r"def _tier.*?(?=\ndef )", src, re.S)
print(m.group(0)[:900] if m else "   (no _tier in wnba_slip)")
