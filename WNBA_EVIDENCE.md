# WNBA v1.1 — cumulative evidence

_updated 2026-07-31T06:09:52Z · frozen 2026-07-31 · constants `433b9e32404d015d` · source `5a8bff53184574fd`_

_measurement only; this file never tunes the model_

## Verdict

**INSUFFICIENT DATA**

- no prospective settled bets yet

## Pre-registered test (fixed 2026-07-31, before any prospective bet)

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
| log loss | **0.64859** | 0.70990 |
| Brier | **0.23090** | 0.25827 |
| expected wins | 30.0 | 20.6 |
| actual wins | 28 | |

| | |
|---|---|
| settled / scored | 49 / 42 |
| record | 28-14 |
| P&L (1u flat) | +19.87u |
| ROI vs breakeven | +40.54% vs 50.9% |
| ROI 95% CI | +13.10% .. +67.98% |
| reliability slope | -0.561 |
| **SPRT log-likelihood ratio** | **+2.5751** |

## Standing instruction

No model change is proposed or adopted on this evidence. Every modification is a new hypothesis and must clear the adoption rule above on PROSPECTIVE data.
