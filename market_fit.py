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

import pga_ruler as RU

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
    pos = {p: i + 1 for i, (p, t) in enumerate(order)}
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
        con = sqlite3.connect(RU.DB)
        ra = con.execute("SELECT score FROM rounds WHERE event_id=? AND LOWER(player)=? AND "
                         "rnd=1", (eid, a)).fetchone()
        rb = con.execute("SELECT score FROM rounds WHERE event_id=? AND LOWER(player)=? AND "
                         "rnd=1", (eid, b)).fetchone()
        con.close()
        if ra and rb and ra[0] and rb[0] and ra[0] != rb[0]:
            buckets["matchup_r1"].append((pr, 1.0 if ra[0] < rb[0] else 0.0))

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


ORDER = ["matchup_72h", "matchup_r1", "make_cut", "top20", "top10", "top5", "outright"]
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
    best = sorted(res.items(), key=lambda kv: -min(kv[1], 2 - kv[1]))
    print("  ranked by calibration (closest to 1.0 first):")
    for k, v in sorted(res.items(), key=lambda kv: abs(kv[1] - 1.0)):
        print("     %-13s slope %.3f" % (k, v))
