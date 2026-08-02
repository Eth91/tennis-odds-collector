"""Apply the MEASURED constants, each with the evidence in the comment.

Every value here was measured, not tuned, except HALF_LIFE_D which is handled separately
(tuned on 2024-25 with 2026 held out). K_COURSE is deliberately LEFT ALONE — see below.
"""
import ast
import io

OUT = []


def sub(path, old, new, tag):
    s = io.open(path, encoding="utf-8").read()
    if new.split("\n")[0].strip() in s:
        print("  = %-16s %s" % (path, tag))
        return
    assert old in s, "ANCHOR MISSING in %s: %s" % (path, tag)
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8").write(s)
    OUT.append(tag)
    print("  + %-16s %s" % (path, tag))


# ============================================================== ruler constants
sub("pga_ruler.py",
    "K_SHRINK = 12.0         # pseudo-rounds of field-average shrinkage",
    """K_SHRINK = 11.0         # MEASURED 2026-07-29 (was 12.0, a guess that turned out close).
                        # Empirical-Bayes optimum k = noise var / true between-player var =
                        # 7.786 / 0.709 over 659 players with >=8 rounds.""",
    "K_SHRINK 12 -> 11 (measured)")

sub("pga_ruler.py",
    "RHO = 0.25              # share of round variance that is player-week form (round dependence)",
    """RHO = 0.05              # MEASURED 2026-07-29, was 0.25 — FIVE TIMES too high. Three
                        # independent estimates: nested ANOVA on rounds within vs across
                        # events = 0.055 (44,580 dof, and the only one that needs no
                        # ratings); raw round-pair correlation r=+0.039 on 57,015 pairs;
                        # selection-free 36-hole total spread implies +0.109. All in
                        # [0.034, 0.109]. A player's four rounds are very nearly
                        # independent. At 0.25 the model inflated 72-hole variance ~14%,
                        # which pushed matchup prices toward 50/50 and fattened the top-N
                        # tails. (The first attempt at this used 72-hole totals and implied
                        # a NEGATIVE rho — an artefact of cut selection, since only
                        # cut-makers have four rounds.)""",
    "RHO 0.25 -> 0.05 (measured)")

sub("pga_ruler.py",
    "SIG_SHRINK = 20.0       # rounds of shrinkage of player sd toward the global sd",
    """SIG_SHRINK = 78.0       # MEASURED 2026-07-29 (was 20.0). The TRUE spread of player
                        # volatility is tiny: between-player variance of sd is 0.052
                        # (sd 0.23) around a mean sd of 2.81 — an 8% spread — against
                        # sampling noise of 4.02 per observation. So 'some players are
                        # streakier' is mostly an illusion and own-sd deserves far less
                        # weight. k = 4.020 / 0.052.""",
    "SIG_SHRINK 20 -> 78 (measured)")

# ============================================================ context constants
sub("pga_context.py",
    "K_FIT = 8.0          # pseudo-rounds of shrinkage on personal course fit (history is noisy)",
    """K_FIT = 105.0        # MEASURED 2026-07-29 (was 8.0 — a 13x error). Personal course fit
                     # is very nearly noise, confirmed two independent ways:
                     #   empirical Bayes over 8,257 player-course cells -> k = 104.8
                     #     (true affinity sd only 0.267 strokes vs 7.49 round variance)
                     #   OUT-OF-SAMPLE: split each cell by date, regress the LATE course
                     #     deviation on the EARLY one over 2,979 cells -> slope +0.0605,
                     #     r=+0.058, implying k = 80. An early course read predicts ~6% of
                     #     the later one.
                     # At 8.0 the code trusted 33% of a 4-round course deviation and was
                     # injecting up to 1.2 strokes of noise into ratings; at 105 it trusts
                     # 3.7%. Course history really is the most over-claimed edge in golf.""",
    "K_FIT 8 -> 105 (measured, OOS-confirmed)")

