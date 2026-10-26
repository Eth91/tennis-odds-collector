#!/usr/bin/env python3
"""GM-011 — WIND x PLAYER. Does anyone actually handle wind better, and can we tell in advance?

GM-009 established that wind moves scoring (+0.44 strokes per 10 km/h) but not dispersion. The
charter's question is the next one: is the wind penalty the SAME for everyone, or do some players
pay less? If a measurable skill buys wind resistance, that is a course-and-conditions interaction
the model has no representation of.

TWO WAYS TO ASK IT, and they fail differently.

  LEG A  SKILL x WIND. Interpretable and well powered: does a player's prior-season DRIVE_ACC /
         SG_APP / DRIVE_DIST change how much a windy day costs them? Mechanisms are obvious --
         accuracy should matter more when the ball is being pushed around, and putting should
         matter less. Prior-SEASON skill only, so nothing from the round being predicted.
  LEG B  PLAYER-SPECIFIC WIND ABILITY, the charter's literal wording. Estimate each player's own
         wind slope, then ask whether it REPEATS. This is the shape that has already produced two
         illusions in this project -- "streaky players" (8% real, SIG_SHRINK) and "Sunday players"
         (93% sampling noise, GM-002) -- so it is tested the same way: between-player variance of
         the slope against the sampling noise in estimating it.

DESIGN
  target    resid = (round score - that round's field mean) - as-of rating
  wind      from the REBUILT pga_wx table (per-event-year venue, country-gated, curated majors),
            NOT the old bare-city geocode. Demeaned WITHIN EVENT, so a venue that is simply windy
            cannot masquerade as a wind effect -- only day-to-day variation at one venue counts.
  dev 2024 -> OOS 2025. 2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
  placebo   wind values shuffled BETWEEN event-rounds. GM-001 showed the empirical null t has
            sd 1.14 rather than 1.0 here, so significance is read against the placebo, never
            against the t table.
"""
import datetime as dt
import math
import sqlite3
from collections import defaultdict

import numpy as np

SKILLS = ["DRIVE_ACC", "DRIVE_DIST", "GIR", "SCRAMBLE", "SG_APP", "SG_ARG", "SG_OTT", "SG_PUTT"]

ix = sqlite3.connect("file:/home/ubuntu/pga_interactions.sqlite?mode=ro", uri=True, timeout=60)
rows = ix.execute("SELECT event_id, date, year, rnd, player, resid, %s FROM ix"
                  % ",".join(SKILLS)).fetchall()
ix.close()
wx = sqlite3.connect("file:pga_wx.sqlite?mode=ro", uri=True, timeout=60)
WIND = {(str(e), str(d)): float(w) for e, d, w in
        wx.execute("SELECT event_id, date, wind FROM wx WHERE wind IS NOT NULL")}
wx.close()
print("ix rows %d | rebuilt wind day-rows %d" % (len(rows), len(WIND)))

pm = sqlite3.connect("file:pga_model.sqlite?mode=ro", uri=True, timeout=60)
start = {str(e): str(d) for e, d in
         pm.execute("SELECT event_id, MIN(date) FROM rounds GROUP BY event_id")}
pm.close()

D = []
miss = 0
for r in rows:
    eid, _d, yr, rnd, pl, res = str(r[0]), r[1], int(r[2]), int(r[3]), r[4], r[5]
    if yr >= 2026 or res is None:
        continue
    s0 = start.get(eid)
    if not s0:
        miss += 1
        continue
    day = (dt.date.fromisoformat(s0) + dt.timedelta(days=rnd - 1)).isoformat()
    w = WIND.get((eid, day))
    if w is None:
        miss += 1
        continue
    sk = {k: float(v) for k, v in zip(SKILLS, r[6:]) if v is not None}
    if len(sk) < len(SKILLS):
        continue
    D.append(dict(eid=eid, yr=yr, rnd=rnd, pl=pl, res=float(res), wind=w, sk=sk))
print("usable rows %d (dropped for no wind/date: %d) | 2024 %d | 2025 %d"
      % (len(D), miss, sum(1 for d in D if d["yr"] == 2024),
         sum(1 for d in D if d["yr"] == 2025)))
if len(D) < 2000:
    raise SystemExit("insufficient overlap between ix and the rebuilt weather")

# demean wind WITHIN EVENT: a windy venue is not a wind effect
byev = defaultdict(list)
for d in D:
    byev[d["eid"]].append(d)
for eid, v in byev.items():
    w = np.array([x["wind"] for x in v])
    m = w.mean()
    for x in v:
        x["dw"] = x["wind"] - m
D = [d for d in D if abs(d.get("dw", 0.0)) > 0 or True]
print("events %d | within-event wind sd %.2f km/h"
      % (len(byev), float(np.std([d["dw"] for d in D]))))


