"""EXP-029 §10 PRICE RESPONSE AFTER THE EVENT, against a §26 matched placebo.

THE PLACEBO IS THE EXPERIMENT. Prices drift constantly; measuring movement across an event and
calling it a response is the single easiest way to manufacture a result. For every event straddle
(t_pre -> t_post) we draw a SAME-DURATION straddle on the SAME player-stat-day that does NOT
contain the event, and compare. Without that, any number below is meaningless.

Movement is measured in IMPLIED PROBABILITY, not American odds: American is discontinuous at even
money and would rank a 1.0pp move as 5x worse than an 11.6pp move (a real bug already hit here).

Sign convention: POSITIVE = the over got MORE expensive = the market moved TOWARD the model."""
import sqlite3, datetime as dt, random, statistics as st, math
random.seed(20260815)                      # fixed: the placebo must be reproducible

tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=180)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
names = {}
for (n,) in tick.execute("SELECT DISTINCT player FROM obs"): names.setdefault(str(n).lower(), n)
def resolve(p):
    k = str(p).lower()
    if k in names: return names[k]
    return next((v for kk, v in names.items() if k and (k in kk or kk in k)), None)

clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
ev = clv.execute("SELECT date,player,stat,flag_line,flagged_at FROM clv WHERE flagged_at IS NOT NULL "
                 "AND flag_line IS NOT NULL AND date BETWEEN ? AND ?", (days[0], days[-1])).fetchall()

def dec2p(o):
    o = float(o)
    return 1.0/o if o > 1.0 else None      # decimal -> implied prob (incl. vig)

real, plac, meta = [], [], []
skip = {"unresolved": 0, "no series at the rung": 0, "no straddle": 0, "no placebo window": 0}
for date, player, stat, fline, fat in ev:
    P = resolve(player)
    if P is None: skip["unresolved"] += 1; continue
    series = tick.execute(
        "SELECT collected_at, odds, book FROM obs WHERE d=? AND player=? AND stat=? AND line=? "
        "AND side='over' ORDER BY collected_at", (date, P, stat, float(fline))).fetchall()
    if len(series) < 4: skip["no series at the rung"] += 1; continue
    pre = [s for s in series if str(s[0]) < str(fat)]
    post = [s for s in series if str(s[0]) > str(fat)]
    if not pre or not post: skip["no straddle"] += 1; continue
    a, b = pre[-1], post[0]
    pa, pb = dec2p(a[1]), dec2p(b[1])
    if pa is None or pb is None: skip["no series at the rung"] += 1; continue
    dur = (dt.datetime.fromisoformat(str(b[0])) - dt.datetime.fromisoformat(str(a[0]))).total_seconds()
    real.append(pb - pa)
    # matched placebo: same duration, same rung, NOT containing the event
    cands = []
    for i in range(len(series) - 1):
        t0 = dt.datetime.fromisoformat(str(series[i][0]))
        for j in range(i + 1, len(series)):
            t1 = dt.datetime.fromisoformat(str(series[j][0]))
            gap = (t1 - t0).total_seconds()
            if gap > dur * 1.5: break
            if gap >= dur * 0.5 and not (str(series[i][0]) < str(fat) < str(series[j][0])):
                cands.append((series[i], series[j]))
    if not cands: skip["no placebo window"] += 1; plac.append(None)
    else:
        c0, c1 = random.choice(cands)
        q0, q1 = dec2p(c0[1]), dec2p(c1[1])
        plac.append((q1 - q0) if (q0 and q1) else None)
    meta.append((stat, dur/60.0, len(series)))

pairs = [(r, p) for r, p in zip(real, plac) if p is not None]
print(f"events with a measurable straddle at the flagged rung: {len(real)}")
print(f"  skipped: {skip}")
print(f"  with a matched placebo: {len(pairs)}\n")
def summ(v, lab):
    v = list(v)
    if not v: print(f"  {lab}: none"); return
    m = st.mean(v); sd = st.pstdev(v) or 1e-12
    print(f"  {lab:26s} mean {m*100:+6.2f}pp  median {st.median(v)*100:+6.2f}pp  "
          f"sd {sd*100:5.2f}  |moved|>0: {sum(1 for x in v if abs(x)>1e-9)}/{len(v)}")
print("=== MOVEMENT IN IMPLIED PROBABILITY (positive = over got more expensive) ===")
summ(real, "EVENT straddle")
summ([p for _, p in pairs], "PLACEBO (same duration)")
d = [r - p for r, p in pairs]
if d:
    m = st.mean(d); se = (st.pstdev(d) / math.sqrt(len(d))) or 1e-12
    print(f"\n  paired difference (event - placebo): {m*100:+.3f}pp   t = {m/se:+.2f}   n = {len(d)}")
    print(f"  -> {'EVENT MOVES THE PRICE MORE THAN DRIFT' if abs(m/se) > 2 else 'NO detectable event response above ordinary drift'}")
print("\n=== how often does the price move AT ALL across the event? ===")
mv = sum(1 for x in real if abs(x) > 1e-9)
print(f"  {mv}/{len(real)} ({mv/len(real)*100:.1f}%) of event straddles show ANY odds change")
pmv = sum(1 for _, p in pairs if abs(p) > 1e-9)
print(f"  {pmv}/{len(pairs)} ({pmv/len(pairs)*100:.1f}%) of placebo straddles show ANY odds change")
print("\n=== by stat ===")
bys = {}
for (s, dur, n), r in zip(meta, real): bys.setdefault(s, []).append(r)
for s, v in sorted(bys.items()):
    if len(v) >= 10:
        print(f"  {s:9s} n={len(v):3d}  mean {st.mean(v)*100:+6.2f}pp  "
              f"moved {sum(1 for x in v if abs(x)>1e-9)}/{len(v)}")
print(f"\n  median straddle duration: {st.median([m[1] for m in meta]):.1f} min")
