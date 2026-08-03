# ⛳ PGA golf-logic learning report

_2026-08-02T23:55:43Z · 48942 player-rounds, 130 events · PROPOSES ONLY, never applies_

Residuals are de-conditioned at the round level and use leave-one-event-out baselines, so a course playing harder or easier cannot masquerade as a finding. Every hypothesis below is scored against that residual, never against raw birdie counts.

A candidate must clear ALL of: |r| >= 0.05, n >= 400, |null| <= 0.02, and a sign that survives leave-one-event-out. Results that fail are listed too — a recorded null is what stops a dead idea being re-proposed every month.

| hypothesis | n | r | null | stable | effect (birdies/18) | verdict |
|---|---|---|---|---|---|---|
| wave (PM vs AM) | 45627 | -0.041 | -0.002 | yes | 0.07 | not supported |
| tee slot (hours from median) | 45627 | -0.036 | -0.004 | yes | 0.06 | not supported |
| round number | 46722 | -0.022 | -0.008 | yes | 0.04 | not supported |
| start tee (10th vs 1st) | 45627 | +0.021 | +0.007 | yes | 0.03 | not supported |
| prev_round_residual (H-P1 control) | 32038 | +0.013 | +0.003 | yes | 0.02 | not supported |
| par-5 skill x course par-5 share | 39171 | +0.011 | +0.015 | yes | 0.02 | not supported |
| cut pressure (R2) | 13104 | -0.011 | +0.002 | yes | 0.02 | not supported |
| position vs field entering round | 28859 | -0.001 | -0.003 | no | 0.00 | not supported |

## Candidates

_None cleared the bar this run._

## Our own flagged bets (the prompt, not the evidence)

Settled: **23-30**.

| | mean model p | mean market p |
|---|---|---|
| winners | 0.591 | 0.502 |
| losers | 0.485 | 0.403 |

| stream | record | mean model p | mean market p |
|---|---|---|---|
| birdies | 16-12 | 0.643 | 0.540 |
| birdies-lowprice | 2-2 | 0.544 | 0.460 |
| match | 1-2 | 0.450 | 0.388 |
| rscore | 2-9 | 0.469 | 0.397 |
| rscore-lowprice | 1-0 | 0.470 | 0.431 |
| top10 | 1-3 | 0.125 | 0.095 |
| top20 | 0-2 | 0.238 | 0.177 |

Price-floor split (round-scoped streams): kept side 15-6, floored side 6-17.

At this sample size this can only raise questions. Anything it suggests has to be answered against the field above before it means anything.


## Standing rule

This engine proposes. It does not tune, retrain, or adopt. Every candidate enters the evidence file as a hypothesis and must beat the frozen baseline on PROSPECTIVE data. Automated self-modification on ~10 bets a round is the failure that retired MLB, manufactured the original PGA edges, and forced the WNBA freeze after 132 logic changes against 151 graded bets.
