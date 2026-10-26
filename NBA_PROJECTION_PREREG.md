# PRE-REGISTRATION — a calibrated NBA player-stat projection engine, measured against FanDuel's close

Written and committed **before any model code runs on a held-out period.** 2026-10-26.
Research only: projections are shown on the props page as model estimates, never as picks or bets.
Nothing here changes `nba_flags`, `LIVE_TIERS` (empty), or the "SHADOW · NOT A BET" behavior.

## The question
Can a projection built only from information available before tip produce **calibrated** full
distributions for player box-score stats, and do its over/under probabilities **add information
beyond FanDuel's closing price**? The honest prior from this repo: every NBA *selection* test so far
lost at the close (NBA_PRICE_EDGE_PREREG.md). So the primary aim is a trustworthy, measured
forecast. Beating the close is a claim to test, not to assume.

## Data, inspected before writing (counts and dates only; no model outcomes)
| source | content | coverage |
|---|---|---|
| `nba_gamelogs.sqlite.logs_full` (VM; stats.nba.com leaguegamelog) | one row per player-game, all box columns (min rounded to whole minutes, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta, ftm, oreb, dreb) | regular seasons 2022-23, 2023-24, 2024-25, 2025-26 — 1,230 games each |
| `nba_gamelogs.sqlite.positions` | the player index's position (G, F, C, G-F, …): static, as of fetch | all 877 players in logs_full |
| `nba_profiles.sqlite.team_games` | home/away per team-game | 2022-23 to 2024-25 |
| `nba_matchup.sqlite` (cdn.nba.com box scores) | player_games with starter flag, decimal minutes; games with home/away and scores | 2025-26, 2026-27 (to date) |
| `basketball_nba_odds_hist.sqlite` (The Odds API history, already used by earlier preregs) | one snapshot per game, **~29 min before scheduled tip** (2,572 of 2,670 events at −29 min), FanDuel, DraftKings, BetMGM, Caesars; **one main line per player-stat-book**, half points; points, rebounds, assists, threes, steals, blocks, PRA, P+R, P+A, R+A | 2023-24, 2024-25 (regular + playoffs; only regular graded) |
| `nba_lines.sqlite.quotes` (our collector; a CHANGE log) | FanDuel + DraftKings, main and alt rungs, every change with a timestamp; the board is rebuilt by carrying each book forward (`nba_research.replay`) | from 2026-10-22 09:34 UTC |
| `nba_news.sqlite.snapshots` | official injury report snapshots, published_at timestamps | from 2026-10-22 only |

Name matching (odds → player id): `nba_margin_refit.norm`, then a match within the game's two teams'
rosters on (first initial, last name), then a short alias table (Bub/Carlton Carrington, Herb/Herbert
Jones, Moe/Moritz Wagner, …). Before aliases, 98.8% (2023-24) and 97.6% (2024-25) of FanDuel rows
matched; ambiguous names are dropped, never guessed.

**Known gaps, stated now.** No point-in-time injury reports, starting lineups or news before
2026-10-22. The historical market (−29 min) knows about late scratches and starters; the historical
model does not. The model is handicapped against the close in 2023-25, by design and on the record.
Positions are static labels. Historical minutes are whole numbers.

## Prediction target and cutoff
- **Outcome**: for player *p* in regular-season game *g*, the vector
  `Y = (min, pts, reb, ast, fg3m, stl, blk, tov)`, **conditional on appearing** (min > 0 in the box
  score). This is the target books settle (a DNP voids the prop). Availability, P(appears), is a
  separate component (below).
- **Cutoff**: scheduled tip − 30 min. Allowed: box scores of games on **earlier dates** only (a
  same-day earlier game is never used — conservative). Market input, where a variant uses it: the
  latest price at or before the cutoff (historical: the −29 min snapshot; 2026-27: the board as of
  the cutoff). Injury input (2026-27 only): the latest official report published before the cutoff.
- **Combination markets** (PRA, P+R, P+A, R+A) are sums of the component draws of the **same**
  joint simulation, never sums of separately estimated distributions.

## Markets
| market | modeled | market benchmark |
|---|---|---|
| points, rebounds, assists, threes, PRA, P+R, P+A, R+A | yes | FanDuel close 2023-24 (tuning), 2024-25 (test), 2026-27 (prospective) |
| steals, blocks | yes | FanDuel close 2023-24 / 2024-25 only (our collector does not carry them) |
| turnovers | yes (box score only) | none: no book line in any source |
| anything else (double-doubles, first basket, quarters, …) | no | no data |

## Periods (chronological; whole dates, so a game never straddles a split)
| period | role |
|---|---|
| 2022-23 | history only: feeds features and the analog pool, never scored |
| **2023-24** | **tuning**: every hyperparameter and choice is made here |
| **2024-25** | **held-out test A**: stats + FanDuel close. Untouched by this model until the config is frozen in code (a git commit before the run) |
| **2025-26** | **held-out test B**: stats only (no historical lines for this season) |
| 2026-27 from 2026-10-22 | **prospective test C**: our own timestamped forecasts, FanDuel/DraftKings close from the change log, injury reports. Logged forward; reported with its (small) n |