# K_COURSE is NOT changed. The empirical-Bayes measurement (k~0.2 pseudo-editions, from
# between-course true var 0.038 vs within-course noise 0.008) applies to the DIRECT
# birdie-count factor, not to the bridge-derived factor that K_COURSE actually shrinks. The
# bridge is a lossy inference from scoring (r=-0.777, so ~60% of variance explained) and so
# deserves MORE shrinkage than direct counting; 2.0 editions is directionally right and
# changing it on the strength of a measurement of a different quantity would be exactly the
# mistake this whole pass is correcting.

sub("pga_context.py",
    """    # shrink on ROUNDS, not editions: four rounds of one edition is not a course read
    w = nrd / (nrd + 300.0)""",
    """    # shrink on ROUNDS, not editions: four rounds of one edition is not a course read.
    # 100.0 is MEASURED (2026-07-29): the empirical-Bayes optimum for the course birdie
    # factor is 0.21 pseudo-EDITIONS, and an edition carries ~470 player-rounds, so
    # 0.21 * 470 ~= 100 pseudo-rounds. Courses genuinely differ a lot (between-course true
    # variance 0.038, i.e. +/-19%, against within-course noise of only 0.008), so the 300 I
    # first guessed was over-shrinking a signal that is actually strong.
    w = nrd / (nrd + 100.0)""",
    "direct course factor 300 -> 100 (measured)")

# ============================================================ birdie constants
sub("pga_birdies.py",
    "K_H = 60.0                      # pseudo-holes of shrinkage toward the field rate",
    """K_H = 106.0                     # MEASURED 2026-07-29 (was 60.0 flat). Per-par, because
                                # birdie skill separates players very differently by par:
K_H_PAR = {3: 593.0, 4: 106.0, 5: 162.0}
# Empirical Bayes on binomial noise p(1-p) over true between-player variance, players with
# >=40 holes of that par:
#   par 3: field p=0.133, true between-player var 0.0002 (sd 1.4 percentage points) -> k=593
#   par 4: field p=0.175, true var 0.0014 -> k=106
#   par 5: field p=0.470, true var 0.0015 -> k=162
# Par-3 birdie ability is almost entirely luck — nearly a tenth of what 60 assumed — while
# par 4s carry most of the real signal. A flat 60 over-trusted par 3s badly.""",
    "K_H flat 60 -> per-par (measured)")

sub("pga_birdies.py",
    """    out = {}
    for pl, agg in per.items():
        out[pl] = {par: min(((b + K_H * frate[par]) / (h + K_H)) * ctx, 0.95)
                   for par, (h, b) in agg.items()}""",
    """    out = {}
    for pl, agg in per.items():
        out[pl] = {par: min(((b + K_H_PAR.get(par, K_H) * frate[par])
                             / (h + K_H_PAR.get(par, K_H))) * ctx, 0.95)
                   for par, (h, b) in agg.items()}""",
    "rates() uses per-par K_H")

sub("pga_birdies.py",
    """PAR_MIX_RULE = {70: {3: 4, 4: 12, 5: 2}, 71: {3: 4, 4: 11, 5: 3},
                72: {3: 4, 4: 10, 5: 4}, 73: {3: 4, 4: 9, 5: 5}}""",
    """PAR_MIX_RULE = {70: {3: 4, 4: 12, 5: 2}, 71: {3: 4, 4: 11, 5: 3},
                72: {3: 4, 4: 10, 5: 4}, 73: {3: 3, 4: 11, 5: 4}}
# RE-VALIDATED 2026-07-29 on 114 harvested events (the rule was set on 8 and 5):
#   par 70 -> (4,12,2) in 21/27 events (78%)
#   par 71 -> (4,11,3) in 35/41 (85%)
#   par 72 -> (4,10,4) in 42/44 (95%)
#   par 73 -> (3,11,4) in 2/2  <- CORRECTED from the assumed (4,9,5); n=2, so thin, but
#             observed beats invented, and this is only a fallback for a course we have no
#             hole data for at all (rare now that 114 events are harvested).""",
    "PAR_MIX par-73 corrected")

print()
print("applied %d change(s)" % len(OUT))
for f in ("pga_ruler.py", "pga_context.py", "pga_birdies.py"):
    ast.parse(io.open(f, encoding="utf-8").read())
    print("  parses: %s" % f)