def run(skill, rows_, label, verbose=True):
    tr = [d for d in rows_ if d["yr"] == 2024]
    te = [d for d in rows_ if d["yr"] == 2025]
    if len(tr) < 400 or len(te) < 400:
        return None

    def z(v, m=None, s=None):
        v = np.asarray(v, float)
        m = v.mean() if m is None else m
        s = (v.std() or 1.0) if s is None else s
        return (v - m) / s, m, s

    sk_tr, ms, ss = z([d["sk"][skill] for d in tr])
    dw_tr, mw, sw = z([d["dw"] for d in tr])
    y_tr = np.array([d["res"] for d in tr])
    X = np.column_stack([np.ones(len(tr)), sk_tr, dw_tr, sk_tr * dw_tr])
    b = np.linalg.lstsq(X, y_tr, rcond=None)[0]
    u = y_tr - X @ b
    idx = defaultdict(list)
    for i, d in enumerate(tr):
        idx[(d["eid"], d["rnd"])].append(i)
    XtXi = np.linalg.pinv(X.T @ X)
    meat = np.zeros((4, 4))
    for g in idx.values():
        sgv = X[g].T @ u[g]
        meat += np.outer(sgv, sgv)
    V = XtXi @ meat @ XtXi
    se = math.sqrt(max(V[3, 3], 0))
    sk_te = (np.array([d["sk"][skill] for d in te]) - ms) / ss
    dw_te = (np.array([d["dw"] for d in te]) - mw) / sw
    y_te = np.array([d["res"] for d in te])
    Xt = np.column_stack([np.ones(len(te)), sk_te, dw_te, sk_te * dw_te])
    b0 = b.copy()
    b0[3] = 0.0
    m1 = float(np.mean((y_te - Xt @ b) ** 2))
    m0 = float(np.mean((y_te - Xt @ b0) ** 2))
    if verbose:
        print("   %-14s d=%+.4f  SE %.4f  t=%+.2f   OOS MSE %.4f -> %.4f  %s"
              % (label, b[3], se, b[3] / se if se > 0 else 0, m0, m1,
                 "BETTER" if m1 < m0 else "worse"))
    return dict(d=b[3], t=b[3] / se if se > 0 else 0.0, gain=m0 - m1)


print("\n" + "=" * 94)
print("LEG A — does a SKILL change what wind costs you? (dev 2024, OOS 2025)")
print("=" * 94)
out = {}
for s in SKILLS:
    r = run(s, D, "%s x wind" % s)
    if r:
        out[s] = r

best = max(out, key=lambda k: abs(out[k]["t"])) if out else None
if best:
    print("\n   PLACEBO for the strongest (%s): wind shuffled BETWEEN event-rounds" % best)
    rng = np.random.default_rng(17)
    keys = sorted({(d["eid"], d["rnd"]) for d in D})
    null = []
    for _ in range(120):
        perm = list(keys)
        rng.shuffle(perm)
        mp = {a: b for a, b in zip(keys, perm)}
        dwmap = {}
        for d in D:
            dwmap.setdefault((d["eid"], d["rnd"]), d["dw"])
        Dp = [dict(x, dw=dwmap[mp[(x["eid"], x["rnd"])]]) for x in D]
        r = run(best, Dp, "", verbose=False)
        if r:
            null.append(r["t"])
    null = np.array(null)
    p = float((np.abs(null) >= abs(out[best]["t"])).sum()) / max(len(null), 1)
    print("   real t %+.2f | placebo mean %+.2f sd %.2f | p = %.3f"
          % (out[best]["t"], null.mean(), null.std(), p))
    print("   %s" % ("SURVIVES the placebo" if p < 0.05 else "does NOT beat its placebo"))

print("\n" + "=" * 94)
print("LEG B — do INDIVIDUAL players have a repeatable wind slope?")
print("=" * 94)
per = defaultdict(lambda: defaultdict(list))
for d in D:
    per[d["pl"]][d["yr"]].append((d["dw"], d["res"]))
sl = {}
for pl, byyr in per.items():
    for yr, v in byyr.items():
        if len(v) < 25:
            continue
        w = np.array([t[0] for t in v])
        y = np.array([t[1] for t in v])
        if w.std() < 1e-6:
            continue
        b = float(np.polyfit(w, y, 1)[0])
        rss = float(np.sum((y - np.polyval(np.polyfit(w, y, 1), w)) ** 2))
        vb = rss / max(len(v) - 2, 1) / max(np.sum((w - w.mean()) ** 2), 1e-9)
        sl[(pl, yr)] = (b, vb, len(v))
both = sorted({p for p, y in sl} & {p for p, y in sl if (p, 2025) in sl}
              & {p for p, y in sl if (p, 2024) in sl})
both = [p for p in {k[0] for k in sl} if (p, 2024) in sl and (p, 2025) in sl]
print("   players with >=25 rounds in BOTH 2024 and 2025: %d" % len(both))
if len(both) >= 30:
    a = np.array([sl[(p, 2024)][0] for p in both])
    b2 = np.array([sl[(p, 2025)][0] for p in both])
    noise = float(np.mean([sl[(p, 2024)][1] for p in both]))
    obs = float(a.var(ddof=1))
    print("   corr(wind slope 2024, wind slope 2025) = %+.3f" % float(np.corrcoef(a, b2)[0, 1]))
    print("   observed variance of slope %.5f | sampling noise %.5f | TRUE %.5f"
          % (obs, noise, max(obs - noise, 0.0)))
    print("   -> %.0f%% of the apparent spread in 'wind players' is sampling noise"
          % (100 * min(noise / obs, 1.0) if obs > 0 else 100))