2024-25 outcomes were graded by *earlier, different* tests in this repo (selection rules, price
shopping). No setting of this model is chosen on 2024-25 or later. That is the guard.

## Models compared
- **B1, season rate**: this season's per-minute rate × this season's average minutes (last season's
  when he has < 5 games this season).
- **B2, recent form, shrunk**: exponentially weighted per-minute rates and minutes, shrunk toward his
  longer-run averages.
- **B3, market**: FanDuel's de-vigged probability at its line (proportional de-vig of the paired
  prices); the line as the point forecast for MAE.
- **M1, the engine**: minutes (EWMA, shrunk) × per-minute rates (EWMA, partially pooled toward the
  league rate for his position group) × context (opponent's allowed rate for his group, blended with
  last season; pace; home; back-to-back), each context exponent chosen on 2023-24 (0 allowed = off).
  Distribution: an **analog ensemble** — the K prior player-games (all players, strictly earlier
  dates) whose own walk-forward predicted mean vectors are nearest, their realized outcome vectors
  rescaled per stat to this mean and rounded stochastically. Joint draws keep the covariance between
  stats and with minutes; combos are summed per draw.
- **M1+mkt**: logit blend `(1−w)·logit(p_M1) + w·logit(p_FD)`, w chosen on 2023-24. Evaluated only
  where the FanDuel price exists at the cutoff.
- **Availability** (shown, not part of the conditional target): P(appears | latest official status)
  estimated from 2026-27 reports + box scores with a Beta(1,1) prior and its n displayed. No fixed
  probability is assumed for "Questionable".

Tuning objective on 2023-24: mean CRPS over the 8 base outcomes, each divided by its 2022-23 standard
deviation; ties broken by FanDuel log loss. Search: coordinate descent over a fixed grid (written in
`nba_project.py` as `GRID`), at most 3 passes. The chosen config is written to `PROJ_CONFIG` and
committed **before** any 2024-25 or 2025-26 prediction is scored.

## Metrics
- Stat accuracy (B1, B2, M1; per stat): MAE, RMSE, CRPS (sample estimator), discrete log score
  (add-0.5 smoothing over the simulated pmf). Also the FanDuel line's MAE as a point forecast.
- Probability quality at FanDuel lines (two-sided at the cutoff, half points; an integer line pays a
  push, which is excluded and reported): Brier and log loss of P(over), for M1, B2 (with negative
  binomial marginals fit on 2023-24), B3 and M1+mkt; reliability tables by 10 buckets per market.
- Segments, all reported: market, season, projected-minutes band (<15, 15–25, 25–32, 32+), history
  depth (< 10, 10–40, 40+ prior appearances), favorite/underdog side.
- Uncertainty: date-clustered bootstrap (4,000 reps, seed 7) for every difference.
- CLV (prospective only): no-vig close probability of the side the model favors minus the no-vig
  probability at the time of the forecast. Positive = the market moved toward the model. CLV is not
  profit.

## Decision lines (written now)
| claim | required evidence |
|---|---|
| "M1 projects stats better than baseline X" | M1 − X mean CRPS < 0 with the 95% CI below 0, on **both** held-out A and B |
| "M1 is calibrated" | every reliability bucket with n ≥ 200 within ±3 percentage points on A, and PIT histogram deciles each within 10–12% |
| "M1 adds information beyond FanDuel's close" | M1+mkt − B3 log loss < 0 with the CI below 0 on A, **and** the same sign on C once C has ≥ 2,000 graded props |
| "M1 beats FanDuel's close" | M1 − B3 log loss < 0 with the CI below 0 on A **and** on C (≥ 2,000 props) |
| none of the above | the page shows the projection as a calibrated model estimate and says the close is better |

**Secondary, pre-specified, never tuned on A**: a flat-unit simulation on A at the −29 min FanDuel
price, betting the side where `p_M1+mkt − p_FD ≥ 0.03`. Report n, win rate, ROI with CI, and max
drawdown. Pushes are void, and unmatched or missing quotes are not bets.

## Leakage guards (tests that must exist before the A/B runs)
1. Changing any outcome dated on or after date *d* leaves every prediction for *d* unchanged.
2. The analog pool for date *d* contains only player-games dated before *d*.
3. Market inputs: snapshots at or before the cutoff only; the change log is replayed, never read as
   snapshots.
4. A traded player's rates follow the player; his opponent and his team are the ones on that night.
5. A DNP never enters a conditional target or the minutes history. It counts in availability.
   Postponed games (no box score) are absent.
6. The same game never appears in two periods.

## What the page will show (integration)
For each prop's player: projection mean and median, an 80% interval, P(over), P(under) and P(push)
at the selected line, the model version, the cutoff and "as of" time, the inputs used and missing,
and a stale state when its inputs are old. Every element is labeled as a model estimate, kept apart
from book prices, never a pick. Steals, blocks and turnovers are shown as projections with "no book
line collected".
