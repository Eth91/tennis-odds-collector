import sqlite3, statistics as st, math, random, sys; sys.path.insert(0,".")
c=sqlite3.connect("wnba_ledger.sqlite"); c.row_factory=sqlite3.Row
cols=[d[1] for d in c.execute("PRAGMA table_info(predictions)")]
R=[dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
R=[r for r in R if r.get("actual") is not None and r.get("elev_avg") is not None
   and r.get("season_avg") and (r.get("side") or "over")=="over"]
d=[abs(r["actual"]-r["season_avg"])-abs(r["actual"]-r["elev_avg"]) for r in R]  # +ve = model better
print("=== paired: does the ELEVATED projection beat the SEASON AVERAGE? (n=%d) ===" % len(d))
m=st.mean(d)
print("   mean improvement of model over baseline: %+0.3f pts  (negative = model is WORSE)")
print("   mean improvement = %+0.3f" % m)
random.seed(3); bs=[]
for _ in range(5000):
    s=[random.choice(d) for _ in d]; bs.append(st.mean(s))
bs.sort()
lo,hi=bs[125],bs[4875]
print("   95%% CI [%+0.3f, %+0.3f]  -> %s" % (lo,hi,
      "model significantly WORSE" if hi<0 else ("model significantly better" if lo>0 else "indistinguishable")))
print("   model better on %d of %d bets (%.0f%%)" % (sum(1 for x in d if x>0), len(d), 100*sum(1 for x in d if x>0)/len(d)))
# does a blend beat both?
for w in (0.0,0.25,0.5,0.75,1.0):
    e=[abs(r["actual"]-(w*r["elev_avg"]+(1-w)*r["season_avg"])) for r in R]
    print("   blend %3.0f%% elevated / %3.0f%% season -> |miss| %.3f" % (100*w,100*(1-w),st.mean(e)))
