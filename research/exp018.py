"""EXP-018 does NEWS AGE predict the BET OUTCOME, not just CLV? CLV is not money.
clv.actual vs flag_line grades the over at the price we actually got -> 479 rows, not 85."""
import sys, os, sqlite3, json, statistics as st, datetime as dt, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
news = []
for ln in open(os.path.join(ROOT, "underdog_log.jsonl"), encoding="utf-8", errors="ignore"):
    ln = ln.strip()
    if not ln: continue
    try: e = json.loads(ln); ts = dt.datetime.fromisoformat(str(e.get("t")).replace("Z","+00:00"))
    except Exception: continue
    news.append((ts, (e.get("text") or "").lower()))
c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT * FROM clv WHERE flag_line IS NOT NULL AND actual IS NOT NULL AND flag_over IS NOT NULL")]
def sn(n): return (n or "").strip().split()[-1].lower()
def parse(x):
    try:
        t = dt.datetime.fromisoformat(str(x).replace("Z","+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except Exception: return None
recs = []
for r in rows:
    f = parse(r["flagged_at"])
    if not f: continue
    outs = [sn(x) for x in (r["out_player"] or "").split(",") if x.strip()]
    best = None
    for ts, txt in news:
        if ts <= f and any(o and o in txt for o in outs):
            a = (f-ts).total_seconds()/3600.0
            if a <= 240 and (best is None or a < best): best = a
    if best is None: continue
    recs.append({"age": best, "won": float(r["actual"]) > float(r["flag_line"]),
                 "dec": float(r["flag_over"]), "date": r["date"]})
print(f"gradeable rows matched to news: {len(recs)}\n")
def rec(v, lbl):
    if len(v) < 12: print(f"  {lbl:26s} n={len(v)} thin"); return None
    w = sum(1 for r in v if r["won"]); u = sum((r["dec"]-1) if r["won"] else -1 for r in v)
    print(f"  {lbl:26s} n={len(v):3d}  {w}-{len(v)-w} = {w/len(v)*100:5.1f}%  "
          f"{u:+7.2f}u  ROI {u/len(v)*100:+6.1f}%")
    return w/len(v)
FRESH = 9.0
print("=== BET OUTCOME by news age (graded at the FLAG line and FLAG price) ===")
a = rec([r for r in recs if r["age"] <= FRESH], f"fresh (<= {FRESH:g}h)")
b = rec([r for r in recs if r["age"] > FRESH], f"stale (>  {FRESH:g}h)")
if a and b:
    fa=[r for r in recs if r["age"]<=FRESH]; ba=[r for r in recs if r["age"]>FRESH]
    pp=(sum(1 for r in fa if r["won"])+sum(1 for r in ba if r["won"]))/(len(fa)+len(ba))
    se=math.sqrt(pp*(1-pp)*(1/len(fa)+1/len(ba)))
    print(f"\n  gap {(a-b)*100:+.1f}pp   z={(a-b)/se if se else 0:.2f}")
print("\n=== chronological split of the OUTCOME effect ===")
ds=sorted({r["date"] for r in recs}); mid=ds[len(ds)//2]
for lbl, sub in ((f"early (<{mid})",[r for r in recs if r["date"]<mid]),
                 (f"later (>={mid})",[r for r in recs if r["date"]>=mid])):
    print(f"  -- {lbl} --")
    x=rec([r for r in sub if r["age"]<=FRESH],"    fresh"); y=rec([r for r in sub if r["age"]>FRESH],"    stale")
    if x and y: print(f"     gap {(x-y)*100:+.1f}pp")
