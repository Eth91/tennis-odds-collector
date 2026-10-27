# PRE-REGISTRATION: the user's volume-to-line ratios

Written 2026-10-27 (about 08:45 UTC), before any ratio was computed on any line. Research only: nothing is bet
automatically.

**User:** "if a player's potential assists are double or more of their assist line I like that bet, and if their
FGA are equal to their point line or more I like the bet ... line is 10.5 points and they average 10 FGA a game,
I like that ... rebound chances, if they have say 2 - 2.5x the rebound chances of their line I like that bet too."
Also: players who "started the season with elevated role or volume that the books haven't caught up to yet."

## The rules (the user's thresholds, nothing fitted)
- **FGA:** over in points when his season-to-date FGA per game ≥ the points line.
- **PA:** over in assists when his season-to-date potential assists per game ≥ 2 × the assists line.
- **RC:** over in rebounds when his season-to-date rebound chances per game ≥ 2 × the rebounds line. RC 2.5×
  is also reported.

"Season to date" means his games this season before the date (minutes > 0), with ≥ 3 games. Potential assists and
rebound chances come from stats.nba.com tracking (`leaguedashptstats`, per date). For 2023-24 and 2024-25 these are
fetched into a research copy (`.projdata/tracking_hist.sqlite`), never the VM's store.

## Backtest: 2023-24 and 2024-25, the archive's tip lines
- **The line and price:** the main line is the FanDuel/DraftKings rung nearest even money; the price is the best
  FanDuel/DraftKings over.
- **No hindsight:** season-to-date volume is known before the game.
- **Weakness:** the archive has only the tip − 30 snapshot, the sharpest price of the day, not the opener the
  user bets.
- **Reported, per rule and season:**
  - n, hit rate, and ROI at the price;
  - the market's all-overs ROI, as the baseline;
  - by ratio band: FGA 1.0–1.1 / 1.1–1.25 / 1.25+; PA and RC 2.0–2.25 / 2.25–2.5 / 2.5+;
  - early season (his games ≤ 10) against later.
- **A rule passes** if its ROI is > 0 in **both** seasons and above the market's all-overs ROI in both.

## Forward
- **All three rules enter the side-by-side** at the opener, pass or fail, because openers are the real target.
  They are registered with fingerprints, using this season's volume (box scores for FGA; nba_tracking for PA
  and RC).
- **Phone pings** (SHADOW) go only for rules that pass the backtest.
