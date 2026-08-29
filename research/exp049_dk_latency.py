"""RE-MEASURE. The first pass counted overnight hours when dk_publish deliberately skips
("quiet hours"), so it conflated a design choice with a failure. What matters is the lag during
the hours the model actually selects: the run-up to tip."""
import sqlite3, datetime as dt, statistics as st, bisect
from collections import defaultdict
db = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_lines.sqlite?mode=ro", uri=True, timeout=90)
rows = db.execute("SELECT COALESCE(book,'fd'), collected_at FROM fd_lines WHERE sport='wnba' "
                  "AND (live IS NULL OR live=0) GROUP BY 1, collected_at").fetchall()
st_ = defaultdict(list)
for bk, ca in rows: st_[bk].append(dt.datetime.fromisoformat(str(ca)))
for k in st_: st_[k].sort()
dks, fds = st_.get("dk", []), st_.get("fd", [])
def dist(lo_h, hi_h, label):
    lags, t = [], max(min(dks), min(fds))
    end = min(max(dks), max(fds))
    while t <= end:
        if lo_h <= t.hour < hi_h:
            i = bisect.bisect_right(dks, t) - 1; j = bisect.bisect_right(fds, t) - 1
            if i >= 0 and j >= 0: lags.append((fds[j] - dks[i]).total_seconds()/60)
        t += dt.timedelta(minutes=10)
    if len(lags) < 10: print(f"  {label:34s} thin ({len(lags)})"); return
    lags.sort(); n = len(lags)
    ok = sum(1 for x in lags if x <= 10)
    print(f"  {label:34s} n={n:4d}  median {st.median(lags):6.1f}  p90 {lags[int(n*.9)]:7.1f}  "
          f"inside 10min {ok/n*100:5.1f}%")
print("\nlag by UTC hour band (WNBA tips are ~23:00-02:00 UTC):")
dist(0, 24, "ALL hours (my first number)")
dist(16, 24, "16:00-24:00 UTC (pre-tip + tip)")
dist(20, 24, "20:00-24:00 UTC (the selection window)")
dist(0, 8,  "00:00-08:00 UTC (overnight/quiet)")
dist(8, 16, "08:00-16:00 UTC (daytime)")
