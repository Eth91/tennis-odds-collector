# WNBA v1.2 — cumulative evidence

_updated 2026-08-02T05:53:29Z · frozen 2026-07-31 · constants `433b9e32404d015d` · source `323d26d55c6d35fc`_

_measurement only; this file never tunes the model_

## Verdict

**CONTINUE COLLECTING**

- LLR -0.290 inside (-1.558, +2.773) — undecided

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

Bets carded on or after the freeze date.

| metric | model | market |
|---|---|---|
| log loss | **0.81814** | 0.67321 |
| Brier | **0.30572** | 0.24004 |
| expected wins | 1.4 | 1.0 |
| actual wins | 1 | |

| | |
|---|---|
| settled / scored | 2 / 2 |
| record | 1-1 |
| P&L (1u flat) | -0.13u |
| ROI vs breakeven | -6.50% vs 52.9% |
| ROI 95% CI | -136.08% .. +123.08% |
| reliability slope | -34.483 |
| **SPRT log-likelihood ratio** | **-0.2898** |

## Retrospective, for context only — NOT part of the test

Produced by a model that was changing underneath it (132 commits / 151 bets). Reported so the freeze has a baseline, never as evidence.

| metric | model | market |
|---|---|---|
| log loss | **0.65631** | 0.70951 |
| Brier | **0.23461** | 0.25807 |
| expected wins | 30.6 | 21.1 |
| actual wins | 28 | |

| | |
|---|---|
| settled / scored | 50 / 43 |
| record | 28-15 |
| P&L (1u flat) | +18.87u |
| ROI vs breakeven | +37.73% vs 51.0% |
| ROI 95% CI | +10.29% .. +65.17% |
| reliability slope | -0.382 |
| **SPRT log-likelihood ratio** | **+2.2874** |

## Standing instruction

No model change is proposed or adopted on this evidence. Every modification is a new hypothesis and must clear the adoption rule above on PROSPECTIVE data.

### Registered open hypotheses

- **H-6 — should DvP carry more than TIEBREAKER weight?** `prop_edges` adds `dvp(opp,pos,stat) * proj_min` to `elev_avg` and nothing more, on the basis that the backtest looked marginal. Re-run leak-free on 954 spots (`dvp_backtest.py`), it is not marginal for the side we actually bet: OVERS into a soft positional defence went **27-12 / 69.2%**, overs into a tough one **14-17 / 45.2%** — a 24-point gap, n=70, z=2.02. MAE barely moves (2.85 to 2.84), which is how it was mistaken for marginal: it improves BET SELECTION far more than it improves the projection, and MAE cannot see that. Candidate change: gate or downweight overs where |coef| > 0.010 and the sign opposes the bet. NOT adopted — the 954 spots are the backtest's own universe, not our carded bets, so it must still clear the paired-SPRT rule prospectively.

  **FIRST TEST ON OUR OWN BETS (2026-07-31) — it does NOT transfer.** Refitting DvP as-of each bet's own date and applying the filter to the counted record makes it worse at EVERY threshold: drop coef<=-0.005 -> 20-14 / +4.53u (-14 bets, -14.52u); <=-0.010 -> 29-15 / +13.43u (-5.62u); <=-0.015 -> -4.54u; <=-0.020 -> -1.26u, against a 33-15 / +19.05u baseline. The split is REVERSED here: our overs into a TOUGH positional defence went 4-0 (+5.62u) where the backtest's universe gave 45.2%. Plausible mechanism: the backtest scores general props, while our bets are injury-beneficiary overs whose minutes and usage are exploding — role expansion dominates matchup, so a tough defence costs far less than it does for an ordinary prop. ⚠ n=4 in that bucket proves nothing on its own; it merely fails to confirm. Also 17 of 48 bets could not be resolved to a position/opponent and went 9-8 (52.9%), worse than the resolved ones — worth its own look. CONCLUSION: do not gate on DvP; keep it as the tiebreaker it is, and let the prospective record settle it.

- **H-5 — the correlation cap ranking.** SHIPPED as v1.1 (A-band before odds). It changed zero past bets because no historical contest had the split-band shape, so it is untested by construction. Watch whether the play it now keeps outperforms the one it used to.

  ⚠ **H-5 and H-6 disagree on the same bet.** POR 2026-07-31: DiLeo has the role expansion (+4.2 min, +3.1 FGA, tier A) but is a CENTRE into IND, our 3rd-toughest matchup vs C; Carleton has almost no role change (+0.3 min) but is a FORWARD into our 2nd-SOFTEST matchup vs F. H-5 keeps DiLeo, H-6 prefers Carleton. On current evidence H-6 rests on the larger and statistically significant sample (n=70, z=2.02) while the tier gap behind H-5 is not significant (A 82.4% vs B 60.7%, n=17/28, z=1.52). Do not resolve this by argument — it is why both are registered.
