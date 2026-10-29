"""EXP-030 §13 TIME-TO-REPRICE. EXP-029 found no response, but measured only the FIRST tick after
the flag -- a 5.9-minute median window. Absorption may be slower than that. This measures the move
from the last pre-event price out to +5/+15/+30/+60/+120 min and to the last pre-game price.

Every horizon keeps its own matched placebo: a same-length window on the same rung that does NOT
contain the event. A horizon effect only counts if it beats its OWN placebo -- longer windows drift
more, so comparing a 2h event move against a 6min placebo would manufacture the finding.

Sign: POSITIVE = over got more expensive = market moved TOWARD the model."""
import sqlite3, datetime as dt, random, statistics as st, math, bisect
random.seed(20260815)
tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=300)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
names = {}
for (n,) in tick.execute("SELECT DISTINCT player FROM obs"): names.setdefault(str(n).lower(), n)
def resolve(p):
    k = str(p).lower()
    return names.get(k) or next((v for kk, v in names.items() if k and (k in kk or kk in k)), None)
clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
ev = clv.execute("SELECT date,player,stat,flag_line,flagged_at FROM clv WHERE flagged_at IS NOT NULL "
                 "AND flag_line IS NOT NULL AND date BETWEEN ? AND ?", (days[0], days[-1])).fetchall()
HZ = [5, 15, 30, 60, 120, None]            # None = last pre-game observation
def p_of(o):
    o = float(o); return 1.0/o if o > 1.0 else None
res = {h: {"ev": [], "pl": []} for h in HZ}
used = 0
for date, player, stat, fline, fat in ev:
    P = resolve(player)
    if P is None: continue
    ser = tick.execute("SELECT collected_at, odds FROM obs WHERE d=? AND player=? AND stat=? "
                       "AND line=? AND side='over' AND book='fd' ORDER BY collected_at",
                       (date, P, stat, float(fline))).fetchall()
    if len(ser) < 8: continue
    ts = [dt.datetime.fromisoformat(str(s[0])) for s in ser]
    pr = [p_of(s[1]) for s in ser]
    T = dt.datetime.fromisoformat(str(fat))
    k = bisect.bisect_left(ts, T)
    if k == 0 or k >= len(ts): continue
    base = pr[k-1]
    if base is None: continue
    used += 1
    for h in HZ:
        if h is None:
            j = len(ts) - 1
        else:
            j = bisect.bisect_left(ts, ts[k-1] + dt.timedelta(minutes=h)) - 1
            if j <= k - 1: continue
        if j >= len(ts) or pr[j] is None: continue
        span = (ts[j] - ts[k-1]).total_seconds()
        if span <= 0: continue
        res[h]["ev"].append(pr[j] - base)
        got = None
        for _ in range(80):
            i = random.randrange(0, len(ts) - 1)
            jj = bisect.bisect_left(ts, ts[i] + dt.timedelta(seconds=span)) - 1
            if jj <= i or jj >= len(ts): continue
            g = (ts[jj] - ts[i]).total_seconds()
            if not (span * 0.6 <= g <= span * 1.4): continue
            if ts[i] < T < ts[jj]: continue
            if pr[i] is None or pr[jj] is None: continue
            got = pr[jj] - pr[i]; break
        res[h]["pl"].append(got)
print(f"events contributing at least one horizon: {used}\n")
print(f"{'horizon':>10s} {'n':>5s} {'EVENT mean':>12s} {'PLACEBO mean':>13s} {'paired diff':>12s} "
      f"{'t':>7s} {'moved%':>8s}")
for h in HZ:
    e = res[h]["ev"]; p = res[h]["pl"]
    pairs = [(a, b) for a, b in zip(e, p) if b is not None]
    if len(pairs) < 12: 
        print(f"{str(h or 'pre-game'):>10s} {len(e):5d}   thin"); continue
    d = [a - b for a, b in pairs]
    m = st.mean(d); se = (st.pstdev(d)/math.sqrt(len(d))) or 1e-12
    mv = sum(1 for x in e if abs(x) > 1e-9)/len(e)*100
    print(f"{str(h or 'pre-game'):>10s} {len(pairs):5d} {st.mean([a for a,_ in pairs])*100:+11.2f}pp "
          f"{st.mean([b for _,b in pairs])*100:+12.2f}pp {m*100:+11.3f}pp {m/se:+7.2f} {mv:7.1f}%")
print("\n  a real absorption effect would GROW with horizon and beat its own placebo at t>2.")
