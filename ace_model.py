#!/usr/bin/env python3
"""ACE MODEL v1 + chronological backtest. Train <= 2024, test 2025. Strictly leakage-safe.

STRUCTURE. An ace count is a RATE times a WORKLOAD, and conflating them is the classic error:
a model that predicts counts without conditioning on service points is largely predicting match
length wearing a serving costume.

    expected_aces = rate(server, returner, surface, indoor) * expected_service_points

RATE is a log5 combine on the surface baseline - the server's own ace rate scaled by how hard the
returner is to ace, both measured relative to that surface:
    rate = base_s * (server_rate / base_s) * (returner_conceded / base_s)
Both inputs are empirical-Bayes shrunk toward the surface baseline, because a player with 200
service points has a rate estimate that is mostly noise and must not be trusted like one with
20,000. Shrinkage constants are fitted on TRAIN ONLY.

WORKLOAD is predicted separately from best_of and the two players' historical service-point loads.

EVERY input is built from matches STRICTLY BEFORE the match being predicted, accumulated in date
order with exponential decay. Nothing is fitted on 2025 and nothing looks forward.

FOUR BASELINES, because a model must beat the cheap thing it replaces, not just beat zero:
    global mean        one number for everyone
    player mean        the server's own historical mean count - a genuinely strong baseline
    rate x ACTUAL svpt isolates the RATE model by handing it the true workload
    full model         rate x PREDICTED svpt - the only one usable before a match
"""
import math
import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parent / "tennis_ace.sqlite"
HALF_LIFE_D = 540.0          # fitted on train below
TEST_YEAR = 2025

con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=60)
rows = con.execute(
    "SELECT date, year, surface, indoor, best_of, player, opp, aces, svpt, sv_gms "
    "FROM ace_pm WHERE svpt > 0 AND surface IS NOT NULL AND surface != '' ORDER BY date").fetchall()
con.close()
print("player-match rows: %d" % len(rows))


def days(a, b):
    ya, ma, da = int(a[:4]), int(a[5:7]), int(a[8:10])
    yb, mb, db_ = int(b[:4]), int(b[5:7]), int(b[8:10])
    return (yb - ya) * 365.25 + (mb - ma) * 30.44 + (db_ - da)


# surface baselines from TRAIN ONLY
base = {}
for s in {r[2] for r in rows}:
    v = [(r[7], r[8]) for r in rows if r[2] == s and r[1] <= 2024]
    if v:
        base[s] = sum(a for a, _ in v) / max(sum(p for _, p in v), 1)
print("surface ace-per-service-point baselines (train only):")
for s, b in sorted(base.items(), key=lambda kv: -kv[1]):
    print("   %-8s %.4f" % (s, b))


def run(k_serve, k_ret, hl, report=False):
    """One pass in date order. Predict, then learn - never the reverse."""
    sv = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))   # player->surf->[ace,svpt,last]
    rt = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))   # returner conceded
    load = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))        # player->bo->[svpt,n]
    pmean = defaultdict(lambda: [0.0, 0.0])                            # player->[aces,n]
    out = []
    for d, yr, surf, indoor, bo, pl, opp, aces, svpt, gms in rows:
        b = base.get(surf)
        if not b:
            continue

        def decayed(store, key, s2):
            a, p, last = store[key][s2]
            if last is None:
                return 0.0, 0.0
            w = 0.5 ** (days(last, d) / hl)
            return a * w, p * w

        sa, sp = decayed(sv, pl, surf)
        ra, rp = decayed(rt, opp, surf)
        # empirical-Bayes shrink toward the surface baseline
        r_serve = (sa + k_serve * b) / (sp + k_serve)
        r_ret = (ra + k_ret * b) / (rp + k_ret)
        rate = b * (r_serve / b) * (r_ret / b)
        lp, ln = load[pl][bo]
        lo_, lon = load[opp][bo]
        exp_svpt = ((lp / ln) if ln >= 3 else 0.0) * 0.5 + ((lo_ / lon) if lon >= 3 else 0.0) * 0.5
        if exp_svpt <= 0:
            exp_svpt = 60.0 if bo == 3 else 100.0
        pm_a, pm_n = pmean[pl]
        if yr == TEST_YEAR:
            out.append(dict(aces=aces, svpt=svpt, bo=bo, surf=surf,
                            pred_rate_actual=rate * svpt,
                            pred_full=rate * exp_svpt,
                            pred_pmean=(pm_a / pm_n) if pm_n >= 5 else None,
                            rate=rate, exp_svpt=exp_svpt))
        # learn AFTER predicting
        for store, key, a_, p_ in ((sv, pl, aces, svpt), (rt, opp, aces, svpt)):
            A, P, last = store[key][surf]
            w = 0.5 ** (days(last, d) / hl) if last else 1.0
            store[key][surf] = [A * w + a_, P * w + p_, d]
        load[pl][bo][0] += svpt
        load[pl][bo][1] += 1
        pmean[pl][0] += aces
        pmean[pl][1] += 1
    return out


