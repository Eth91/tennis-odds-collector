# PRE-REGISTRATION — NBA tracking stats in the WNBA pricing model (real lines, at the close)

Written and committed **before any tracking data is fetched**. 2026-10-23.

## Why
The WNBA pricing machinery, run unchanged on NBA real lines (`NBA_PRICING_PREREG.md`), lost
−3.46% over 1,186 bets and was **overconfident by 10-17 points of probability**: it judges a
beneficiary by how often his own elevated-role games cleared the line, and 10-20 such games are a
noisy sample. A rebound or an assist is an opportunity *plus* a conversion; the conversion part is
mostly luck game to game. The NBA measures the opportunity directly — **rebound chances** and
**potential assists**, per game, back to 2022-23 (verified 2026-10-23). The WNBA has no such data.

## The single change under test — Arm S ("smoothed")
Arm T exactly as tested (`nba_pricing.price` → `wnba_tonight.prop_edges`, base rung,
`current_selection`, the four NBA departures), with ONE input change. In the beneficiary's game log
and in his with/without-X split, every game's
- `reb` is replaced by `reb_chances × p_reb(B)`,
- `ast` is replaced by `potential_ast × p_ast(B)`,
- combos (pra, pts_reb, pts_ast, reb_ast) are rebuilt from the replaced components; points, minutes
  and shot columns are untouched.

`p_reb(B)` / `p_ast(B)` = B's conversion (rebounds ÷ rebound chances; assists ÷ potential assists)
over his PRIOR games in the 400-day pool — strictly before the game date — shrunk toward the
league rate with **K = 40** pseudo-opportunities. The league rates are computed from the
**2022-23 season only**, which precedes every test date. Nothing else is fitted. A game with no
tracking row keeps its real value and is counted.

## Data
`stats.nba.com/stats/leaguedashptstats`, `PtMeasureType=Passing` and `=Rebounding`, one call per
game date with `DateFrom = DateTo` (verified: every row is one game, GP = 1), regular seasons
2022-23, 2023-24, 2024-25. **Integrity gate before any test runs**: the tracking feed's own AST and
REB must equal the box score's on ≥ 99% of joined player-games, or the data is treated as broken
and nothing is run.

## Universe, books, counting — identical to Arm T
WOWY tier (absence game 1-2, X ≥ 28 min trailing-10, B with ≥ 2 games without and ≥ 3 with),
FanDuel + DraftKings best price, base rung, overs, `current_selection`, flat 1 unit. Split for the
halves: 2024-10-29. Date-clustered bootstrap 95% CI (4,000 reps, seed 7).

## Decision lines — Arm S, pooled
| verdict | condition |
|---|---|
| **KILL** | pooled ROI ≤ 0, **or** halves disagree in sign, **or** Arm S does not beat Arm T's ROI in the same run |
| **B — informative** | pooled ROI > 0, both halves > 0, beats Arm T, CI lower bound ≤ 0 |
| **A — actionable** | the above with CI lower bound > 0 |
| thin | n < 100 → KILL for wiring |

Arm T is re-run in the same pass (it must reproduce −3.46% / n = 1,186, or the harness changed and
nothing is concluded). Must also beat the always-over null on the same candidates.

## Secondary — information only
Calibration of the model's stated probability against the realised hit rate, by EV band, Arm S vs
Arm T (the defect this is aimed at); per-stat ROI (the change only touches rebound/assist markets;
points-only bets are identical in both arms).

## What a pass would and would not mean
This is a test **at the close**, like every NBA test before it. A pass would justify a new shadow
tier (`priced_trk`) in the forward speed test via its own amendment — never a change to the
existing `priced` tier, whose forward record must stay what it was registered as. A pass does not
authorise money.
