"""EXP-017 does NEWS AGE survive (a) a chronological split and (b) controlling for lead-to-tip?
EXP-015 showed LATE flags earn CLV. If fresh news simply happens near tip, EXP-016 is that
effect re-expressed and adds nothing. Test news-age WITHIN lead-time strata."""
import sys, os, sqlite3, json, statistics as st, datetime as dt, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
news = []
for ln in open(os.path.join(ROOT, "underdog_log.jsonl"), encoding="utf-8", errors="ignore"):
    ln = ln.strip()
    if not ln: continue
    try: e = json.loads(ln)
    except Exception: continue
    try: ts = dt.datetime.fromisoformat(str(e.get("t")).replace("Z", "+00:00"))
    except Exception: continue
    news.append((ts, (e.get("text") or "").lower()))
c = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute("SELECT * FROM clv WHERE close_line IS NOT NULL AND flag_line IS NOT NULL")]
def sn(n): return (n or "").strip().split()[-1].lower()
def parse(x):
    try:
        t = dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
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
    tip = parse(r.get("tip"))
    lead = (tip-f).total_seconds()/3600.0 if tip else None
    recs.append({"age": best, "clv": float(r["close_line"])-float(r["flag_line"]),
                 "date": r["date"], "lead": lead})
print(f"n={len(recs)}\n")
FRESH = 9.0
def split(rs, lbl):
    a = [x["clv"] for x in rs if x["age"] <= FRESH]; b = [x["clv"] for x in rs if x["age"] > FRESH]
    if len(a) < 12 or len(b) < 12:
        print(f"  {lbl:34s} thin ({len(a)}/{len(b)})"); return None
    d = st.mean(a)-st.mean(b)
    se = math.sqrt(st.pvariance(a)/len(a) + st.pvariance(b)/len(b))
    print(f"  {lbl:34s} fresh n={len(a):3d} {st.mean(a):+.3f} | stale n={len(b):3d} {st.mean(b):+.3f}"
          f"  diff {d:+.3f}  z={d/se if se else 0:5.2f}")
    return d
print("(a) CHRONOLOGICAL SPLIT — first half vs second half by date")
ds = sorted({x["date"] for x in recs}); mid = ds[len(ds)//2]
d1 = split([x for x in recs if x["date"] < mid], f"early slates (<{mid})")
d2 = split([x for x in recs if x["date"] >= mid], f"later slates (>={mid})")
if d1 is not None and d2 is not None:
    print(f"  -> {'SAME direction (holds)' if (d1>0)==(d2>0) else 'SIGN FLIP (artifact)'}")
print("\n(b) WITHIN LEAD-TO-TIP STRATA — is this just EXP-015's late-flag effect?")
wl = [x for x in recs if x["lead"] is not None]
if wl:
    lm = st.median([x["lead"] for x in wl])
    split([x for x in wl if x["lead"] <= lm], f"lead <= {lm:.1f}h (late flags)")
    split([x for x in wl if x["lead"] > lm], f"lead >  {lm:.1f}h (early flags)")
    xs=[x["age"] for x in wl]; ys=[x["lead"] for x in wl]
    mx,my=st.mean(xs),st.mean(ys)
    num=sum((a-mx)*(b-my) for a,b in zip(xs,ys))
    den=(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))**0.5
    print(f"  corr(news_age, lead) = {num/den:+.3f}  -> {'CONFOUNDED' if abs(num/den)>0.5 else 'largely independent axes'}")
