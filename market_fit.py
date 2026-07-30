"""Which PGA market is this model actually built for? Measured, per market.

The birdie test showed the model's TAIL probabilities are systematically too extreme (reliability
slope 0.61) because p_x_or_more assumes independent holes. The obvious question is whether the
same disease affects the TOURNAMENT simulator, which is what prices top-5/10/20 and outrights.
That has never been tested — so test it the same way, against outcomes.

Reliability slope of realized frequency on predicted probability, per market, on as-of fits so
nothing measured is in the training set:
    slope ~ 1.0  the probabilities mean what they say
    slope < 1.0  too extreme — confident predictions do not come true at their stated rate,
                 and that is precisely where flagged edges live

Matchups are included as the control: they are pure ORDERING, the model's measured strength, and
they sit in the middle of the distribution rather than the tail.
"""
import math
import random
import sqlite3
import statistics as st
from collections import defaultdict

import os
import shutil

import pga_ruler as RU

# SNAPSHOT: pga_model.sqlite is tracked and the wnba loop resets/replays it, so a multi-minute
# reader gets "no such table: rounds" or "readonly database" mid-run. Read from a private copy.
_SNAP = os.path.expanduser("~/pga_model_mf.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP

random.seed(5)
SIMS = 4000

con = sqlite3.connect(RU.DB)
evs = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                  "HAVING d >= '2026-01-01' ORDER BY d").fetchall()
con.close()
rows_all = RU.all_rows()

buckets = defaultdict(list)          # market -> [(predicted, realized)]
n_ev = 0
for eid, d0 in evs:
    con = sqlite3.connect(RU.DB)
    rr = con.execute("SELECT player, SUM(score), COUNT(*) FROM rounds WHERE event_id=? "
                     "AND score>0 GROUP BY player", (eid,)).fetchall()
    con.close()
    tot = {RU.norm(p): (t, n) for p, t, n in rr if t}
    full = {p: t for p, (t, n) in tot.items() if n == 4}
    if len(full) < 50 or len(tot) < 100:
        continue
    R, _ = RU.fit(asof=d0, rows=rows_all)
    Rn = {RU.norm(k): v for k, v in R.items()}
    field = [p for p in tot if p in Rn]
    if len(field) < 100:
        continue
    sim = RU.simulate(Rn, field, n_sims=SIMS, seed=9)
    if not sim:
        continue
    n_ev += 1
    # realized finishing position among the whole field; missed-cut players rank behind everyone
    # STRICT ranking, to match what the simulator produces. The first version used
    # pos = 1 + count(strictly lower), i.e. ties SHARE the better rank — which made realized
    # "top 20" average 22.7 players per event and every tournament market read falsely "too
    # timid". simulate() ranks continuous draws, so exact ties never occur and its top20 is
    # exactly 20 players; the realized side must be defined the same way. Ties are broken by
    # total then name, which is arbitrary but unbiased.
    order = sorted(full.items(), key=lambda kv: (kv[1], kv[0]))
    pos = {p: i + 1 for i, (p, t) in enumerate(order)}          # strict, ties broken arbitrarily
    # ties-inclusive realized position: 1 + how many are STRICTLY better, so a tie shares the
    # better rank — the definition the "(Incl. Ties)" products settle on
    tpos = {p: 1 + sum(1 for _q, tq in full.items() if tq < t) for p, t in full.items()}
    for p in field:
        v = sim.get(p) or sim.get(RU.norm(p))
        if not v:
            continue
        made = p in full
        pp = pos.get(p, 10 ** 6)
        buckets["make_cut"].append((v["cut"], 1.0 if made else 0.0))
        buckets["top20"].append((v["top20"], 1.0 if pp <= 20 else 0.0))
        buckets["top10"].append((v["top10"], 1.0 if pp <= 10 else 0.0))
        buckets["top5"].append((v["top5"], 1.0 if pp <= 5 else 0.0))
        buckets["outright"].append((v["win"], 1.0 if pp == 1 else 0.0))
        tp = tpos.get(p, 10 ** 6)
        if "top20_ties" in v:
            buckets["top20_ties"].append((v["top20_ties"], 1.0 if tp <= 20 else 0.0))
            buckets["top10_ties"].append((v["top10_ties"], 1.0 if tp <= 10 else 0.0))
            buckets["top5_ties"].append((v["top5_ties"], 1.0 if tp <= 5 else 0.0))
            buckets["win_ties"].append((v["win_ties"], 1.0 if tp == 1 else 0.0))
    # round-1 scores loaded ONCE per event. v1 opened a fresh connection per PAIR — 600 per
    # event, ~13k total — which is both slow and what exposed it to the DB swap.
    con = sqlite3.connect(RU.DB)
    r1 = {RU.norm(p): sc for p, sc in con.execute(
        "SELECT player, score FROM rounds WHERE event_id=? AND rnd=1 AND score>0", (eid,))}
    con.close()
    # matchup control: pairs of players who both completed 72 holes
    fl = [p for p in field if p in full]
    for _ in range(300):
        a, b = random.choice(fl), random.choice(fl)
        if a == b or full[a] == full[b]:
            continue
        pr = RU.matchup_prob(Rn, a, b, rounds=4)
        if pr is not None:
            buckets["matchup_72h"].append((pr, 1.0 if full[a] < full[b] else 0.0))
    for _ in range(300):
        a, b = random.choice(fl), random.choice(fl)
        if a == b:
            continue
        pr = RU.matchup_prob(Rn, a, b, rounds=1)
        if pr is None:
            continue
        ra, rb = r1.get(a), r1.get(b)
        if ra and rb and ra != rb:
            buckets["matchup_r1"].append((pr, 1.0 if ra < rb else 0.0))

