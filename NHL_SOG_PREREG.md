# PRE-REGISTRATION: an NHL shots-on-goal model (2026-11-02, 08:55 UTC, before code)

**User:** "yes run the test", after asking whether NHL SOG props are modelable and beatable, and about NHL EDGE data.
The NBA and NFL books priced public box scores well (`NFL_MODEL_PREREG.md`: A, B, C all fail). This is the same three
tests on NHL shots on goal: ice time by strength × shot-attempt rate by strength × on-target share × the opponent.
`nhl_sog.py`, Mac only.

**Data:**
- **Per-game skater stats:** the NHL stats reports (api.nhle.com/stats/rest, isGame), 2022-23 to 2025-26, regular
  season and playoffs. They give shots on goal; total, missed and blocked shot attempts; even, power-play and
  short-handed ice time; power-play shots and attempts; short-handed shots and attempts. Team shots against per game
  come from the team summary report. Cached in `.projdata/nhl_cache`.
  - Even-strength attempts = total − power-play − short-handed (floored at 0). The same subtraction gives shots.
- **Lines:** `~/tennis-odds-collector/icehockey_nhl_odds_hist.sqlite`, the snapshot near puck drop (`tip`), market
  `player_shots_on_goal`.
  - **The main line:** as in `NFL_UNDER_PREREG.md`. Among lines with a two-sided FanDuel or DraftKings price, it's the
    one whose over price is closest to even.
  - **The book's no-vig:** FanDuel's pair at that line, else DraftKings'.
  - **The bet price:** the better of the two books' prices at that line, per side.
- **Grading:** his shots on goal in the game. A whole-number line that lands exactly is a push and is dropped.
- **Matching:**
  - Event to game: the game's Eastern date and its two teams, with ±1 day allowed.
  - Player: the folded name among the game's skaters, else a unique last name + first initial. The unmatched share is
    reported.
- **No look-ahead:** history is his games before the game's date, this season and last. Nothing from the game day on is
  read.
- **EDGE is not used.** The EDGE endpoints answer season-to-date totals only, with no dated history, so any backtest
  would leak the future. If C passes, EDGE gets a forward snapshot, never a backtest.
- **Game script is left out.** The archive has no historical moneylines.

**Fit and test:**
- Every fitted number comes from 2023-24, with 2022-23 as history: the ice-time regressions, the position priors, the
  dispersion and the calibration.
- 2024-25 and 2025-26 are held out; nothing is fit on them.

## The model
- **Weights:** this season's games count 1 each. Last season's count min(1, 20 ÷ his games last season) each, so last
  season is worth at most 20 games.
  - A projection needs 3+ games across the two seasons.
- **1. Ice time by strength (even, power play, short-handed):**
  - One OLS per strength, fit on every 2023-24 skater-game with a projection.
  - Inputs: his last game's ice time at that strength, his last 5 games' mean (across seasons), and the weighted
    season mean.
  - Floored at 0.
- **2. Shot-attempt rate per hour by strength:**
  - The weighted attempts plus K hours × the prior, over the weighted hours plus K.
  - The prior is his position group's (forwards or defense) 2023-24 rate at that strength.
  - K is 3 hours at even strength, and 1 hour each on the power play and short-handed.
- **3. On-target share:** the weighted shots on goal plus 60 × the prior, over the weighted attempts plus 60. The prior
  is his position group's 2023-24 share.
- **4. The opponent:**
  - The opponent's shots against per game (this season before the date, last season counted as 20 games), over the
    mean of all teams' same number.
  - Pulled halfway to 1.
