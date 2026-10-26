#!/usr/bin/env python3
"""Fit rank-conditional logit offsets for the placement markets. Fit 2023-25, score 2026.

THE DEFECT: top5/10/20 carry a monotone bias in the model's OWN win-rank. top20, holdout rows:
rank 2-5 priced .3985 vs realised .5159; rank 41+ priced .1075 vs realised .0894 (-4.1 SE,
n=4,198). The tail over-prediction is the manufactured longshot edge behind the -85.6% book.

⚠️ THE AGGREGATE CALIBRATION CHECK CANNOT SEE THIS. top10 slope 1.002, intercept -0.001, while
rank-1 is +11pp and rank-41+ is -1.1pp: the two ends cancel. No function of p alone can remove a
residual that is conditional on something other than p — which is also why the isotonic headroom
measured ~0.

⚠️ PLACEMENT MARKETS ONLY. The same offsets applied to `win` make 2026 win Brier skill go
+0.0031 -> -0.0138. Fitting them there would be fitting noise.

Offsets are applied in logit space and then a single intercept is re-solved per market so the
FIELD TOTAL is preserved exactly — same contract as _recal_shape. Without that the probabilities
stop summing to 5/10/20 and every downstream devig breaks.
"""
import json

import numpy as np

MK = ["win", "top5", "top10", "top20", "win_ties", "top5_ties", "top10_ties", "top20_ties"]
PLACE = ["top5", "top10", "top20", "top5_ties", "top10_ties", "top20_ties"]
EDGES = [1, 2, 6, 16, 41]            # bucket lower bounds on win-rank
EPS = 1e-9

z = np.load("shape_sims.npz")
P, Y, OFF, DATE = z["P"], z["Y"], z["OFF"], z["DATE"]
NEV = len(OFF) - 1


def bucket_of(r):
    b = 0
    for i, e in enumerate(EDGES):
        if r >= e:
            b = i
    return b


RANK = np.zeros(P.shape[0], dtype=np.int8)
for e in range(NEV):
    a, b = OFF[e], OFF[e + 1]
    order = np.argsort(-P[a:b, 0])          # rank by the model's OWN win probability
    rk = np.empty(b - a, dtype=np.int32)
    rk[order] = np.arange(1, b - a + 1)
    RANK[a:b] = [bucket_of(int(x)) for x in rk]

train = [e for e in range(NEV) if DATE[e] < 2026]
hold = [e for e in range(NEV) if DATE[e] >= 2026]
print("train %d events, holdout %d\n" % (len(train), len(hold)))


def rows(idx):
    return np.concatenate([np.arange(OFF[e], OFF[e + 1]) for e in idx])


def logit(p):
    q = np.clip(p, EPS, 1 - EPS)
    return np.log(q / (1 - q))


def apply_off(mi, idx, off):
    """Offsets in logit space, then one intercept per EVENT re-solved to hold the field sum."""
    out = np.zeros(P.shape[0])
    for e in idx:
        a, b = OFF[e], OFF[e + 1]
        lg = logit(P[a:b, mi].astype(np.float64)) + off[RANK[a:b]]
        tgt = float(P[a:b, mi].astype(np.float64).sum())
        lo, hi = -40.0, 40.0
        for _ in range(60):
            c = 0.5 * (lo + hi)
            if float((1 / (1 + np.exp(-(lg + c)))).sum()) > tgt:
                hi = c
            else:
                lo = c
        out[a:b] = 1 / (1 + np.exp(-(lg + 0.5 * (lo + hi))))
    return out


def ll(mi, idx, off=None):
    r = rows(idx)
    p = apply_off(mi, idx, off)[r] if off is not None else P[r, mi].astype(np.float64)
    y = Y[r, mi].astype(np.float64)
    q = np.clip(p, EPS, 1 - EPS)
    return float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())


FIT = {}
print("%-12s %s" % ("market", "  ".join("b%d" % i for i in range(len(EDGES)))))
for mi, m in enumerate(MK):
    if m not in PLACE:
        continue
    off = np.zeros(len(EDGES))
    for _it in range(40):                    # coordinate descent on train log-loss
        moved = False
        for bi in range(len(EDGES)):
            best, bv = off[bi], ll(mi, train, off)
            for d in (-0.20, -0.08, -0.03, -0.01, 0.01, 0.03, 0.08, 0.20):
                t = off.copy(); t[bi] = off[bi] + d
                v = ll(mi, train, t)
                if v < bv - 1e-9:
                    bv, best = v, t[bi]
            if abs(best - off[bi]) > 1e-12:
                off[bi] = best; moved = True
        if not moved:
            break
    FIT[m] = [round(float(x), 4) for x in off]
    print("%-12s %s" % (m, "  ".join("%+.3f" % x for x in off)))

print("\n2026 HOLDOUT — untouched during fitting")
print("%-12s %10s %10s %10s %9s" % ("market", "LL base", "LL fixed", "dLL/obs", "verdict"))
tot = 0.0
for mi, m in enumerate(MK):
    if m not in PLACE:
        continue
    a, b = ll(mi, hold), ll(mi, hold, np.array(FIT[m]))
    tot += (a - b) * len(rows(hold))
    print("%-12s %10.5f %10.5f %+10.5f %9s" % (m, a, b, a - b, "better" if b < a else "WORSE"))
print("   total %.1f nats over %d holdout rows" % (tot, len(rows(hold))))

print("\nNULL CHECK — the same offsets on `win`, where they must NOT help")
wi = MK.index("win")
a, b = ll(wi, hold), ll(wi, hold, np.array(FIT["top20"]))
print("   win  LL %.5f -> %.5f  (%s)" % (a, b, "WORSE, as required" if b > a else "BETTER — investigate"))
json.dump({"edges": EDGES, "offsets": FIT}, open("rank_offsets.json", "w"), indent=1)
print("\nwrote rank_offsets.json")
