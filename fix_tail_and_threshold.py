"""Recalibrate the top-N tail, and replace the ABSOLUTE edge threshold with a RELATIVE band.

Both fixes are measured on 986 priced+rated runners across 9 majors with REAL FanDuel/DraftKings
closes (oa_golf.sqlite), graded against actual finishes.

--------------------------------------------------------------------------------------------
FIX 1 — TAIL RECALIBRATION.  simulate() returns probabilities that are accurate on favourites
and badly inflated on longshots:

    top-20 quintile   Q1     Q2     Q3     Q4     Q5
    model            .055   .101   .153   .218   .383
    REALISED         .010   .061   .152   .183   .411
                     5.5x                         ok

The shape parameter is a logistic slope on logit(p) fitted WITH EVENT FIXED EFFECTS, so it
measures shape only — the per-event level is absorbed by the dummies. That matters because the
backtest's field is truncated to priced+rated runners (75-138 of a real ~156), which biases the
LEVEL but not the shape. Three independent estimates:

    win 1.485 (se .310)   top-20 1.527 (se .144)   top-10 1.280 (se .151)

All overlap; a single pooled 1.45 is used rather than three per-market slopes fitted on nine
events, which would be fitting noise.

Applied as: stretch log-odds by SHAPE_SLOPE, then bisect ONE intercept so the field sums to
exactly what it summed to before. That preserves the coherence property the audit verified
(win=1, top5=5, top10=10, top20=20, and the ties variants keep their own >N sums) while moving
probability from the tail to the head. Measured effect: Q1 .055 -> .028 against a realised .010,
and mean log-likelihood improves on BOTH top-20 (-.3686 -> -.3610) and top-10 (-.2432 -> -.2414).

NOT applied in-play. The slope was fitted on pre-tournament sims; once `progress`/`partial`
condition on posted scores the distribution is a different animal and stretching it would
distort a known-sharp number.

--------------------------------------------------------------------------------------------
FIX 2 — RELATIVE THRESHOLD.  `ours - fair >= 0.04` is an absolute probability difference, and on
a distribution whose tail is inflated 5x it fires almost exclusively on longshots: 11 flags in
the longest-odds quartile against 3 in the shortest. It structurally excludes favourites, which
is the ONLY region where the model is calibrated.

The replacement is a RATIO BAND, and the cap is measured rather than guessed. Bucketing all 986
runners by (model / market) and grading on top-20 finishing — 162 positives, so this has real
power:

    ratio band   n     model t20   REALISED   error
    0.8-1.2     213      .2173      .1972     1.10x   <- accurate
    1.2-2.0     168      .1768      .1667     1.06x   <- accurate
    2.0-4.0     134      .1711      .0821     2.08x   <- breaks down
    4.0+        192      .1677      .0677     2.48x   <- breaks down

Inside 2x the model is right; beyond 2x the disagreement IS the error. So TN_RATIO_MAX = 2.0 is
where the data says to stop believing our own number.

The absolute floor is KEPT but lowered to 0.02, because floor and cap together imply a minimum
fair probability without needing a separate constant:
    fair * (RATIO_MAX - 1) >= TN_EDGE   =>   fair >= 0.02
which is exactly the "stay out of the tail" rule, derived instead of asserted.

MATCHUPS get the same treatment at 1.6 — but flagged as PRUDENTIAL, not measured: G2 is still
n=0, so there is no matchup-specific evidence. It is carried over from the top-N result because
the audit found the identical signature (model backs the UNDERDOG in 12 of 14, every model prob
inside 0.430-0.599 against a market spanning 0.211-0.682).

BIRDIES get only a loose 1.6 guard-rail and are otherwise untouched, deliberately: the birdie
stream is the one that HAS passed a probability-space reliability test (slope 1.06 against a
0.85 bar, leak-free). Tightening a stream that passed its own calibration gate on evidence
borrowed from one that never had a gate would be over-reach.
"""
import ast
import io

# ------------------------------------------------------------------ 1. pga_ruler.py
p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()

