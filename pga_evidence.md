# PGA v1.0  frozen 2026-07-30 — cumulative evidence

_updated 2026-07-30T20:51:18Z · measurement only; the model is frozen and this file never tunes it_

## Verdict

**INSUFFICIENT DATA**

- no settled bets carrying both probabilities yet

## Pre-registered test (fixed 2026-07-30 at n=0)

| | |
|---|---|
| H0 | outcomes occur at the devigged market rate `p_fair` |
| H1 | outcomes occur at the model rate `p_bet` |
| boundaries | reject H0 at LLR >= +2.773; accept H0 at LLR <= -1.558 |
| alpha / beta | 0.05 / 0.2 |
| halt | H-1 lower boundary · H-2 slope < 0.7 over 200 · H-3 n>=100 and ROI CI upper < 0 · H-4 data integrity |
| adoption | a challenger must beat the frozen baseline on a PAIRED SPRT over >= 100 prospective settled bets |

## Evidence

No scored bets yet. Settled rows in the ledger: **0**

Nothing can be concluded. The first scorable bets arrive when a tournament settles with `p_bet`/`p_fair` recorded.

## Shadow streams (candidate hypotheses — NOT in the v1.0 test)

No settled shadow bets yet. `E3-cut-shadow` logs but cannot arm until it beats the frozen baseline on a paired SPRT over >= 100 prospective settled bets.

## Standing instruction

No model change is proposed or adopted on this evidence. Every modification is a new hypothesis and must clear the adoption rule above on PROSPECTIVE data. Retrospective improvement on data the change was designed against counts for nothing.
