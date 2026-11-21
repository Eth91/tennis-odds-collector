# NBA_Q15: a search for a 15%+ ROI NBA model, with the test sets fixed in advance (pre-registered 2026-10-31, about 09:05 UTC)

**The user's brief:** build, test and validate an NBA betting model with a real, sustainable 15%+ ROI after the vig.
Don't stop at the first failure, and never call a backtest a success. Research only: nothing is bet, and
`nba_flags.LIVE_TIERS` stays empty.

This file fixes the data split, the candidate limit and the pass bar **before any model is fit**. Every experiment is
logged in `NBA_Q15_LOG.md`, failures included.

## What data exists (inspected 2026-10-31, before any outcome)
- **Prop prices:** `basketball_nba_odds_hist.sqlite`.
  - One snapshot about 30 minutes before tip, main lines only (no alternate ladders), both sides.
  - FanDuel, DraftKings, BetMGM, Caesars. 8 markets used: points, rebounds, assists, threes, P+R, P+A, R+A, P+R+A.
  - 2023 playoffs through 2025 playoffs.
- **No historical prices for moneylines, spreads, totals, first halves, quarters or team totals,** and no live
  prices. Those markets can be modelled for accuracy only, so they can't produce a demonstrated ROI. They are left
  out, and this is said in the report.
- **Box scores:**
  - `nba_gamelogs.sqlite` logs_full: regular seasons 2022-23 to 2025-26.
  - `nba_postseason.sqlite` logs_post: play-in and playoffs 2023 to 2025.
- **Live (this season):** the VM's `nba_lines.sqlite`, FanDuel and DraftKings from 2026-10-22, every price change,
  openers and ladders included.

## What earlier studies used (why the split is what it is)
- **Regular-season prices, 2023-24 and 2024-25:** used by more than 10 earlier studies. These include
  NBA_PRICE_EDGE, T4, the WNBA pricing transfer, the projection tests, UNDER and its 35-range grid, BOOST and
  ROLES_L3. They are **development data**, whatever is done here: a rule found on them carries the selection of
  every earlier look.
- **Postseason prices, 2023-2025:** used once, only for NBA_PLAYOFF_HOLDOUT's two cross-book price leads. No
  projection, under or model rule has been graded on them.
- **This season (2026-27):** forward.

## The split
| set | games | use |
|---|---|---|
| **TRAIN** | 2023-24 regular season (features also read 2022-23) | fitting, walk-forward by month |
| **VALIDATE** | 2024-25 regular season | choosing a model family, features and EV threshold |
| **TEST A** | postseasons 2023, 2024, 2025 | **once** per frozen candidate, never used to choose |
| **TEST B** | 2026-27 forward, shadow | decides "validated" |

## Rules for every model
- **Features use only games before tonight.** The one exception is "teammates out tonight": it comes from the box
  score, which is mild hindsight because by tip − 30 the inactive list is almost always known. Test B uses the
  injury report instead.
- **Prices:**
  - The bet is graded at the book's own price at its own line.
  - **Primary:** the better of FanDuel and DraftKings, the two books the live system reads.
  - **Secondary:** the best of all 4 books.
- **The market's view:** the proportional no-vig probability of each book's pair, averaged over the books posting
  the consensus main line.
- **Grading:**
  - Over or under the line, win at the price; a push is the stake back.
  - A player who doesn't play is void.
  - Flat 1 unit per bet.
- **Reported for every candidate:**
  - ROI; bets (total and by season or block);
  - win rate against the break-even rate;
  - units; maximum drawdown;
  - a 90% and a 95% bootstrap interval resampling player-games;
  - Brier score and log loss against the market's;
  - ROI by market, side, price band and season.
  - CLV can't be measured historically (one snapshot); it is reported on Test B.

## Candidates and the pass bar
- **At most 5 frozen candidates go to Test A.** Their names, code fingerprints and thresholds are logged before
  Test A is graded.
- **A candidate passes Test A only if all hold:**
  1. ROI ≥ +15% on Test A at the primary prices;
  2. at least 300 bets on Test A;
  3. ROI > 0 in each of the 3 postseasons;
  4. the one-sided bootstrap lower bound on ROI is above 0 at α = 0.05 / 5 (Bonferroni over the 5 slots);
  5. on VALIDATE it also had ROI ≥ +10% and ROI > 0 in each half-season.
- **A Test A pass is a candidate, not a validated model.** It is validated only after Test B:
  - at least 200 forward shadow bets at the price posted when the signal fired (not at tip);
  - ROI ≥ +10%;
  - mean CLV against FanDuel's closing no-vig > 0.
- **If nothing passes, the report says so.** It names the strongest model, how far it falls short, and what data
  would be needed next.

## Model families to try (on TRAIN / VALIDATE only)
1. **Baselines:**
   - the market's calibration (Brier, log loss) by market, line and price;
   - every over and every under at the primary prices.
2. **A market-anchored logistic model:** logit(p) = logit(market) + β·x, L2-penalized, fit walk-forward.
3. **Gradient boosting on the market's residual:** LightGBM with the market logit as the starting score, shallow
   and heavily regularized.
4. **A distribution model:** minutes × per-minute rate, a negative binomial with each player's own spread, blended
   with the market.
5. **Simple rules** (projection ratio, line against recent averages) as reference points.

**Features, all from before tonight:**
- his minutes and per-minute rates (last 3, 5 and 10 games, season, last season);
- the stat's mean, median and spread;
- games played; rest days and back-to-backs; home or away;
- the opponent's allowed rate for the stat; both teams' pace;
- minutes vacated by teammates out tonight;
- the line against his averages; the over/under price gap;
- how much the 4 books disagree on the line; FanDuel against the consensus.

## Honest limits, stated now
- One snapshot at tip − 30: no timing edge can be tested historically.
- Prop limits are low, and books limit winning accounts. An edge on paper may not scale.
- Since 2026-10-16, books restrict unders on players projected under 12 minutes. A strategy relying on those unders
  can't be executed now, and is reported with and without them.
