#!/usr/bin/env python3
"""GM-013 — does par-type-aware birdie skill PREDICT better? The market test of GM-012.

GM-012 found that birdie-making is 45% real skill (corr +0.518 across halves) and that par-5
birdie rate stays distinct at partial +0.215 once overall birdie rate is known -- unlike par 3
(+0.025) and par 4 (+0.082), and unlike every strokes-gained category, whose partials were ~0.

Distinct is not the same as USEFUL. This asks the only question that matters for the birdie
market: predicting a player's birdie count in a round, does splitting their skill by par type beat
one overall rate?

    A  one rate      pred = expected_birdies * f(overall skill)
    B  par-type      pred = SUM over par of expected_birdies[par] * f(skill for that par)

"expected" is the FIELD's own rate for that (event, round, par type) times the holes the player
played, so course, setup, conditions and par mix are all absorbed before any skill is applied.
The two models differ ONLY in whether skill is one number or three.

SHRINKAGE IS APPLIED IDENTICALLY TO BOTH, and it has to be: model B estimates three rates from
the same rounds that gave A one, so B's inputs are noisier by construction. Comparing an unshrunk
three-parameter model against a one-parameter model would measure the extra noise, not the extra
information. The shrinkage constant is tuned on 2024 alone (internal split) and then applied
unchanged to 2025.

Scored by POISSON DEVIANCE, which is the right loss for a count, alongside MSE.
Estimate on 2024 -> test on 2025. 2026 IS THE PROTECTED HOLDOUT AND IS NOT READ.
"""
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

pm = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
br = pm.execute("SELECT tid, player, rnd, p3h, p3b, p4h, p4b, p5h, p5b "
                "FROM birdie_rounds").fetchall()
pm.close()


def yr(t):
    m = re.match(r"R(\d{4})", str(t))
    return int(m.group(1)) if m else None


D = []
for tid, pl, rnd, p3h, p3b, p4h, p4b, p5h, p5b in br:
    y = yr(tid)
    if y is None or y >= 2026:
        continue
    h = {3: (p3h or 0, p3b or 0), 4: (p4h or 0, p4b or 0), 5: (p5h or 0, p5b or 0)}
    if sum(v[0] for v in h.values()) < 15:
        continue
    D.append(dict(tid=tid, yr=y, pl=RU.norm(pl), rnd=int(rnd), h=h,
                  b=sum(v[1] for v in h.values())))

# field rate per (tid, rnd, par) -> expected birdies for each player
bykey = defaultdict(list)
for d in D:
    bykey[(d["tid"], d["rnd"])].append(d)
for k, v in bykey.items():
    for par in (3, 4, 5):
        den = sum(x["h"][par][0] for x in v)
        num = sum(x["h"][par][1] for x in v)
        rate = (num / den) if den else 0.0
        for x in v:
            x.setdefault("e", {})[par] = rate * x["h"][par][0]
    for x in v:
        x["etot"] = sum(x["e"].values())
D = [d for d in D if d["etot"] > 0.5]
print("player-rounds %d | 2024 %d | 2025 %d"
      % (len(D), sum(1 for d in D if d["yr"] == 2024), sum(1 for d in D if d["yr"] == 2025)))


def skills(rows_):
    """player -> (overall factor inputs, per-par inputs) as (birdies, expected)."""
    tot = defaultdict(lambda: [0.0, 0.0])
    per = defaultdict(lambda: {3: [0.0, 0.0], 4: [0.0, 0.0], 5: [0.0, 0.0]})
    for d in rows_:
        tot[d["pl"]][0] += d["b"]
        tot[d["pl"]][1] += d["etot"]
        for par in (3, 4, 5):
            per[d["pl"]][par][0] += d["h"][par][1]
            per[d["pl"]][par][1] += d["e"][par]
    return tot, per


def factor(bird, exp, K):
    """Shrunk multiplicative skill factor: 1.0 when a player has no history."""
    if exp <= 0:
        return 1.0
    w = exp / (exp + K)
    return 1.0 + w * ((bird - exp) / exp)


def deviance(y, mu):
    y = np.asarray(y, float)
    mu = np.clip(np.asarray(mu, float), 1e-9, None)
    t = np.where(y > 0, y * np.log(y / mu), 0.0) - (y - mu)
    return float(2 * t.mean())


def evaluate(train, test, K):
    tot, per = skills(train)
    ya, pa, pb = [], [], []
    for d in test:
        t = tot.get(d["pl"])
        fa = factor(t[0], t[1], K) if t else 1.0
        pa.append(d["etot"] * fa)
        p = per.get(d["pl"])
        if p:
            pb.append(sum(d["e"][par] * factor(p[par][0], p[par][1], K) for par in (3, 4, 5)))
        else:
            pb.append(d["etot"])
        ya.append(d["b"])
    return (np.array(ya), np.array(pa), np.array(pb))


tr24 = [d for d in D if d["yr"] == 2024]
te25 = [d for d in D if d["yr"] == 2025]

print("\n" + "=" * 92)
print("TUNE the shrinkage on 2024 ONLY (internal split), identically for both models")
print("=" * 92)
half = len(tr24) // 2
a24, b24 = tr24[:half], tr24[half:]
print("   %-8s %12s %12s" % ("K", "dev A", "dev B"))
bestK, bestv = None, None
for K in (5, 10, 20, 40, 80, 160, 320):
    y, pa, pb = evaluate(a24, b24, K)
    da, db = deviance(y, pa), deviance(y, pb)
    if bestv is None or min(da, db) < bestv:
        bestK, bestv = K, min(da, db)
    print("   %-8d %12.5f %12.5f" % (K, da, db))
print("   -> K = %d" % bestK)

print("\n" + "=" * 92)
print("OOS: estimate skill on 2024, predict every 2025 round")
print("=" * 92)
y, pa, pb = evaluate(tr24, te25, bestK)
base = np.array([d["etot"] for d in te25])
print("   n = %d player-rounds, %d players" % (len(y), len({d["pl"] for d in te25})))
print("   %-26s %12s %12s" % ("model", "Poisson dev", "MSE"))
for lab, p in (("field only (no skill)", base), ("A  one birdie rate", pa),
               ("B  par-type rates", pb)):
    print("   %-26s %12.5f %12.5f" % (lab, deviance(y, p), float(np.mean((y - p) ** 2))))
dA, dB = deviance(y, pa), deviance(y, pb)
print("\n   B - A = %+.5f  ->  %s" % (dB - dA, "PAR-TYPE HELPS" if dB < dA else "par-type does NOT help"))
print("   skill over field-only: A %+.5f | B %+.5f  (negative = better)"
      % (dA - deviance(y, base), dB - deviance(y, base)))

# does it help WHERE IT SHOULD -- rounds with more par 5s?
print("\n   by number of par-5 holes played (the mechanism should concentrate here):")
n5 = np.array([d["h"][5][0] for d in te25])
for lo, hi in ((0, 2), (3, 3), (4, 4), (5, 9)):
    m = (n5 >= lo) & (n5 <= hi)
    if m.sum() >= 200:
        print("      %d-%d par 5s  n=%5d   dev A %.5f  dev B %.5f  %+.5f"
              % (lo, hi, int(m.sum()), deviance(y[m], pa[m]), deviance(y[m], pb[m]),
                 deviance(y[m], pb[m]) - deviance(y[m], pa[m])))
