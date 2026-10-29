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
