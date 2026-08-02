"""The birdie model is OVER-DISPERSED 1.81x. Every birdie edge sits in the tails it invented.

Two independent measurements agree to two decimal places:
  vs THE MARKET   our sd of P(over) across players is 1.81x the devigged market's (r=0.664)
  vs OUTCOMES     reliability slope of realized on predicted = 0.552 over 19,942 leak-free
                  out-of-sample player-rounds; 1/0.552 = 1.81x
Top decile: we predict 0.714, reality delivers 0.636. Bottom: we predict 0.461, reality 0.480.
Monotone, so the ORDERING is real — the SPREAD is not.

That the two agree is what settles it: the market's tighter spread was the honest one, and the
balanced 5-over/5-under flag split I called "healthy two-sidedness" is the signature of the
disease. Over-dispersion flags the high tail as overs and the low tail as unders.

Why K_H did not already handle this: it was fit by empirical Bayes on the RATE assuming binomial
noise. But birdie counts are over-dispersed relative to binomial (course and day effects make
holes correlated), so the true noise is larger than p(1-p) and the EB shrinkage came out too
weak. And P(>=k birdies) is a threshold function over 18 holes, which AMPLIFIES small rate
differences. So the correct correction is measured on the probability, not the rate.

Fix: shrink each player's per-par rate deviation from the field by the measured reliability
slope. This is a calibration constant with an out-of-sample provenance, not a fudge.
"""
import ast, io

p = "pga_birdies.py"
s = io.open(p, encoding="utf-8").read()

old_c = "K_H = 106.0                     # MEASURED 2026-07-29 (was 60.0 flat). Per-par, because"
new_c = """DISPERSION = 0.552              # MEASURED 2026-07-30 out of sample. The model separated
                                # players 1.81x more than reality: reliability slope of
                                # realized on predicted = 0.552 over 19,942 leak-free
                                # player-rounds (early-half rates -> late-half rounds), and
                                # independently our sd of P(over) was 1.81x the devigged
                                # market's with r=0.664. 1/0.552 = 1.81 — the two agree, so
                                # the spread was noise and the market's was right. Applied to
                                # the per-par rate DEVIATION from the field, because K_H
                                # shrinks the rate under a binomial-noise assumption while
                                # birdie counts are over-dispersed (correlated holes) AND
                                # P(>=k) over 18 holes amplifies small rate gaps.
K_H = 106.0                     # MEASURED 2026-07-29 (was 60.0 flat). Per-par, because"""
if "DISPERSION = 0.552" in s:
    print("  = dispersion constant already present")
else:
    assert old_c in s, "K_H anchor missing"
    s = s.replace(old_c, new_c, 1)

old_r = '''    out = {}
    for pl, agg in per.items():
        out[pl] = {par: min(((b + K_H_PAR.get(par, K_H) * frate[par])
                             / (h + K_H_PAR.get(par, K_H))) * ctx, 0.95)
                   for par, (h, b) in agg.items()}'''
new_r = '''    out = {}
    for pl, agg in per.items():
        row = {}
        for par, (h, b) in agg.items():
            kh = K_H_PAR.get(par, K_H)
            r_ = (b + kh * frate[par]) / (h + kh)
            # DISPERSION CORRECTION: pull the deviation from the field toward the field by the
            # measured out-of-sample factor. Without this the model separated players 1.81x
            # more than reality and every flagged birdie edge was a tail artefact.
            r_ = frate[par] + DISPERSION * (r_ - frate[par])
            row[par] = min(r_ * ctx, 0.95)
        out[pl] = row'''
if "DISPERSION CORRECTION" in s:
    print("  = rates() already dispersion-corrected")
else:
    assert old_r in s, "rates() anchor missing"
    s = s.replace(old_r, new_r, 1)
ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_birdies: player rate deviations shrunk by the measured 0.552")
