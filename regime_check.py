"""Does the REGIME SPLIT actually beat the single validated slope? Holdout only.

The 8/8 holdout result validated ONE thing: the non-major s* applied to every 2026 event beats
1.30 applied to every 2026 event. It did NOT test the major-specific slopes -- those come from 25
training events and have never been scored out of sample. Shipping them because they were fitted
would repeat, in miniature, the exact error being corrected: a small-n majors optimum trusted
beyond the population it was measured on.

Three arms on the 2026 holdout, from the checkpoint (no re-simulation):
  A  1.30 everywhere                    — what ships today
  B  non-major s* everywhere            — the arm that already won 8/8
  C  regime split                        — major s* on majors, non-major s* on the rest

Lower log-loss wins. Majors and non-majors are also reported separately, because a split that
only helps on 12 major events could be pooled into looking good.
"""
import numpy as np

MARKETS = ["win", "top5", "top10", "top20", "win_ties", "top5_ties", "top10_ties", "top20_ties"]
STD = {"win": 1.21, "top5": 1.03, "top10": 1.00, "top20": 1.00,
       "win_ties": 1.02, "top5_ties": 1.03, "top10_ties": 1.00, "top20_ties": 1.01}
MAJ = {"win": 1.65, "top5": 1.19, "top10": 1.25, "top20": 1.20,
       "win_ties": 1.48, "top5_ties": 1.16, "top10_ties": 1.28, "top20_ties": 1.22}
EPS = 1e-9

z = np.load("shape_sims.npz")
P, Y, OFF, DATE, MJ = z["P"], z["Y"], z["OFF"], z["DATE"], z["MAJ"]
NEV = len(OFF) - 1
hold = [e for e in range(NEV) if DATE[e] >= 2026]
hmaj = [e for e in hold if MJ[e]]
hstd = [e for e in hold if not MJ[e]]
print("holdout %d events: %d major, %d non-major\n" % (len(hold), len(hmaj), len(hstd)))


def stretch(p, s):
    if abs(s - 1.0) < 1e-12 or p.size < 10:
        return p.copy()
    q = np.clip(p, EPS, 1 - EPS)
    lg = np.log(q / (1 - q))
    tgt = float(p.sum())
    lo, hi = -40.0, 40.0
    for _ in range(60):
        c = 0.5 * (lo + hi)
        if float((1.0 / (1.0 + np.exp(-(s * lg + c)))).sum()) > tgt:
            hi = c
        else:
            lo = c
    return 1.0 / (1.0 + np.exp(-(s * lg + 0.5 * (lo + hi))))


def ll(idx, mi, pick):
    tot = n = 0.0
    for e in idx:
        a, b = OFF[e], OFF[e + 1]
        p = stretch(P[a:b, mi].astype(np.float64), pick(e, MARKETS[mi]))
        y = Y[a:b, mi].astype(np.float64)
        q = np.clip(p, EPS, 1 - EPS)
        tot += float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).sum())
        n += (b - a)
    return tot / n if n else float("nan")


ARMS = [
    ("A 1.30 global (ships today)", lambda e, k: 1.30),
    ("B non-major s* global", lambda e, k: STD[k]),
    ("C regime split", lambda e, k: (MAJ if MJ[e] else STD)[k]),
]

for label, idx in (("ALL HOLDOUT", hold), ("holdout MAJORS", hmaj), ("holdout NON-MAJORS", hstd)):
    if not idx:
        continue
    print("=== %s (n=%d events) ===" % (label, len(idx)))
    print("   %-12s %11s %11s %11s   %s" % ("market", "A 1.30", "B std s*", "C split", "winner"))
    wins = {"A": 0, "B": 0, "C": 0}
    for mi, m in enumerate(MARKETS):
        v = [ll(idx, mi, f) for _, f in ARMS]
        w = "ABC"[int(np.argmin(v))]
        wins[w] += 1
        print("   %-12s %11.5f %11.5f %11.5f   %s" % (m, v[0], v[1], v[2], w))
    print("   markets won: A=%d  B=%d  C=%d\n" % (wins["A"], wins["B"], wins["C"]))

print("READ: C must beat B on MAJORS to justify the extra constants. If B >= C there,")
print("the major-specific slopes are noise from 25 events and the single validated")
print("slope should ship instead.")
