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

---

## Results (2026-10-28, about 08:55 UTC; `nba_rebmatch.py`): nothing passes
**Data:**
- Last-season profiles fetched for all 777 players (390 for 2022-23, 387 for 2023-24); none empty.
- 25,467 rebounds props: 13,275 in 2023-24 and 12,192 in 2024-25.
- **Baseline at 20+ mpg:** overs lose (−9.0% \| −7.9%); unders are near even (+0.4% \| −1.4%).

**A, the solver (over when xREB ≥ k × line).** Both seasons pick k = 1.36, which fails:
- 2023-24: −1.9% on 429;
- 2024-25: +4.3% on 399;
- the neighbouring k are not positive in both seasons.

The matchup adds nothing. At the same k, xREB (with the matchup) and xREB0 (without it) are within about a point of
each other:

| k | xREB, matchup | xREB0, no matchup |
|---|---|---|
| 1.2 | −3.7% \| −2.9% | −3.7% \| −2.1% |
| 1.3 | −3.5% \| −2.1% | −3.8% \| +0.5% |

xREB0's own picks also fail: 1.32 gives −3.2% → +0.8%, and 1.26 gives +2.2% → −3.5%.

**B, fixed thresholds** (n, ROI; 2023-24 \| 2024-25). All four fail.

| cell | result | baseline |
|---|---|---|
| B1 rim rebounder vs short misses, over | 518, −6.7% \| 395, −7.6% | overs −9.0% \| −7.9% |
| B2 long rebounder vs long misses, over | 2,741, −8.9% \| 2,817, −8.7% | overs |
| B3 rim rebounder vs few short misses, under | 536, +1.7% \| 386, −4.6% | unders +0.4% \| −1.4% |
| B4 long rebounder vs few long misses, under | 2,729, −0.4% \| 2,845, −3.1% | unders |

**C, logistic beyond the book.** It fails: held-out log loss is below the book's both ways, but only slightly, and
the bets don't win in both seasons.

| direction | log loss, model / book | bets |
|---|---|---|
| fit 2023-24 → test 2024-25 | 0.68469 / 0.68491 | 2,410 at −2.0% (2,341 unders) |
| fit 2024-25 → test 2023-24 | 0.68749 / 0.68838 | 1,609 at +4.9% |

Coefficients per SD (fit 2023-24 / fit 2024-25):
- **Same sign both ways:**
  - REB/g ÷ line: +0.068 / +0.036;
  - opponent's long-miss factor: +0.018 / +0.005;
  - minutes: +0.014 / +0.026;
  - near: −0.005 / −0.026;
  - intercept: −0.13 / −0.11 (overs are overpriced).
- **Inconsistent:**
  - M: −0.025 / +0.006;
  - opponent's short misses: −0.004 / −0.041 (the wrong sign for the rim-rebounder idea);
  - open: +0.002 / −0.036;
  - own-team misses: −0.015 / +0.011.

**Reading:**
- **Where the misses come from, and how far out a player grabs them, add nothing reliable beyond the line.**
- **As for points,** volume against the line (rebounds per game ÷ line) is the one consistent positive.
- **Books overprice rebounds overs** (−8% to −9% at 20+ minutes); unders are near even.
- **Not covered:** this test uses last season's profiles from a player's 6th game on, so the early-season window
  is not covered.
- **The chart is still useful as information:** where a player's rebounds come from, and how far out he grabs
  them. It is not a betting signal.
