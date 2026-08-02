import sqlite3, sys; sys.path.insert(0,".")
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
rows=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
rows=[r for r in rows if r.get("result") in ("over","under") and r.get("odds")]
overs=[r for r in rows if str(r.get("side"))=="over"]
import wnba_slip as S
sel,_=S.current_selection(overs, commit=False)
uni=[r for r in sel if str(r.get("confidence")) in ("confirmed","likely")]
print("  full graded selected universe: %d" % len(uni))
have=[r for r in uni if str(r["pred_date"])[:10] >= "2026-07-29"]
print("  ...with rung history available (>= 2026-07-29): %d" % len(have))
print("  ...and with a realized `actual`: %d" % len([r for r in have if r.get("actual") is not None]))
from collections import Counter
print("  by date:", dict(Counter(str(r["pred_date"])[:10] for r in have)))
print("  by stat:", dict(Counter(r["stat"] for r in have)))
