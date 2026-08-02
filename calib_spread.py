"""Solve the rating-SPREAD multiplier that makes the tournament markets calibrated.

Why this and not sigma: sigma tested clean at every skill level (elite assigned 2.730 vs realized
2.711, z-sd 0.97-1.01 in all six rating bins), so it is not the cause. What remains is the rating
SPREAD. K_SHRINK compresses each rating toward the field — correct for minimising squared error of
a point estimate, but a rank simulation is NON-LINEAR, so feeding it shrunk point estimates makes
the field look more homogeneous than it is and compresses every tournament probability toward its
base rate. That is exactly the measured symptom: slope >1 on make-cut, top-20, top-10, top-5,
outright and 72-hole matchups.

This is the mirror of the birdie fix (which needed MORE shrinkage, DISPERSION=0.552): tail
probabilities of a threshold-of-independent-events model came out too WIDE, while tail
probabilities of a rank model come out too NARROW.

Discipline: solve on 2025 events ONLY, then report 2026 as a holdout. The birdie exercise showed a
constant solved on the wrong scale can look fine and fix nothing, so the objective here is the
calibration SLOPE of the actual market, not the rating's own error.
"""
import math
import os
import random
import shutil
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_spread.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP
random.seed(4)
SIMS = 6000


def events(lo, hi):
    con = sqlite3.connect(RU.DB)
    e = con.execute("SELECT event_id, MIN(date) d FROM rounds GROUP BY event_id "
                    "HAVING d >= ? AND d <= ? ORDER BY d", (lo, hi)).fetchall()
    con.close()
    return e


rows_all = RU.all_rows()
CACHE = {}


def event_data(eid, d0):
    """(ratings, field, realized strict positions, r1 scores) — fit once, reuse per spread."""
    if eid in CACHE:
        return CACHE[eid]
    con = sqlite3.connect(RU.DB)
    rr = con.execute("SELECT player, SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                     "score>0 GROUP BY player", (eid,)).fetchall()
    r1 = {RU.norm(p): s for p, s in con.execute(
        "SELECT player, score FROM rounds WHERE event_id=? AND rnd=1 AND score>0", (eid,))}
    con.close()
    tot = {RU.norm(p): (t, n) for p, t, n in rr if t}
    full = {p: t for p, (t, n) in tot.items() if n == 4}
    if len(full) < 50 or len(tot) < 100:
        CACHE[eid] = None
        return None
    R, _ = RU.fit(asof=d0, rows=rows_all)
    Rn = {RU.norm(k): v for k, v in R.items()}
    field = [p for p in tot if p in Rn]
    if len(field) < 100:
        CACHE[eid] = None
        return None
    order = sorted(full.items(), key=lambda kv: (kv[1], kv[0]))
    pos = {p: i + 1 for i, (p, _t) in enumerate(order)}
    CACHE[eid] = (Rn, field, full, pos, r1)
    return CACHE[eid]


def stretch(Rn, S):
    """Widen every rating deviation from the field mean by S. S=1 is today's model."""
    if abs(S - 1.0) < 1e-9:
        return Rn
    vals = [v[0] for v in Rn.values()]
    m = st.mean(vals) if vals else 0.0
    return {k: (m + S * (v[0] - m), v[1], v[2]) for k, v in Rn.items()}


def slopes_for(evs, S, markets=("top20", "top10", "cut", "win")):
    buckets = defaultdict(list)
    mp = []
    for eid, d0 in evs:
        d = event_data(eid, d0)
        if not d:
            continue
        Rn, field, full, pos, _r1 = d
        Rs = stretch(Rn, S)
        sim = RU.simulate(Rs, field, n_sims=SIMS, seed=13)
        if not sim:
            continue
        for p in field:
            v = sim.get(p)
            if not v:
                continue
            pp = pos.get(p, 10 ** 6)
            buckets["cut"].append((v["cut"], 1.0 if p in full else 0.0))
            buckets["top20"].append((v["top20"], 1.0 if pp <= 20 else 0.0))
            buckets["top10"].append((v["top10"], 1.0 if pp <= 10 else 0.0))
            buckets["win"].append((v["win"], 1.0 if pp == 1 else 0.0))
        fl = [p for p in field if p in full]
        for _ in range(250):
            a, b = random.choice(fl), random.choice(fl)
            if a == b or full[a] == full[b]:
                continue
            pr = RU.matchup_prob(Rs, a, b, rounds=4)
            if pr is not None:
                mp.append((pr, 1.0 if full[a] < full[b] else 0.0))
    buckets["match72"] = mp

    def sl(pairs, nb=7):
        if len(pairs) < 300:
            return None
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
        return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else None

    return {k: sl(v) for k, v in buckets.items()}


TUNE = events("2025-01-01", "2025-12-31")
HOLD = events("2026-01-01", "2026-12-31")
print("tune events (2025): %d | holdout events (2026): %d" % (len(TUNE), len(HOLD)))
print()
print("=== TUNE on 2025 ONLY: slope by rating-spread multiplier S ===")
print("  %5s  %9s %9s %9s %9s %9s   %s" % ("S", "match72", "cut", "top20", "top10", "win",
                                           "mean |slope-1|"))
best = None
for S in (1.0, 1.15, 1.3, 1.45, 1.6, 1.8):
    r = slopes_for(TUNE, S)
    got = {k: v for k, v in r.items() if v is not None}
    err = st.mean([abs(v - 1.0) for v in got.values()]) if got else 9
    print("  %5.2f  %9s %9s %9s %9s %9s   %.4f"
          % (S,
             "%.3f" % r["match72"] if r.get("match72") else "n/a",
             "%.3f" % r["cut"] if r.get("cut") else "n/a",
             "%.3f" % r["top20"] if r.get("top20") else "n/a",
             "%.3f" % r["top10"] if r.get("top10") else "n/a",
             "%.3f" % r["win"] if r.get("win") else "n/a", err))
    if best is None or err < best[1]:
        best = (S, err)
print()
print("  BEST on the tune set: S = %.2f (mean |slope-1| = %.4f)" % best)
print()
print("=== HOLDOUT 2026 — does it generalise? ===")
for S in (1.0, best[0]):
    r = slopes_for(HOLD, S)
    got = {k: v for k, v in r.items() if v is not None}
    err = st.mean([abs(v - 1.0) for v in got.values()]) if got else 9
    tag = "  <- today's model" if S == 1.0 else "  <- tuned"
    print("  S=%.2f  match72 %s  cut %s  top20 %s  top10 %s  win %s   mean|slope-1| %.4f%s"
          % (S,
             "%.3f" % r["match72"] if r.get("match72") else "n/a",
             "%.3f" % r["cut"] if r.get("cut") else "n/a",
             "%.3f" % r["top20"] if r.get("top20") else "n/a",
             "%.3f" % r["top10"] if r.get("top10") else "n/a",
             "%.3f" % r["win"] if r.get("win") else "n/a", err, tag))
