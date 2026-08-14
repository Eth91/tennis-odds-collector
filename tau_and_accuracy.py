"""(1) Is TAU identifiable at all?  (2) How accurate has the sim actually been?

PART 1 — A UNITS MISMATCH I NEED TO CHECK BEFORE FITTING ANYTHING ELSE.
`SimResult.cut_line()` returns the cut in the sim's own score space, which INCLUDES the shared
shock tau*(w1+w2). The realised value I compared it against was `actual_cut - (fm1+fm2)` — field
mean removed. If the sim keeps the level shock and the actual has it subtracted out, then tau
inflates the sim's spread for a reason that has no counterpart in the data, and the coverage
"improving" from tau=0 to tau=1 is an artefact, not identification.

The prediction if that is what happened: sd(cut_line) should equal sqrt(sd0^2 + 2*tau^2) exactly,
because a per-round common shift over two rounds contributes variance 2*tau^2 and NOTHING else.
Checked numerically below. If it holds, tau is a pure level term, every field-relative quantity is
exactly tau-invariant, and tau cannot be fitted from anything this model claims to predict —
pga_ruler models strokes RELATIVE TO THE FIELD and never predicts the level at all.

PART 2 — accuracy, straight off the fit checkpoint (215 walk-forward events, no re-simulation).
"""
import numpy as np

import pga_ruler as RU
import pga_sim as PS

print("=" * 88)
print("PART 1 — is TAU identifiable, or is the cut-line result a units mismatch?")
print("=" * 88)
R, _g = PS.ratings_asof("2026-08-01")
field = list(R)[:150]
rows = []
for tau in (0.0, 1.0, 2.0, 3.0, 4.0):
    cl = PS.simulate(field, n=6000, seed=11, ratings=R, tau=tau, cut_n=65,
                     spread=1.30).cut_line()
    rows.append((tau, cl["sd"]))
sd0 = rows[0][1]
print("\n   %-6s %10s %14s %10s" % ("tau", "sim sd", "sqrt(sd0^2+2t^2)", "diff"))
worst = 0.0
for tau, sd in rows:
    pred = (sd0 ** 2 + 2.0 * tau ** 2) ** 0.5
    worst = max(worst, abs(sd - pred))
    print("   %-6.1f %10.4f %14.4f %10.4f" % (tau, sd, pred, sd - pred))
print("\n   worst deviation from a PURE LEVEL SHOCK: %.4f strokes" % worst)
print("   -> if ~0, every stroke of tau variance is common-mode: it shifts the whole field")
print("      together, cancels EXACTLY out of any field-relative quantity, and therefore")
print("      cannot be identified from data the model predicts.")

print("\n   DIRECT CHECK — is a field-relative quantity tau-invariant?")
for tau in (0.0, 2.0, 4.0):
    r = PS.simulate(field, n=6000, seed=11, ratings=R, tau=tau, cut_n=65, spread=1.30)
    w = r.win
    top = sorted(w, key=lambda p: -w[p])[:3]
    print("      tau=%.0f  win of top-3: %s" % (tau, "  ".join("%.4f" % w[p] for p in top)))

print("\n" + "=" * 88)
print("PART 2 — historical accuracy, 215 walk-forward events (2023-10 .. 2026-08)")
print("=" * 88)
z = np.load("shape_sims.npz")
P, Y, OFF, DATE = z["P"], z["Y"], z["OFF"], z["DATE"]
MK = ["win", "top5", "top10", "top20", "win_ties", "top5_ties", "top10_ties", "top20_ties"]
NEV = len(OFF) - 1
EPS = 1e-9

print("\n%-12s %8s %9s %9s %9s %9s" % ("market", "n", "base", "Brier", "BrierSkill", "LogLoss"))
for mi, m in enumerate(MK):
    p, y = P[:, mi].astype(np.float64), Y[:, mi].astype(np.float64)
    base = y.mean()
    br = float(((p - y) ** 2).mean())
    bb = float(((base - y) ** 2).mean())
    q = np.clip(p, EPS, 1 - EPS)
    ll = float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())
    print("%-12s %8d %9.4f %9.5f %9.4f %9.5f" % (m, len(p), base, br, 1 - br / bb, ll))

print("\n--- the plain-English question: when it says X%, does X% happen? ---")
mi = MK.index("top10")
p, y = P[:, mi].astype(np.float64), Y[:, mi].astype(np.float64)
for lo, hi in ((0, .05), (.05, .10), (.10, .20), (.20, .40), (.40, .70), (.70, 1.01)):
    s = (p >= lo) & (p < hi)
    if s.sum() > 30:
        print("   top10 said %2.0f-%2.0f%%  n=%5d   predicted %5.1f%%   actual %5.1f%%   gap %+5.1fpp"
              % (100 * lo, 100 * hi, s.sum(), 100 * p[s].mean(), 100 * y[s].mean(),
                 100 * (y[s].mean() - p[s].mean())))

print("\n--- does its FAVOURITE actually win more than anyone else's? ---")
hit1 = hit5 = hit10 = n = 0
for e in range(NEV):
    a, b = OFF[e], OFF[e + 1]
    pw = P[a:b, 0]
    if pw.size < 20:
        continue
    n += 1
    order = np.argsort(-pw)
    yw = Y[a:b, 0]
    hit1 += float(yw[order[0]] > 0.5)
    hit5 += float(Y[a:b, MK.index("top5")][order[0]] > 0.5)
    hit10 += float(Y[a:b, MK.index("top10")][order[0]] > 0.5)
exp1 = float(np.mean([P[OFF[e]:OFF[e + 1], 0].max() for e in range(NEV)
                      if OFF[e + 1] - OFF[e] >= 20]))
print("   over %d events, the model's TOP-RANKED player:" % n)
print("     won            %3d / %d = %5.1f%%   (model expected %5.1f%%)"
      % (hit1, n, 100 * hit1 / n, 100 * exp1))
print("     finished top5  %3d / %d = %5.1f%%" % (hit5, n, 100 * hit5 / n))
print("     finished top10 %3d / %d = %5.1f%%" % (hit10, n, 100 * hit10 / n))
print("   a random player in a 150-man field wins 0.7%% of the time.")