anchor = "MIN_ROUNDS = 20"
const = '''SHAPE_SLOPE = 1.30      # MEASURED 2026-07-30 on 986 runners / 9 majors with REAL closes,
                        # graded on actual finishes. Logistic slope on logit(p) fitted WITH EVENT
                        # FIXED EFFECTS so it captures SHAPE only — the per-event level is absorbed
                        # by the dummies, which matters because the backtest field is truncated to
                        # priced+rated runners and that biases level, not shape. Estimates: win
                        # 1.485 (se .310), top-20 1.527 (se .144), top-10 1.280 (se .151) — all
                        # overlapping, so ONE pooled value beats three noisy per-market slopes.
                        # >1 means our log-odds are too FLAT: the tail needs pushing down. Measured
                        # effect on the top-20 bottom quintile: .055 -> .028 (realised .010), and
                        # log-likelihood improves on both top-20 and top-10. Set to 1.0 to disable.
                        # REFIT UNDER THE SUM CONSTRAINT: the unconstrained logit fit (1.45-1.53)
                        # OVERSHOOTS, because renormalising back to N returns the tail's mass to the
                        # head — top-20 Q5 went .383 -> .451 against a realised .411, manufacturing
                        # fresh favourite-side flags. Refitting WITH the renormalisation applied
                        # gives a flat surface 1.25-1.53 (top-20 opt 1.527, top-10 opt 1.300, joint
                        # 1.450). 1.30 taken: top-10 optimum, within 0.3% of the top-20 optimum, and
                        # halves the favourite overshoot the ratio gate would turn into bets.
'''
if "SHAPE_SLOPE" in s:
    print("  = SHAPE_SLOPE already present")
else:
    assert anchor in s, "MIN_ROUNDS anchor missing"
    s = s.replace(anchor, const + anchor, 1)

helper = '''
def _recal_shape(out, keys, slope=None):
    """Stretch each probability's log-odds by `slope`, preserving the field total exactly.

    The total is what makes these numbers coherent — win sums to 1, top20 to 20, and the
    ties-inclusive variants to their own (larger) totals. So rather than renormalising to a
    nominal N, this re-solves a single additive intercept per key so the NEW sum equals the OLD
    sum. Shape changes; coherence does not.
    """
    sl = SHAPE_SLOPE if slope is None else slope
    if not out or abs(sl - 1.0) < 1e-9:
        return out
    for key in keys:
        ps = [(out[p_] or {}).get(key) for p_ in out]
        ps = [v for v in ps if v is not None]
        if len(ps) < 10:
            continue
        target = sum(ps)
        if target <= 0:
            continue
        lg = []
        for p_ in out:
            v = (out[p_] or {}).get(key)
            lg.append(None if v is None
                      else math.log(min(max(v, 1e-9), 1 - 1e-9) / (1 - min(max(v, 1e-9), 1 - 1e-9))))
        lo, hi = -40.0, 40.0
        for _ in range(200):
            c = (lo + hi) / 2.0
            tot = sum(1.0 / (1.0 + math.exp(-(sl * l + c))) for l in lg if l is not None)
            if tot > target:
                hi = c
            else:
                lo = c
        c = (lo + hi) / 2.0
        for p_, l in zip(list(out), lg):
            if l is not None:
                out[p_][key] = 1.0 / (1.0 + math.exp(-(sl * l + c)))
    return out


'''
if "_recal_shape" in s:
    print("  = _recal_shape already present")
else:
    a2 = "def simulate(R, field,"
    assert a2 in s, "simulate def missing"
    s = s.replace(a2, helper.lstrip("\n") + a2, 1)

old_ret = '''"cut": float(made[:, i].mean())}
    return out'''
new_ret = '''"cut": float(made[:, i].mean())}
    # TAIL RECALIBRATION (2026-07-30). Skipped in-play: SHAPE_SLOPE was fitted on pre-tournament
    # sims, and once posted scores condition the distribution it is already sharp — stretching it
    # would distort a number that is no longer a forecast of 4 unknown rounds.
    if progress is None and partial is None:
        _recal_shape(out, ("win", "top5", "top10", "top20",
                           "win_ties", "top5_ties", "top10_ties", "top20_ties"))
    return out'''
if "TAIL RECALIBRATION (2026-07-30)" in s:
    print("  = recalibration already wired into simulate()")
