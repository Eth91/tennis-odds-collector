"""Was matchup_r1's slope of 0.310 real, or an artefact of cut-maker selection?

market_fit sampled round-1 pairs from `fl = [p for p in field if p in full]` — players who
completed FOUR rounds, i.e. cut-makers. That conditions on an outcome downstream of round 1:
cut-makers are a stronger, more homogeneous subset whose R1 scores are compressed, so confident
predictions fail more often and the slope reads too extreme.

calib_spread1r sampled ALL players with an R1 score and got the opposite sign (slope 1.16 on 2025,
1.35-1.41 on 2026 — too TIMID). Same market, same constant, opposite verdict.

Measure both on identical events and pairs so the only difference is the selection.
"""
import os, random, shutil, sqlite3, statistics as st
import pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_r1.sqlite")
shutil.copyfile(str(RU.DB), _SNAP); RU.DB = _SNAP
rows_all = RU.all_rows()
con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2026-01-01' ORDER BY d").fetchall()
con.close()

def sl(pairs, nb=7):
    if len(pairs) < 400: return None
    srt = sorted(pairs); sz = len(srt)//nb; xs, ys = [], []
    for i in range(nb):
        ch = srt[i*sz:(i+1)*sz] if i < nb-1 else srt[i*sz:]
        if ch: xs.append(st.mean(c[0] for c in ch)); ys.append(st.mean(c[1] for c in ch))
    mx, my = st.mean(xs), st.mean(ys); den = sum((x-mx)**2 for x in xs)
    return (sum((x-mx)*(y-my) for x, y in zip(xs, ys))/den) if den else None

cut_only, everyone = [], []
for eid, d0 in evs:
    con = sqlite3.connect(RU.DB)
    r1 = {RU.norm(p): s for p, s in con.execute(
        "SELECT player, score FROM rounds WHERE event_id=? AND rnd=1 AND score>0", (eid,))}
    n4 = {RU.norm(p) for p, n in con.execute(
        "SELECT player, COUNT(*) FROM rounds WHERE event_id=? AND score>0 GROUP BY player", (eid,))
        if n == 4}
    con.close()
    if len(r1) < 80: continue
    R, _ = RU.fit(asof=d0, rows=rows_all)
    Rn = {RU.norm(k): v for k, v in R.items()}
    allp = [p for p in r1 if p in Rn]
    cutp = [p for p in allp if p in n4]
    if len(cutp) < 40: continue
    rr = random.Random(21)
    for src, sink in ((cutp, cut_only), (allp, everyone)):
        for _ in range(300):
            a, b = rr.choice(src), rr.choice(src)
            if a == b or r1[a] == r1[b]: continue
            p = RU.matchup_prob(Rn, a, b, rounds=1)
            if p is not None:
                sink.append((p, 1.0 if r1[a] < r1[b] else 0.0))

print("ROUND-1 MATCHUP calibration, 2026, SPREAD=%.2f" % RU.SPREAD)
print("  %-34s %7s %9s" % ("pair pool", "n", "slope"))
print("  %-34s %7d %9s" % ("cut-makers only (market_fit's pool)", len(cut_only),
                           "%.3f" % sl(cut_only) if sl(cut_only) else "n/a"))
print("  %-34s %7d %9s" % ("everyone who played round 1", len(everyone),
                           "%.3f" % sl(everyone) if sl(everyone) else "n/a"))
print()
a, b = sl(cut_only), sl(everyone)
if a and b and abs(a-1) > abs(b-1) + 0.15:
    print("  CONFIRMED: restricting to cut-makers conditions on a post-round-1 outcome and")
    print("  distorts the slope. The unselected pool is the honest number, and it says the model")
    print("  is too TIMID on single rounds — the same direction as every other market — so no")
    print("  separate single-round constant is needed.")
elif a and b:
    print("  NOT the explanation: both pools agree, so the single-round result stands on its own.")
