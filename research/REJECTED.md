# REJECTED HYPOTHESES — check before testing anything new
| id | hypothesis | result | why rejected | revisit if |
|---|---|---|---|---|
| R1 | regime-weighting (availability+arrivals+elevated) improves bets | v1.5 +15.54u vs full +10.09u on 182 rows | dropped marginal WINNERS; wowy-only alone dropped 7 bets that went 7-0 | never on ROI alone; only w/ a >+15.54u backtest |
| R2 | ~~stint-WOWY as a live bettor~~ **SUPERSEDED 2026-08-13 by PR-002** | the original verdict measured only opener(48h, 15% coverage) and T-4h(breakeven) and concluded 'edge and liquidity never overlap'. That was WRONG: 8-24h was never measured, and there coverage is 99.5-100% with ROI +14.8%..+25.2% and a NEGATIVE calibration gap | the conclusion was drawn from an unmeasured gap, not from evidence against the window | superseded — see PR-002; note the 2026-only cells are much weaker (+2.4% at 12h) |
| R3 | lower EV threshold to recover volume | 0.07/0.05 both WORSE (+8.76u vs +10.09u) | adds losers faster than winners | no |
| R4 | narrow book to alt ladders | ladders 4-4 fwd vs main 9-6 | all-time ladder edge was in-sample | no |
| R5 | USAGE_RATE_ADJ | tested, rejected pre-freeze | — | — |
| R6 | harder shrink toward book fixes the anti-predictive residual | k=0/5/11 identical; k>=20 strictly worse | shrinking removes the BET, not just the bad probability -- p_adj is both signal and gate | only with a situation-gate that does not route through p_adj |

## PR-003 WITHDRAWN — 2026-08-15, same day it was registered (EXP-022)

Registered on a −8.5pp gap that was negative in 3/3 chronological thirds and 3/3 markets, with
the stated caveat that it was NON-MONOTONE and had no mechanism. The mechanism test killed it.

**WHY IT WAS NEVER A REAL HYPOTHESIS: out-count and vacated minutes are near-collinear.**

| outs | vacated minutes | hit% |
|---|---|---|
| 1 | 25.9 | 52.9% |
| 2 | 53.2 | 43.8% |
| 3+ | 77.3 | 51.1% |

"How many are out" and "how much production is vacated" are the same variable measured two
ways. You cannot control one for the other, and you cannot register them as two independent
findings — which is precisely what PR-001 (low-`vac` penalty) and PR-003 would have been.

**THE DECISIVE NUMBER.** Stratified on vacated minutes, the one stratum with BALANCED
comparison groups shows no penalty:

- HIGH vac: 2-out 49.5% (n=107) vs rest 51.1% (n=131) → **−1.6pp, z = −0.25**
- MID vac: 2-out 41.2% (n=233) vs rest 64.5% (**n=31**) → −23.3pp, but the comparison cell is
  31 rows hitting 64.5%, which is not a population, it is noise with a decimal point
- LOW vac: n=0 on the 2-out side — the strata cannot even overlap

The headline −8.5pp came from comparing 2-out situations against a *mixture* of low-vac 1-out
and high-vac 3+ groups. Same-sign consistency across 3 thirds and 3 markets did not save it,
because the confound is present in every cut.

**THE TRANSFERABLE LESSON — consistency across cuts is NOT evidence against a confound.** Six
same-sign slices felt like strong corroboration. They were six views of one collinearity. A
confound that lives in the variable itself reproduces in every subgroup you draw. What actually
discriminated was stratifying on the *suspected cause* and checking whether the comparison
groups were balanced inside each stratum. Do that before registering, not after.

**INCIDENTAL, AND A CAUTION FOR PR-001 — NOT a change to its frozen bar.** On this wide 836-row
population, holding out-count fixed, the vac effect is much smaller than the +28..+39pp PR-001
found on 61 tracked bets: **+8.0pp (z=+1.49) within 2-out, +1.4pp (z=+0.27) within 1-out.**
Direction agrees; magnitude does not. That is what a small-n selection effect looks like.
PR-001's promotion bar is UNCHANGED and remains forward-only on tracked bets — this is
retrospective context on a different population, recorded so the eventual forward read is
interpreted against a realistic prior rather than the inflated in-sample one.
