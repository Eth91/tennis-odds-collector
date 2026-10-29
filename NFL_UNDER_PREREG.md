# PRE-REGISTRATION: does the NBA under finding hold in the NFL? (2026-10-29, about 21:50 UTC, before code or data)

**User:** "test if the nba under finding works for nfl."

**The NBA finding** (`NBA_UNDER_PREREG.md`):
- The under, when our projection is far below FanDuel's main line, beat the book in 2023-24 and 2024-25.
- The ping set (30–50% below, under −150 or better, not threes) made +16.8% | +15.0%.
- The book's no-vig over ran above the actual over rate (49.2% against 47–48.5%).

Here the same rule is applied to the NFL, with nothing fit on NFL data, so every NFL season is a test.
`nfl_under.py`, Mac only.

**Data:**
- **Lines:** `americanfootball_nfl_odds_hist.sqlite`, 2023-24, 2024-25 and 2025-26 (855 games), the snapshot about 30
  minutes before kickoff.
  - The main rung: FanDuel's or DraftKings' line, both sides priced, with the over nearest even money, as `nba_tests4.tip_lines`.
  - The under at the better of the two books' prices; the no-vig over from FanDuel, else DraftKings.
- **Results and history:** nflverse weekly player stats for 2022 to 2025, regular season and playoffs.
  - A game is matched by season and teams; a player by his folded name among the two teams' players that week.
  - A player without a stat row that week is not graded.

**Markets (the headline set):** passing yards, attempts and completions; rushing yards and attempts; receptions;
receiving yards; rushing + receiving yards.
- Passing TDs and interceptions are small counts like the NBA's threes. They are reported apart, not in the headline.
- Anytime TD has no under and is left out.

**The projection:**
- His per-game average this season before the game, with last season's per-game average counted as 4 games.
  This mirrors the NBA's rates, where last season counts as 150 minutes, about 4–5 games.
- He needs 3+ games across the two seasons.
- It is cruder than the NBA's V3, which knew who was out; the NFL side has no such model.

**The rules (fixed from the NBA):**
- **UNDER20:** projection < 0.80 × the line.
- **The 20%+ set:** UNDER20 with the under at −150 or better, headline markets.
- **The ping set:** the 20%+ set at 30–50% below the line (projection ÷ line in [0.50, 0.70)).

**Reported:**
- Count, hit rate and ROI (90% bootstrap) per season and pooled, by market.
- The book's no-vig over against the actual over rate on every headline prop.

**It holds when** the ping set's pooled ROI is above 0 with the 90% interval's low end above 0, and its ROI is above 0
in at least 2 of the 3 seasons. Else it does not hold.

**Also (information):**
- The same rule at the snapshot 2 days out (2023-24 and 2024-25 only), graded the same, plus the CLV of that price
  against the near-kickoff no-vig at the same line.
- The NBA's line filter (skip when the line ÷ his last-5 average is in (1.0565, 1.4167]) on the ping set.
- Passing TDs and interceptions, apart.

## Result (2026-10-29, about 22:00 UTC): DOES NOT HOLD
- **Matching:** 852 of 855 games, and 37,888 of 39,454 near-kickoff FanDuel/DraftKings props graded (34,529 headline).
- **The book's no-vig over against the actual over rate:**
  - 2023 49.5% against 49.6%; 2024 49.4% against 48.1%; 2025 49.3% against 46.5%.
  - The overs are shaded in two of three seasons.

| headline markets | 2023 | 2024 | 2025 | pooled |
|---|---|---|---|---|
| UNDER20 (any price) | 1,402, −3.2% | 1,780, −1.1% | 1,414, +1.8% | 4,596, 54.1% hits, −0.8% |
| 20%+ set | 1,242, −2.9% | 1,556, −1.2% | 1,269, +1.5% | 4,067, 52.9%, −0.9% |
| **ping set** | 458, 49.1%, −7.2% | 605, 52.1%, −1.9% | 501, 55.1%, +3.0% | **1,564, 52.2%, −1.9% [−6.0, +2.0]** |

**The test:** the pooled interval's low end is below 0, and the ping set is positive in 1 of 3 seasons, so it does not
hold. The NBA's ping set made +16.8% | +15.0%.

**Information (post-hoc splits, 8 markets tried):**

| by market | ping set | 20%+ set |
|---|---|---|
| rush + rec yards | 164, +15.3% [+3.8, +26.5] | 412, +8.1% [+0.8, +15.4] |
| rush attempts | 212, +5.4% | 544, +8.2% [+1.5, +14.8] |
| rush yards | 234, +3.3% | 617, +3.5% |
| receptions | 362, −4.8% | 880, −2.3% |
| receiving yards | 355, −11.4% [−19.5, −3.1] | 907, −5.4% |
| passing yards, attempts, completions | 71–85 each, −4% to −10% | 227–241 each, −7% to −13% |

- The rushing markets lean positive and receiving and passing lean negative. That was found after looking, so it is
  a lead to track forward, not a result.
- **The NBA's line filter:** kept −1.2%, dropped −3.5%, so no help.
- **Passing TDs and interceptions:** 20%+ set 340, −4.8%.
- **Two days out (2023-24 and 2024-25):**
  - 20%+ set 1,202, −5.7%; ping set 439, −7.0%.
  - The CLV of those prices against the near-kickoff no-vig at the same line is −5.4% | −5.7%: early NFL unders
    get worse prices.
- **Why it may differ:**
  - The NFL projection is a plain average with no role or injury context (the NBA's V3 knew who was out).
  - There are fewer games for a rate.
  - The volume (targets, carries) swings with game script.
