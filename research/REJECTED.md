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

## EXP-026 — THE SITUATION CARRIES NO SIGNAL (2026-08-15)

**The axis was: can a situation-level gate work without `p_adj` or any probability-derived
ranking? The answer is NO, and not because the gate was built badly — because the situation
itself is not informative.**

Flagged selections vs non-flagged market main lines, 2026-08-05..08-14, on a reconstructed
11-day line archive:

| | flagged | non-flagged main | gap |
|---|---|---|---|
| ALL | 44.4% (n=277) | 44.3% (n=734) | **+0.1pp, z=+0.04** |
| points | 44.2% (n=113) | 44.2% (n=285) | +0.0pp |
| rebounds | 47.4% (n=95) | 46.5% (n=243) | +0.9pp |
| assists | 40.6% (n=69) | 41.7% (n=206) | −1.2pp |

Zero in every market. **Identifying the beneficiary of an absence is worth 0.1pp.**

This CORROBORATES and quantifies the existing finding that big WOWY/usage/minutes deltas are
not what makes a beneficiary over hit. It extends it from the tracked pool to a 1011-row
like-for-like comparison with a real baseline.

**THE STRATEGIC CONSEQUENCE.** Whatever edge the tracked system has cannot be coming from
situation identification. It has to come from the PRICE side — the EV gate and the TOP-2
ranking — because the situation pool it draws from is indistinguishable from random. Research
effort spent on better situation variables is spent on a channel measured at +0.1pp. Every
future situation-variable hypothesis inherits this ceiling and should be scoped against it.

### ⚠️ EXP-023 and EXP-024 ARE VOID — and how they lied

Both reported the flag beating the market by **+12.8pp (z=5.53)** and **+12.0pp (z=2.54)**.
Both were wrong, for two independent reasons, and both looked healthy:

1. **`wnba_lines.sqlite` is a 3-DAY ROLLING BUFFER.** 1.5M rows spanning 2026-08-13..08-15 ONLY.
   Querying `WHERE date BETWEEN '2026-07-12' AND '2026-08-14'` returns rows and raises no error
   — it silently answers about 2 days while appearing to answer about 34. Row COUNT looks
   enormous (1.5M) precisely because a buffer is dense, not long. **Always check
   `COUNT(DISTINCT day)`, never `COUNT(*)`, before trusting a window.**
2. **The market pool was the ALT LADDER.** One player's 2.5 main line also appears at 4.5/5.5/6.5.
   The tell was a monotone slide in over% with line level inside every stat (assists 62.9 → 51.3
   → 39.5 → 25.0 → 13.2%). Comparing our selections to that pool compares main lines against
   longshots and manufactures a large fake edge.

**The gate that caught it:** a main line must hit ~47-48% overs after vig. EXP-024's pool
measured 40.5%, which is not a base rate, it is a defect. That single check is now mandatory
before any market-relative claim — it is cheap, it is outcome-independent, and it would have
killed both experiments before they were written up.

**INFRASTRUCTURE BUILT:** `research/build_line_archive.py` → `research/line_archive.sqlite`,
19,287 rows / 11 real days (2026-08-05..08-15), reconstructed by unioning the daily backups
(each itself a 3-day window). One row per (date, player, stat, line, side) = last pre-game
quote. This is the only WNBA line history that exists; the live DB cannot answer any question
spanning more than 3 days. Research-only, imported by nothing in production.
