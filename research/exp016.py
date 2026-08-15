"""EXP-016 NEWS RECENCY -> CLV. EXP-015 showed lead-to-tip is NOT the axis (corr -0.063) but
late flags beat early ones. The reconciliation: what matters is how FRESH the injury signal was
when we flagged, not how far from tip. Uses underdog_log.jsonl timestamps -- a genuine
information-arrival clock, independent of p_adj and of the price."""
import sys, os, sqlite3, json, statistics as st, datetime as dt, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
news = []
for ln in open(os.path.join(ROOT, "underdog_log.jsonl"), encoding="utf-8", errors="ignore"):
    ln = ln.strip()
    if not ln: continue
    try: e = json.loads(ln)
    except Exception: continue
    t = e.get("t"); txt = (e.get("text") or "")
    if not t: continue
    try: ts = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except Exception: continue
    news.append((ts, txt.lower(), e.get("st")))
print(f"news items with timestamps: {len(news)}")

c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT * FROM clv WHERE close_line IS NOT NULL AND flag_line IS NOT NULL")]

def surname(n): return (n or "").strip().split()[-1].lower()

def news_age(r):
    """Hours between the LAST news item naming an out player and our flag. None if no match."""
    try: f = dt.datetime.fromisoformat(str(r["flagged_at"]).replace("Z", "+00:00"))
    except Exception: return None
    if f.tzinfo is None: f = f.replace(tzinfo=dt.timezone.utc)
    outs = [surname(x) for x in (r["out_player"] or "").split(",") if x.strip()]
    if not outs: return None
    best = None
    for ts, txt, _st in news:
        if ts > f: continue
        if any(o and o in txt for o in outs):
            age = (f - ts).total_seconds()/3600.0
            if age <= 240 and (best is None or age < best):
                best = age
    return best

vals = []
for r in rows:
    a = news_age(r)
    if a is None: continue
    vals.append((a, float(r["close_line"]) - float(r["flag_line"]), r))
print(f"rows matched to a prior news item: {len(vals)}\n")
if len(vals) < 40:
    print("  TOO FEW MATCHES to test -- the news log does not overlap the CLV window enough.")
    raise SystemExit
vals.sort(key=lambda x: x[0])
n = len(vals)
print("-- CLV by NEWS AGE at flag time (hours since the out player was last in the news) --")
for i, q in enumerate([vals[:n//3], vals[n//3:2*n//3], vals[2*n//3:]], 1):
    clv = [x[1] for x in q]
    se = st.pstdev(clv)/len(clv)**0.5 if len(clv) > 1 else 0
    print(f"   T{i}  age {q[0][0]:6.1f}..{q[-1][0]:6.1f}h  n={len(q):3d}  "
          f"mean CLV {st.mean(clv):+.3f} +/- {se:.3f}  pos {sum(1 for x in clv if x>0)/len(clv)*100:5.1f}%")
xs = [v[0] for v in vals]; ys = [v[1] for v in vals]
mx, my = st.mean(xs), st.mean(ys)
num = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
den = (sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))**0.5
print(f"\n   corr(news_age, CLV) = {num/den:+.3f}   (negative = FRESHER news earns MORE CLV)")
fresh = [v[1] for v in vals if v[0] <= 6]; stale = [v[1] for v in vals if v[0] > 24]
if len(fresh) >= 15 and len(stale) >= 15:
    print(f"   fresh <=6h  n={len(fresh):3d} mean CLV {st.mean(fresh):+.3f}")
    print(f"   stale >24h  n={len(stale):3d} mean CLV {st.mean(stale):+.3f}")
    print(f"   difference: {st.mean(fresh)-st.mean(stale):+.3f}")
