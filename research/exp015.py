"""EXP-015 LEAD TIME -> CLV. EXP-014 hinted that late-UTC flags earn more line movement, but
hour-of-day conflates announcement timing, slate timing and lead time. Compute ACTUAL hours
from flagged_at to tip and test directly. This is the same axis as the decay curve, measured
on the market rather than on bet outcomes."""
import sys, os, sqlite3, statistics as st, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT * FROM clv WHERE close_line IS NOT NULL AND flag_line IS NOT NULL")]
have_tip = sum(1 for r in rows if r.get("tip"))
print(f"n={len(rows)}, rows with a tip timestamp: {have_tip}")

def lead_hours(r):
    if not r.get("tip"):
        return None
    try:
        t = dt.datetime.fromisoformat(str(r["tip"]).replace("Z", "+00:00"))
        f = dt.datetime.fromisoformat(str(r["flagged_at"]).replace("Z", "+00:00"))
        if t.tzinfo and not f.tzinfo: f = f.replace(tzinfo=t.tzinfo)
        if f.tzinfo and not t.tzinfo: t = t.replace(tzinfo=f.tzinfo)
        return (t - f).total_seconds()/3600.0
    except Exception:
        return None
lh = [(lead_hours(r), r) for r in rows]
lh = [(h, r) for h, r in lh if h is not None and -1 <= h <= 72]
print(f"rows with usable lead time: {len(lh)}")
if len(lh) < 40:
    print("\n  TIP TIMESTAMP TOO SPARSE -> falling back to flagged_at vs the slate's own median flag time")
    by_date = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r["flagged_at"])
    # relative earliness WITHIN a slate: how early was this flag vs that day's median flag?
    med = {d: sorted(v)[len(v)//2] for d, v in by_date.items()}
    out = []
    for r in rows:
        try:
            a = dt.datetime.fromisoformat(str(r["flagged_at"]))
            b = dt.datetime.fromisoformat(str(med[r["date"]]))
            out.append(((a-b).total_seconds()/3600.0, r))
        except Exception:
            pass
    lh = out
    print(f"  usable rows (relative-to-slate-median): {len(lh)}")
    lbl = "hours vs that slate's MEDIAN flag (negative = earlier than peers)"
else:
    lbl = "hours before tip"
print(f"\n-- CLV by {lbl} --")
lh.sort(key=lambda x: x[0])
n = len(lh)
qs = [lh[:n//4], lh[n//4:n//2], lh[n//2:3*n//4], lh[3*n//4:]]
for i, q in enumerate(qs, 1):
    if not q: continue
    clv = [float(r["close_line"])-float(r["flag_line"]) for _h, r in q]
    se = st.pstdev(clv)/len(clv)**0.5 if len(clv) > 1 else 0
    print(f"   Q{i}  lead {q[0][0]:+7.2f}..{q[-1][0]:+7.2f}h  n={len(q):3d}  "
          f"mean CLV {st.mean(clv):+.3f} +/- {se:.3f}  pos {sum(1 for x in clv if x>0)/len(clv)*100:5.1f}%")
xs = [h for h, _ in lh]; ys = [float(r["close_line"])-float(r["flag_line"]) for _h, r in lh]
mx, my = st.mean(xs), st.mean(ys)
num = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
den = (sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))**0.5
print(f"\n   corr(lead, CLV) = {num/den:+.3f}  (n={len(lh)})")
