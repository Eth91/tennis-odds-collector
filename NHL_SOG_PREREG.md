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
