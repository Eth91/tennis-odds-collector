# PRE-REGISTRATION: four modeling tests (2026-10-28, about 22:00 UTC, before any code or data)

**User:** "I feel like we can model better, why not test more." The user chose all four of:
- usage vs efficiency;
- where the book is wrong;
- low lines;
- who takes his shots.

Research only: nothing changes live without the user.

## Shared
- **Data:**
  - `.projdata/nba_gamelogs.sqlite` logs_full 2022-23 to 2025-26 (with FGM/FTM);
  - NBA.com's lineups (`.projdata/nba_stats_raw.sqlite`) for starter flags 2023-26;
  - the 4-book tip-line archive (FanDuel/DraftKings main: the rung with the over nearest even, best over and best
    under across the two, the no-vig over from FanDuel's pair, else DraftKings').
- **Seasons:** fit on 2023-24; tip-line tests on 2024-25. 2025-26 has no odds, so it is used only for projection
  errors.
- **Projection** for every player with a line (`nba_lowend.projections`, population "ALL"): ROLE1 v3 minutes ×
  `nba_boost.rates` (last season worth 150 minutes). Everything reads only games before the date. Tonight's
  box-score outs are hindsight, as in BOOST's backtest.
- **"X-out night":** a usual starter (the lineup tab's usual five; 26+ min/g without starter flags) did not play,
  absence game 1–3. **"New starter":** a confirmed starter tonight outside the usual five.
- **Grading:** stat > line wins at the price, < loses, = pushes. Bootstrap 90% intervals reported.

## T1: usage vs efficiency
- **Question:** on X-out nights, are teammates less efficient than their own norm (TS% = pts ÷ (2 × (FGA + 0.44 ×
  FTA)))?
- **Measure (2023-24):** TSA-weighted mean of (tonight's TS% − his baseline TS%), where the baseline covers his games
  before the date, both seasons, any team. Reported on X-out nights against normal nights, in 4 cells:
  - new starter or other teammate;
  - × X is or is not his team's top FGA player.
- **Adjustment:** δ_cell = (X-out − normal) for each cell on 2023-24. The adjusted points projection = projection ×
  (1 + δ_cell ÷ his baseline TS%).
- **Pass:**
  - the 2024-25 δ's (measured the same way) have the same sign as 2023-24's in the two cells with the most rows;
  - and the adjusted points MAE on X-out nights is below the unadjusted in 2024-25 and 2025-26.
- **Bets (information):** points overs at projection ≥ 1.15 × line, −150 or better, adjusted against unadjusted,
  2024-25.

## T2: where is the book wrong
- **Rows:** every prop at the tip lines in points, rebounds, assists, threes, P+R, P+A, R+A and PRA, for players who
  played, pushes dropped.
- **Target:** over (1) or under (0).
- **Features:**
  - logit(book no-vig over), the line, projection ÷ line;
  - projected minutes − his last-10 minutes, his season mpg, his last-5 stat ÷ his season mean;
  - starters out on his team, new starter (0/1), X-out night (0/1), the smallest absence game;
  - rest days (capped at 4), back-to-back, the game's index, the market (one-hot).
- **Models:** logistic regression (L2, C = 1, standardized) and HistGradientBoostingClassifier (defaults, random_state
  0), fit on 2023-24.
- **Test (2024-25):** log loss of each model against the book's no-vig. Bets on either side where model p × best price
  − 1 ≥ 0.05, at the best FanDuel/DraftKings price.
- **Pass:** a model's 2024-25 log loss is below the book's and its EV ≥ 5% bets have ROI > 0 with ≥ 100 bets. 2023-24 is
  reported in-sample.

## T3: low lines
- **Rows:** props with line 0.5 or 1.5 in threes, assists and rebounds.
- **Model:** P(stat > line) under a negative binomial with mean = the projection and dispersion r. One r per market is
  fit by maximum likelihood on 2023-24, over all of that market's player-games with a projection (not only low
  lines). As an alternative for information, the share of his last 20 games over the line.
- **Bets:** either side where p × best price − 1 ≥ 0.05.
- **Pass:** ROI > 0 in 2023-24 and in 2024-25, each with ≥ 100 bets, and the 2024-25 log loss below the book's.

## T4: who takes his shots
- **Rows:** teammates who played on X-out nights.
- **Shot share:** his FGA ÷ his team's FGA. share_with is over past team games X played; share_without over past
  team games X missed while on the team. Both from this season and last.
- **Projection:** FGA_s = team FGA per game (this season's games before the date if 3+, else last season's) ×
  (share_with + w × (share_without − share_with)), w = n_without ÷ (n_without + 5). 3PA_s is the same with 3PA.
  - Points_s = FGA_s × his points per FGA; threes_s = 3PA_s × his 3P% (his games before the date, both seasons).
- **Baseline:** FGA = V3 minutes × his FGA rate; points and threes as in the shared projection.
- **Pass:** FGA MAE of FGA_s below the baseline's in 2024-25 and 2025-26, and points/threes overs at projection_s ≥ 1.15 ×
  line (−150 or better) with ROI > 0 in 2024-25 and ≥ 100 flags. 2023-24 is reported.

## Afterwards
Each test's result goes to the user. A pass means "worth a forward test", not "it works". Nothing is deployed without
the user's go-ahead.