def mae(v, key):
    z = [(x["aces"] - x[key]) for x in v if x.get(key) is not None]
    return (sum(abs(e) for e in z) / len(z)) if z else float("nan"), len(z)


print("\n" + "=" * 88)
print("TUNE shrinkage + half-life on TRAIN ONLY (scored on 2024, which is inside train)")
print("=" * 88)
best = None
for hl in (270.0, 540.0, 1080.0):
    for ks in (200.0, 500.0, 1200.0):
        globals()["TEST_YEAR"] = 2024
        v = run(ks, ks, hl)
        m, _n = mae(v, "pred_rate_actual")
        if best is None or m < best[0]:
            best = (m, ks, hl)
        print("   half-life %6.0fd  k %6.0f  ->  MAE(rate x actual svpt) %.4f" % (hl, ks, m))
print("   best: k=%.0f half-life=%.0fd  (MAE %.4f)" % (best[1], best[2], best[0]))

globals()["TEST_YEAR"] = 2025
v = run(best[1], best[1], best[2])
print("\n" + "=" * 88)
print("CHRONOLOGICAL BACKTEST — train <= 2024, test 2025 (never touched during tuning)")
print("=" * 88)
acts = [x["aces"] for x in v]
gmean = st.mean([r[7] for r in rows if r[1] <= 2024])
print("   test rows: %d | actual aces mean %.2f sd %.2f" % (len(v), st.mean(acts), st.pstdev(acts)))
print()
print("   %-34s %8s %8s" % ("model", "MAE", "n"))
gm = sum(abs(x["aces"] - gmean) for x in v) / len(v)
print("   %-34s %8.4f %8d" % ("global mean (%.2f)" % gmean, gm, len(v)))
for key, lbl in (("pred_pmean", "player's own historical mean"),
                 ("pred_full", "MODEL rate x PREDICTED svpt"),
                 ("pred_rate_actual", "MODEL rate x ACTUAL svpt")):
    m, n = mae(v, key)
    print("   %-34s %8.4f %8d" % (lbl, m, n))
print()
sub = [x for x in v if x["pred_pmean"] is not None]
if sub:
    a = sum(abs(x["aces"] - x["pred_pmean"]) for x in sub) / len(sub)
    b = sum(abs(x["aces"] - x["pred_full"]) for x in sub) / len(sub)
    print("   like-for-like on the %d rows where BOTH exist:" % len(sub))
    print("      player mean %.4f   vs   model %.4f   -> %s by %.1f%%"
          % (a, b, "MODEL BETTER" if b < a else "player mean better", 100 * abs(a - b) / a))
print()
print("   by surface (model, rate x actual svpt):")
for s in ("Grass", "Hard", "Clay"):
    ss = [x for x in v if x["surf"] == s]
    if len(ss) > 50:
        print("      %-7s n=%5d  actual %5.2f  pred %5.2f  MAE %.3f"
              % (s, len(ss), st.mean([x["aces"] for x in ss]),
                 st.mean([x["pred_rate_actual"] for x in ss]),
                 sum(abs(x["aces"] - x["pred_rate_actual"]) for x in ss) / len(ss)))
