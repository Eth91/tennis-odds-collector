# PRE-REGISTRATION: the user's points process, encoded and tested

Written 2026-10-27 (about 09:50 UTC), before any feature below was computed on lines. Research only: nothing is bet.

**User (an example):** "Duncan Robinson o12.5 pts today."
- He has good minutes in all three games, and takes 10–12 shots a game, 9–10 of them threes, shooting them
  efficiently.
- He shoots 2–8 free throws a game, "bonus extra volume that's more random."
- The matchup is neutral where he takes most of his shots: 68% above-the-break threes, where the Knicks are
  −0.8 pts a game against league average, and 12% right-corner threes, where they are +2.3.
- "That's most of my thought process I'd like to encode ... I just don't know the optimal criterion or
  percentages and ratios for each stat, like efficiency by spot where they take most of their shots."

## Data (2023-24 and 2024-25, season to date, strictly before the game's date; no hindsight)
- **Shots by zone:** every shot (`.projdata/shots_hist.sqlite`), in the zones of `nba_zones`: RA, Paint, Mid,
  Corner 3, Above-break 3.
- **Box scores:** minutes, FGA, 3PA, FTA, FTM, points (`logs_full`).
- **Props:** the archive's points props at the tip line (FanDuel/DraftKings main), with both prices.

## The features (per player, per game)
- **Volume, per game:** mpg, FGA, 3PA, FTA.
- **Shot mix:** 3PA share; the share of attempts in each zone.
- **Efficiency:** FG%, 3P%, FT%, eFG%, TS%. Zone FG% is shrunk toward the league's zone FG% with 20
  pseudo-attempts.
- **xPTS:** Σ over zones of attempts/g × shrunk zone FG% × (2 or 3) + FTA/g × FT% (FT% shrunk toward the
  league's with 20 pseudo-attempts). This is volume × efficiency by spot.
- **xPTS_m:** the same, with each zone's term × the opponent's points allowed in that zone ÷ the league's
  (season to date, opponent ≥ 10 games). This is the user's "where he shoots vs where they give up points."
- **Ratios to the points line:** FGA, 3PA, FTA, xPTS and xPTS_m, each ÷ the line.

## Solver A: the encoded process as one number
- **The rule:** the points over when mpg ≥ 20 and xPTS_m ≥ k × the line.
- **The sweep:** k from 0.90 to 1.40, step 0.02.
- **The pick:** the k with the best ROI (≥ 150 bets) on one season, checked on the other, both ways.
- **Pass:** positive on the season not seen, both ways, with the neighbouring k positive in both seasons (as in
  `NBA_RATIO_PREREG.md` amendment 1).
- xPTS (without the matchup) is reported beside it.

## Solver B: learn how much each stat matters
- **The model:** logistic regression for P(over), on points props with mpg ≥ 20. Pushes are dropped.
- **Its inputs:**
  - logit of the book's no-vig over (FanDuel's pair, else DraftKings'), so the model learns what the stats
    add beyond the line;
  - standardized features: FGA/line, 3PA/line, FTA/line, xPTS/line, xPTS_m/line, FG%, 3P%, FT%, eFG%,
    TS%, 3PA share, mpg.
- **The fit:** on one season, with the L2 penalty chosen by 5-fold cross-validation within it (log loss).
- **The test:** on the other season, bet the over where P × best over price − 1 ≥ 0.03. Then both ways.
- **Reported:**
  - the coefficients, which say which parts of the process carry information;
  - held-out log loss against the book;
  - held-out bets, ROI and hit rate.
- **Pass:** held-out ROI > 0 both ways with ≥ 150 bets each, and held-out log loss below the book's both ways.

**If A or B passes:** its rule enters the side-by-side at the opener, registered with a fingerprint. Pings come
only after a forward record.

**If neither passes:** the report shows which stats carry information and which don't.
