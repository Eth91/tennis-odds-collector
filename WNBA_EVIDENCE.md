# WNBA v1.1 — cumulative evidence

_updated 2026-07-31T07:24:17Z · frozen 2026-07-31 · constants `433b9e32404d015d` · source `5a8bff53184574fd`_

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

### Registered open hypotheses

- **H-6 — should DvP carry more than TIEBREAKER weight?** `prop_edges` adds `dvp(opp,pos,stat) * proj_min` to `elev_avg` and nothing more, on the basis that the backtest looked marginal. Re-run leak-free on 954 spots (`dvp_backtest.py`), it is not marginal for the side we actually bet: OVERS into a soft positional defence went **27-12 / 69.2%**, overs into a tough one **14-17 / 45.2%** — a 24-point gap, n=70, z=2.02. MAE barely moves (2.85 to 2.84), which is how it was mistaken for marginal: it improves BET SELECTION far more than it improves the projection, and MAE cannot see that. Candidate change: gate or downweight overs where |coef| > 0.010 and the sign opposes the bet. NOT adopted — the 954 spots are the backtest's own universe, not our carded bets, so it must still clear the paired-SPRT rule prospectively.

- **H-5 — the correlation cap ranking.** SHIPPED as v1.1 (A-band before odds). It changed zero past bets because no historical contest had the split-band shape, so it is untested by construction. Watch whether the play it now keeps outperforms the one it used to.

  ⚠ **H-5 and H-6 disagree on the same bet.** POR 2026-07-31: DiLeo has the role expansion (+4.2 min, +3.1 FGA, tier A) but is a CENTRE into IND, our 3rd-toughest matchup vs C; Carleton has almost no role change (+0.3 min) but is a FORWARD into our 2nd-SOFTEST matchup vs F. H-5 keeps DiLeo, H-6 prefers Carleton. On current evidence H-6 rests on the larger and statistically significant sample (n=70, z=2.02) while the tier gap behind H-5 is not significant (A 82.4% vs B 60.7%, n=17/28, z=1.52). Do not resolve this by argument — it is why both are registered.
