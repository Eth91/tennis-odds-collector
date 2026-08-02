# ⛳ PGA golf-logic learning report

_2026-07-31T09:57:23Z · 42557 player-rounds, 114 events · PROPOSES ONLY, never applies_

Residuals are de-conditioned at the round level and use leave-one-event-out baselines, so a course playing harder or easier cannot masquerade as a finding. Every hypothesis below is scored against that residual, never against raw birdie counts.

A candidate must clear ALL of: |r| >= 0.05, n >= 400, |null| <= 0.02, and a sign that survives leave-one-event-out. Results that fail are listed too — a recorded null is what stops a dead idea being re-proposed every month.

| hypothesis | n | r | null | stable | effect (birdies/18) | verdict |
|---|---|---|---|---|---|---|
| wave (PM vs AM) | 39482 | -0.040 | +0.006 | yes | 0.07 | not supported |
| tee slot (hours from median) | 39482 | -0.037 | +0.002 | yes | 0.06 | not supported |
| start tee (10th vs 1st) | 39482 | +0.023 | +0.013 | yes | 0.04 | not supported |
| round number | 40465 | -0.022 | -0.003 | yes | 0.04 | not supported |
| prev_round_residual (H-P1 control) | 27756 | +0.012 | +0.006 | yes | 0.02 | not supported |
| par-5 skill x course par-5 share | 38845 | +0.011 | +0.016 | yes | 0.02 | not supported |
| cut pressure (R2) | 11384 | -0.009 | -0.012 | yes | 0.01 | not supported |
| position vs field entering round | 25114 | -0.004 | +0.004 | yes | 0.01 | not supported |

## Candidates

_None cleared the bar this run._

## Standing rule

This engine proposes. It does not tune, retrain, or adopt. Every candidate enters the evidence file as a hypothesis and must beat the frozen baseline on PROSPECTIVE data. Automated self-modification on ~10 bets a round is the failure that retired MLB, manufactured the original PGA edges, and forced the WNBA freeze after 132 logic changes against 151 graded bets.
