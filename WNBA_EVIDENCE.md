# WNBA v1.0 — cumulative evidence

_updated 2026-07-30T22:27:03Z · frozen 2026-07-30 · constants `433b9e32404d015d` · source `ac6530fe526aa9e6`_

_measurement only; this file never tunes the model_

## Verdict

**INSUFFICIENT DATA**

- no prospective settled bets yet

## Pre-registered test (fixed 2026-07-30, before any prospective bet)

| | |
|---|---|
| universe | graded overs → `current_selection` → confidence ∈ {confirmed, likely} |
| H0 | outcomes at the DEVIGGED market rate (odds vs odds_other) |
| H1 | outcomes at the model rate (`proj_hit`) |
| boundaries | reject H0 at LLR ≥ +2.773; accept H0 at LLR ≤ -1.558 |
| halts | H-1 lower boundary · H-2 slope < 0.7 over 100 · H-3 n≥60 and ROI CI upper < 0 · H-4 fingerprint drift / stale feed |
| adoption | a challenger must win a PAIRED SPRT over ≥ 60 PROSPECTIVE settled bets |

## Prospective record (this is the test)

_none yet_

## Retrospective, for context only — NOT part of the test

Produced by a model that was changing underneath it (132 commits / 151 bets). Reported so the freeze has a baseline, never as evidence.

| metric | model | market |
|---|---|---|
| log loss | **0.64241** | 0.71012 |
| Brier | **0.22810** | 0.25837 |
| expected wins | 28.7 | 19.6 |
| actual wins | 27 | |

| | |
|---|---|
| settled / scored | 47 / 40 |
| record | 27-13 |
| P&L (1u flat) | +20.02u |
| ROI vs breakeven | +42.59% vs 50.8% |
| ROI 95% CI | +14.66% .. +70.52% |
| reliability slope | -0.233 |
| **SPRT log-likelihood ratio** | **+2.7087** |

## Standing instruction

No model change is proposed or adopted on this evidence. Every modification is a new hypothesis and must clear the adoption rule above on PROSPECTIVE data.
