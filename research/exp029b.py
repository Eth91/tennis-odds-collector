"""EXP-029 §10 PRICE RESPONSE AFTER THE EVENT, against a §26 matched placebo.

THE PLACEBO IS THE EXPERIMENT. Prices drift constantly; measuring movement across an event and
calling it a response is the easiest way to manufacture a result. For each event straddle
(t_pre -> t_post) we draw SAME-DURATION straddles on the SAME rung that do NOT contain the event.

Implied probability, not American odds (American is discontinuous at even money).
Sign: POSITIVE = the over got more expensive = market moved TOWARD the model."""
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
print(f"{len(ev)} candidate events", flush=True)

def p_of(o):
    o = float(o)
    return 1.0/o if o > 1.0 else None

real, plac, meta = [], [], []
skip = {"unresolved": 0, "thin series": 0, "no straddle": 0, "no placebo": 0}
for idx, (date, player, stat, fline, fat) in enumerate(ev):
    P = resolve(player)
    if P is None: skip["unresolved"] += 1; continue
    ser = tick.execute("SELECT collected_at, odds FROM obs WHERE d=? AND player=? AND stat=? "
                       "AND line=? AND side='over' AND book='fd' ORDER BY collected_at",
                       (date, P, stat, float(fline))).fetchall()
    if len(ser) < 6: skip["thin series"] += 1; continue
    ts = [dt.datetime.fromisoformat(str(s[0])) for s in ser]
    pr = [p_of(s[1]) for s in ser]
    T = dt.datetime.fromisoformat(str(fat))
    k = bisect.bisect_left(ts, T)
    if k == 0 or k >= len(ts): skip["no straddle"] += 1; continue
    if pr[k-1] is None or pr[k] is None: skip["thin series"] += 1; continue
    dur = (ts[k] - ts[k-1]).total_seconds()
    real.append(pr[k] - pr[k-1])
    # placebo: bounded random sampling, never straddling the event
    got = None
    for _ in range(60):
        i = random.randrange(0, len(ts) - 1)
        j = bisect.bisect_left(ts, ts[i] + dt.timedelta(seconds=dur))
        if j <= i or j >= len(ts): continue
        gap = (ts[j] - ts[i]).total_seconds()
        if not (dur * 0.5 <= gap <= dur * 1.5): continue
        if ts[i] < T < ts[j]: continue
        if pr[i] is None or pr[j] is None: continue
        got = pr[j] - pr[i]; break
    if got is None: skip["no placebo"] += 1
    plac.append(got); meta.append((stat, dur / 60.0, len(ser)))
    if idx % 50 == 0: print(f"  ..{idx}/{len(ev)}", flush=True)

pairs = [(r, p) for r, p in zip(real, plac) if p is not None]
print(f"\nevents with a measurable straddle at the flagged rung (FanDuel): {len(real)}")
print(f"  skipped: {skip}")
print(f"  with a matched placebo: {len(pairs)}\n")
def summ(v, lab):
    v = [x for x in v if x is not None]
    if not v: print(f"  {lab}: none"); return
    print(f"  {lab:26s} mean {st.mean(v)*100:+6.2f}pp  median {st.median(v)*100:+6.2f}pp  "
          f"sd {st.pstdev(v)*100:5.2f}  moved {sum(1 for x in v if abs(x)>1e-9)}/{len(v)}")
print("=== MOVEMENT IN IMPLIED PROBABILITY (positive = over got more expensive) ===")
summ(real, "EVENT straddle"); summ([p for _, p in pairs], "PLACEBO (same duration)")
d = [r - p for r, p in pairs]
if d:
    m = st.mean(d); se = (st.pstdev(d)/math.sqrt(len(d))) or 1e-12
    print(f"\n  paired diff (event - placebo): {m*100:+.3f}pp   t = {m/se:+.2f}   n = {len(d)}")
    print(f"  -> {'EVENT RESPONSE ABOVE DRIFT' if abs(m/se) > 2 else 'NO event response above ordinary drift'}")
mv = sum(1 for x in real if abs(x) > 1e-9); pmv = sum(1 for _, p in pairs if abs(p) > 1e-9)
print(f"\n  ANY odds change: event {mv}/{len(real)} ({mv/max(len(real),1)*100:.1f}%)  "
      f"vs placebo {pmv}/{max(len(pairs),1)} ({pmv/max(len(pairs),1)*100:.1f}%)")
bys = {}
for (s, dur, n), r in zip(meta, real): bys.setdefault(s, []).append(r)
print("\n=== by stat ===")
for s, v in sorted(bys.items()):
    if len(v) >= 8:
        print(f"  {s:9s} n={len(v):3d} mean {st.mean(v)*100:+6.2f}pp moved {sum(1 for x in v if abs(x)>1e-9)}/{len(v)}")
if meta: print(f"\n  median straddle duration: {st.median([m[1] for m in meta]):.1f} min")