else:
    assert old_ret in s, "simulate return anchor missing"
    s = s.replace(old_ret, new_ret, 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_ruler.py: SHAPE_SLOPE + _recal_shape + wired into simulate()")

# ------------------------------------------------------------------ 2. pga_e3.py
p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

old_c = "TN_EDGE = 0.04"
new_c = '''TN_EDGE = 0.02          # LOWERED 2026-07-30 from 0.04. The absolute test is no longer doing the
                        # selecting — the ratio band below is — so this is now just a floor that
                        # keeps trivial absolute edges out. Floor and cap together imply a minimum
                        # fair probability with no extra constant: fair*(RATIO_MAX-1) >= TN_EDGE,
                        # i.e. fair >= 0.02. The tail exclusion is DERIVED, not asserted.
TN_RATIO_MIN = 1.15     # MEASURED 2026-07-30. Bucketing 986 runners by (model/market) and grading
TN_RATIO_MAX = 2.0      # on top-20 (162 positives): inside 2x the model is accurate (1.06-1.10x
                        # realised), beyond 2x it over-predicts by 2.08x (n=134) and 2.48x (n=192).
                        # Past 2x the disagreement IS our error, so refuse to bet it. This replaces
                        # `ours - fair >= 0.04`, which on a 5x-inflated tail fired 11 flags in the
                        # longest-odds quartile against 3 in the shortest — structurally excluding
                        # favourites, the only region where this model is calibrated.'''
if "TN_RATIO_MAX" in s:
    print("  = TN_RATIO band already present")
else:
    assert old_c in s, "TN_EDGE anchor missing"
    s = s.replace(old_c, new_c, 1)

old_m = "M_EDGE = 0.06"
new_m = '''M_EDGE = 0.06
M_RATIO_MAX = 1.6       # PRUDENTIAL, not measured — G2 is still n=0, so there is no matchup-specific
                        # evidence. Carried over from the top-N ratio result because the audit found
                        # the same signature: the model backed the UNDERDOG in 12 of 14 markets, with
                        # every model probability inside 0.430-0.599 against a market spanning
                        # 0.211-0.682. Revisit once G2 has a real sample.
B_RATIO_MAX = 1.6       # loose guard-rail only. Birdies are the one stream that HAS passed a
                        # probability-space reliability test (1.06 vs the 0.85 bar, leak-free), so
                        # they are deliberately not retuned on evidence borrowed from top-N.'''
if "M_RATIO_MAX" in s:
    print("  = M_RATIO_MAX already present")
else:
    assert old_m in s, "M_EDGE anchor missing"
    s = s.replace(old_m, new_m, 1)

old_g = "            elif ours - fair >= TN_EDGE and od >= TN_MIN_ODDS:"
new_g = '''            elif (ours - fair >= TN_EDGE and od >= TN_MIN_ODDS
                  and TN_RATIO_MIN <= ours / max(fair, 1e-9) <= TN_RATIO_MAX):'''
if "TN_RATIO_MIN <= ours" in s:
    print("  = top-N ratio gate already applied")
else:
    assert old_g in s, "top-N gate anchor missing"
    s = s.replace(old_g, new_g, 1)

old_mg = "        if pe >= M_EDGE:"
new_mg = '''        _ours_side = p if side == a else (1 - p)
        _fair_side = fair if side == a else (1 - fair)
        if pe >= M_EDGE and _ours_side / max(_fair_side, 1e-9) <= M_RATIO_MAX:'''
if "_ours_side" in s:
    print("  = matchup ratio gate already applied")
else:
    assert old_mg in s, "matchup gate anchor missing"
    s = s.replace(old_mg, new_mg, 1)

old_b = "                if edge >= 0.05 and key not in seen_b:"
new_b = '''                if (edge >= 0.05 and ours <= B_RATIO_MAX * (1.0 / od)
                        and key not in seen_b):'''
if "B_RATIO_MAX * (1.0 / od)" in s:
    print("  = birdie guard-rail already applied")
else:
    assert old_b in s, "birdie gate anchor missing"
    s = s.replace(old_b, new_b, 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_e3.py: ratio band on top-N, ratio cap on matchups, guard-rail on birdies")