- **5. Projection:** Σ over strengths (projected minutes ÷ 60 × attempt rate) × on-target share × the opponent factor.
- **6. Probabilities:**
  - A negative binomial with that mean. Its size (dispersion) is fit by maximum likelihood on 2023-24 skater-games.
  - Then a logistic recalibration fit on 2023-24 main-line props: logit P(over) = b0 + b1 logit(model) + b2 logit(the
    book's no-vig over).
- **The plain average (the baseline):** his shots on goal per game with the same weights and the same 3-game minimum.

## The tests (2024-25 and 2025-26)
- **A, accuracy:**
  - The model's MAE against the plain average's on every graded main-line prop.
  - Also the line itself as a forecast.
  - **Passes** if the model's MAE is lower than the average's in both seasons.
- **B, the book:**
  - Log loss of the recalibrated P(over) against the book's no-vig.
  - **Passes** if lower in both seasons.
- **C, bets:**
  - Every main-line prop where the recalibrated p × the bet price − 1 ≥ 5% on either side.
  - **Passes** if pooled ROI > 0 with the 90% interval's low end > 0 (2,000 bootstrap draws, seed 5), and ROI > 0 in
    both seasons.
- **D, the NBA under rule on SOG (secondary):**
  - The plain average 30–50% below the main line, the under at −150 or better (as `NFL_UNDER_PREREG.md`).
  - Nothing is fit, so all three seasons count: 2023-24, 2024-25 and 2025-26.
  - **Holds** if the pooled ROI > 0 with the 90% low end > 0, and ROI > 0 in at least 2 of the 3 seasons.
- **Also (information):**
  - A variant with a plain shrunk shots-on-goal rate per hour in place of attempts × on-target. Same ice time, same
    opponent, K as above. It shows whether the attempts split adds anything.
  - Bets by side, by line (0.5, 1.5, 2.5, 3.5+), by position group, and regular season against playoffs.
  - The book's no-vig over against the actual over rate, by season.

A pass on C is a candidate for the forward record (NHL 2026-27, shadow), not a betting edge. No live change without the
user.

## Result (2026-11-02, about 09:50 UTC): A PASS, B PASS, C PASS, D DOES NOT HOLD
- **Fit on 2023-24:**
  - Minutes (1, last game, last 5, season mean): even 0.10 + 0.11 + 0.38 + 0.50; power play 0.02 + 0.08 + 0.36 +
    0.52; short-handed 0.03 + 0.05 + 0.43 + 0.48.
  - Negative binomial size 18.6.
  - The calibration puts 0.28 on the model and 0.71 on the book, intercept −0.07 (toward the under).
- **Matching:** 60,401 main-line props; 59,102 matched (1,299 players not found, every event found).

| | 2023-24 (fit) | 2024-25 | 2025-26 |
|---|---|---|---|
| **A** MAE, model / plain average / the line | 1.289 / 1.306 / 1.328 | 1.253 / 1.265 / 1.282 | 1.239 / 1.247 / 1.272 |
| **B** log loss, model / book | 0.68112 / 0.68306 | 0.68148 / 0.68283 | 0.68239 / 0.68241 |
| **C** EV ≥ 5% bets | — | 833, 50.7%, +8.3% | 570, 50.0%, +5.5% |

- **C pooled:** 1,403 bets, +7.1% [+2.5, +11.7]. 1,397 are unders.
  - By line: 1.5 +6.5% (479), 2.5 +10.3% (700), 3.5+ −1.2% (224).
  - By group: forwards +9.8% (999), defense +0.6% (404).
  - Regular season +7.8% (1,064), playoffs +5.0% (339).
- **D:** 45 pings, +21.6% [−1.5, +43.1]. Positive in all 3 seasons (+15.0% on 14, +0.3% on 11, +37.9% on 20), but the
  low end is below 0: does not hold.
- **Information:**
  - The attempts split adds nothing. The plain shots-on-goal rate variant has the same MAE and makes +6.0% on 1,396
    bets.
  - The line's MAE isn't a fair comparison: a half-number line is always at least 0.5 from the count.
  - The book's no-vig over against the actual over rate: 0.507 / 0.479, 0.504 / 0.484, 0.504 / 0.499.
- **Checks (after the result):**
  - **The book alone**, recalibrated on 2023-24 (an under lean): +2.7% [−1.4, +6.9] on 1,801 bets. That's +6.6% in
    2024-25 and −2.8% in 2025-26, as the over lean shrank.
    - Model bets the book alone doesn't make: +8.2% [+1.9, +14.5] on 752.
    - Model bets it also makes: +5.9% on 651.
    - So the model adds more than the books' over lean.
  - **One book's prices** (bet only where that book has the main line):
    - DraftKings: +6.7% [+1.7, +11.8] on 1,242 (+7.9%, +5.1%).
    - FanDuel: +16.6% [+5.6, +27.8] on 260 (+14.7%, +22.7%). FanDuel has the main line less often.
  - **Same-game bets as linked** (resampling the 852 games): 90% [+2.5, +11.8], unchanged.
- **Reading:**
  - The first public-data model that beats a book's closing number out of sample here, in two held-out seasons. The NBA
    and NFL models failed.
  - The edge is unders on forwards at 1.5 and 2.5. It's thin: 2025-26 alone is +5.5% with a low end below 0, and B's
    2025-26 margin is 0.00002.
  - Two seasons of backtest is not a betting edge. Per the plan it's a candidate for the forward record (NHL 2026-27,
    shadow, no bets).
  - Not checked: limits (NHL props are low-limit), and whether the prices at about 30 minutes before puck drop were
    really available.
