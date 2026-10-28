# PRE-REGISTRATION: a rebounding matchup (where the misses come from, and how far out a player grabs them)

Written 2026-10-28 (about 08:10 UTC), before any feature below was fetched or computed. Research only: nothing is bet.

**User:** "ok backtest a rebounding matchup rule with that." "That" is NBA.com's rebound tracking:
- each player's rebounds by **grab distance** (how far from the hoop he secured them: 0–3, 3–6, 6–10, 10+ ft);
- his rebounds by the **distance of the missed shot** (0–6, 7–13, 13–19, 19+ ft);
- whether the rebound was contested.

This is published as totals per player for a date range, not per rebound.

## Data (2023-24 and 2024-25; no hindsight)
- **Player profile, from his previous full season** (2022-23 for 2023-24; 2023-24 for 2024-25). Source: stats.nba.com
  `playerdashptreb`, Regular Season totals. It needs ≥ 20 games last season (`logs_full`); otherwise the player is
  left out, which drops rookies. Fetched once per player and season on the Mac, into `.projdata/rebdist_hist.sqlite`.
  - **near** = share of his rebounds grabbed within 6 ft (0–3 + 3–6); **far** = 1 − near;
  - **open** = share with no one contesting;
  - **by miss distance:** DREB_b and OREB_b per game played, for the four miss-distance bands b.
- **Misses by distance, season to date** (games before the date only), from every shot in `shots_hist`. Distance =
  √(x² + y²) / 10 ft. The bands are < 7, 7–13, 13–19 and ≥ 19 ft. Free-throw misses are not in the shot data and are
  left out.
  - For each team: its own missed FGA per game, and its opponents' missed FGA per game, in each band.
  - A team's figures are shrunk toward the league per-team-game average with k = 10 games.
  - **f_opp,b** = tonight's opponent's own misses per game in b ÷ the league's.
  - **f_own,b** = the player's team's misses per game in b ÷ the league's.
- **Opportunity factor:** M = (Σ_b DREB_b·f_opp,b + Σ_b OREB_b·f_own,b) ÷ (Σ_b DREB_b + Σ_b OREB_b).
  - This scales each part of his rebounding by how many misses of that length tonight's game should produce.
  - Defensive boards come off the opponent's misses; offensive boards off his own team's.
- **Volume:** this season's REB per game and minutes per game, from games before the date. Needs ≥ 5 games this
  season.
  - **xREB** = REB/g × M.
  - **xREB0** = REB/g, the same with M = 1 (no matchup).
- **Props:** rebounds props from the archive, at the tip line (the FanDuel/DraftKings main closest to even). Each has
  the best over price, the best under price, and FanDuel's no-vig over (DraftKings' if FanDuel has none).
  - Results come from `logs_full`. Pushes are dropped.
  - Every rule requires mpg ≥ 20.

## The rules
**A. Solver (as in `NBA_PTS_PREREG.md` solver A).**
- **The rule:** over when xREB ≥ k × line, with k from 0.90 to 1.40 in steps of 0.02.
- **The pick:** the k with the best ROI (≥ 150 bets) on one season, checked on the other, both ways.
- **Pass:** positive on the season not seen, both ways, with the neighbouring k positive in both seasons.
- **Isolating the matchup:** xREB0 (no matchup) is run the same way beside it.

**B. The user's logic, fixed thresholds (no fitting).** Tertiles are the league's teams on the date, season to date.
- **B1, rim rebounder vs short misses:** near ≥ 0.75, and the opponent is in the top third for misses per game under
  7 ft → over.
- **B2, long rebounder vs long misses:** far ≥ 0.35, and the opponent is in the top third for misses per game at
  19+ ft → over.
- **B3, B4:** the mirrors (the bottom third) → under.
- **Pass, each cell:** ROI > 0 in both seasons and above its baseline in both. The baseline is all overs (or unders)
  on rebounds props at 20+ mpg.

**C. Logistic beyond the book (as in `NBA_PTS_PREREG.md` solver B).**
- **Inputs:** the logit of the no-vig over, plus standardized REB/g ÷ line, M, near, open, f_opp (< 7 ft),
  f_opp (19+ ft), the own team's total-miss factor, and mpg.
- **The fit:** on one season, with the L2 penalty chosen by 5-fold CV within it (log loss).
- **The test:** on the other season, bet the over or the under where P × best price − 1 ≥ 0.03, both ways.
- **Pass:** held-out ROI > 0 with ≥ 150 bets both ways, and held-out log loss below the book's both ways.

**Multiple looks:** A, B (4 cells) and C are 6 tests. Something passing by chance is likely at this count, so a
passing rule only enters the side-by-side at the opener (registered then), to be judged forward. No pings until a
forward record.

**If nothing passes:** the report says which parts carry information (C's coefficients) and which don't.