print("events used: %d" % n_ev)


def slope(pairs, nb=8):
    if len(pairs) < 300:
        return None, None, None, len(pairs)
    srt = sorted(pairs)
    sz = len(srt) // nb
    xs, ys = [], []
    for i in range(nb):
        ch = srt[i * sz:(i + 1) * sz] if i < nb - 1 else srt[i * sz:]
        if ch:
            xs.append(st.mean(c[0] for c in ch))
            ys.append(st.mean(c[1] for c in ch))
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    sl = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0
    return sl, st.mean(c[0] for c in srt), st.mean(c[1] for c in srt), len(pairs)


ORDER = ["matchup_72h", "matchup_r1", "make_cut", "top20", "top10", "top5", "outright",
         "top20_ties", "top10_ties", "top5_ties", "win_ties"]
print()
print("  %-13s %7s %9s %9s %8s   %s" % ("market", "n", "pred mean", "real mean", "slope",
                                        "reads as"))
res = {}
for k in ORDER:
    sl, pm, rm, n = slope(buckets.get(k) or [])
    if sl is None:
        print("  %-13s %7d  (too few)" % (k, n))
        continue
    res[k] = sl
    verdict = ("CALIBRATED" if 0.85 <= sl <= 1.15 else
               "too extreme" if sl < 0.85 else "too timid")
    print("  %-13s %7d %9.4f %9.4f %8.3f   %s" % (k, n, pm, rm, sl, verdict))
print()
print("  slope 1.0 = probabilities mean what they say; below 0.85 = confident predictions do")
print("  not come true at their stated rate, which is exactly where flagged edges sit.")
print()
if res:
    print("  ranked by calibration (closest to 1.0 first):")
    for k, v in sorted(res.items(), key=lambda kv: abs(kv[1] - 1.0)):
        print("     %-13s slope %.3f" % (k, v))

# A slope extrapolated into the tails can mislead, and the bets we would actually place live in
# the tails — so print the observed curve instead of trusting the line.
print()
print("RELIABILITY CURVES (observed, not extrapolated)")
for k in ("matchup_72h", "matchup_r1", "top20", "top10", "outright"):
    pr = buckets.get(k) or []
    if len(pr) < 300:
        continue
    srt = sorted(pr)
    nb = 8
    sz = len(srt) // nb
    print("  %s" % k)
    for i in range(nb):
        ch = srt[i * sz:(i + 1) * sz] if i < nb - 1 else srt[i * sz:]
        if not ch:
            continue
        px = st.mean(c[0] for c in ch)
        py = st.mean(c[1] for c in ch)
        gap = py - px
        bar = "over-predicted" if gap < -0.01 else ("under-predicted" if gap > 0.01 else "ok")
        print("     d%d  pred %.4f  real %.4f  %+.4f  %s" % (i + 1, px, py, gap, bar))
