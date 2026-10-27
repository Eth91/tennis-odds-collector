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

# AMENDMENT 1: the solver, the threshold that would have paid (written 2026-10-27, about 08:45 UTC, before it ran)
**User:** "use a solver type scenario to test the ratio needed to be profitable."

- **The sweep, for each rule:**
  - FGA ÷ points line from 0.80 to 2.00, step 0.05;
  - potential assists ÷ assists line from 1.0 to 4.0, step 0.1;
  - rebound chances ÷ rebounds line from 1.0 to 4.0, step 0.1.
- **At each threshold k:** the over whenever the ratio is ≥ k. Report n and ROI in each season.
- **The pick:** on one season (2023-24), the k with the highest ROI among thresholds with ≥ 150 bets.
- **The check:** the picked k's ROI on the other season (2024-25), which played no part in the pick. The same is
  done in reverse (pick on 2024-25, check on 2023-24).
- **What "profitable" requires:**
  - the picked k is positive on the season it did not see, in both directions;
  - **and** the neighbouring thresholds (k ± one step) are positive in both seasons, so it is a region, not a
    spike.
- **Honest limits:**
  - A sweep tries many thresholds, so the best one on a season is always optimistic. The other season is the
    real number.
  - These are tip lines; a threshold that works there would very likely work at softer openers too.

# AMENDMENT 2: minutes first (written 2026-10-27, about 08:50 UTC, before it ran)
**User:** "I usually do them correlated with minutes, so they have to have a decent amount of minutes like 20+, and
then have 1-1.2x+ as many FGA as points line."

- **FGA20:** his season-to-date minutes per game ≥ 20 **and** FGA per game ≥ k × the points line.
  - Primary: k = 1.0. Also reported: k = 1.1 and k = 1.2.
- **Baseline:** every points over among players at 20+ minutes.
- **Same pass bar:** ROI > 0 in both seasons and above that baseline in both.
- **The solver curve** (k from 0.80 to 1.50) restricted to 20+ minutes, using amendment 1's pick-and-check rule.
- **The minutes condition is applied to PA and RC too** (20+ minutes, at their 2× rule and in the solver), and
  reported beside the unfiltered versions.

---

## Results (2026-10-27, about 09:00 UTC): no rule passes as registered
Tracking history: 51,277 player-games over 317 dates. The guard rejected 5 dates, which are left out.

**The rules as stated, tip lines** (n, hit rate, ROI; each market's all-overs baseline in brackets):

| | 2023-24 | 2024-25 |
|---|---|---|
| FGA ≥ points line | 1,102, 50.5%, −3.6% [−7.8%] | 1,169, 50.4%, −4.5% [−5.9%] |
| FGA, 20+ min, k 1.0 / 1.1 / 1.2 | −2.3% (962) / +1.3% (469) / +2.6% (199) | −3.3% (997) / −4.9% (410) / −7.3% (183) |
| PA ≥ 2× assists line | 1,985, 52.1%, −3.0% [−5.5%] | 2,701, 53.1%, −3.5% [−5.2%] |
| PA, 20+ min | 1,874, −2.1% | 2,617, −3.2% |
| RC ≥ 2× rebounds line | 3,672, 51.8%, −4.0% [−9.6%] | 1,991, 55.3%, **+0.3%** [−8.2%] |
| RC ≥ 2.5× | 572, −0.9% | 216, −5.8% |
| RC, 20+ min, 2× | 3,274, −4.6% | 1,743, **+0.7%** |

Every rule picks overs that hit 2–8 points more often than the market's overs, and beats blind overs by 1–8 ROI
points. None is positive in both seasons at tip lines.

**The solver (amendment 1):** not profitable as registered for any rule.
- **FGA:** 2023-24's best (1.2×, +3.9%) loses 12.3% in 2024-25.
- **RC:** the picks fail in reverse; 2.8× gives −8.3% on 54, and 2.2× gives −1.4%.
- **PA, the closest:**
  - ROI rises steadily with the ratio, from −5% at 1× to +9–21% at 3×.
  - 2.7×: +1.9% (124) and +0.4% (241).
  - 2.8×: +8.0% (91) and +4.3% (175).
  - 2.9×: +10.8% (68) and +4.2% (108).
  - 3.0×: +20.8% (45) and +9.0% (60).
  - Picked on 2024-25 (2.8×), it holds on 2023-24 with positive neighbours. Picked on 2023-24 (where 2.8× has
    under 150 bets, so the pick was 2.2×), it does not hold (−2.4%). The registered both-ways test fails.
  - PA ≥ 2.8× is the one region positive in both seasons, on 266 bets in all. Not significant.

**Definitions across seasons:**
- Potential assists per assist are stable: 1.72 (2023-24), 1.82 (2024-25), 1.85 (2026-27).
- Rebound chances per rebound drift: 1.75, 1.68, then 1.88 in 2026-27. "2× the rebounds line" this season is
  about 1.8× in 2024-25's terms.

**Forward, as registered:** RATIO_FGA, RATIO_PA (2×) and RATIO_RC (2×) enter the side-by-side at the opener from
13:00 UTC. No rule passed, so there are **no pings** for them.

# AMENDMENT 3: RATIO_PA28, forward with pings (written 2026-10-27, about 09:05 UTC)
**User:** "yes, add it shadowing. I want to see how it forward tests with the speed factor involved."

- **The rule:** at a book's opener (first two-sided main, up to tip − 5), the assists over when his potential
  assists per game this season are ≥ **2.8 ×** the assists line, with ≥ 3 games.
- **Pings:** to the phone, labeled SHADOW, the moment it fires (`nba_role_open.py`, every minute).
- **Honest status:** 2.8× was chosen by the solver after both backtest seasons were seen (+8.0% on 91, +4.3% on
  175). So the backtest is in sample, and only the forward record counts. It is judged by the side-by-side's
  bars (side-by-side amendment 4).

# AMENDMENT 4: matchup conditions (written 2026-10-27, about 09:10 UTC, before they were computed)
**User:** "for rebounds and points, add a matchup rule so it has to be a good rebounding matchup vs their position,
and for points, where they score from and where their opponents give up points needs to be a good matchup, along
with defense vs their position."

**Measures** (season to date, strictly before the game's date; the opponent needs ≥ 10 team games):
- **Defense vs position (DvP):** points, or rebounds, scored per game against the opponent by players in the
  player's position group (G / F / C, from `positions`), ÷ the league's per-team-game average for that group over
  the same dates. Above 1 means the opponent gives that position more than average.
- **ZONE:** `nba_zones`' all-zone score: the player's share of his points from each zone × (the opponent's points
  allowed there ÷ league − 1). Above 0 means the opponent is soft where he scores.
- **"Good":** above the 2023-24 median of the measure; the top tercile is also reported.

**Rules:**
- **PTS_MATCH:** FGA ≥ 1.0 × the points line, 20+ minutes, ZONE good **and** points-DvP good. Points over.
- **REB_MATCH:** rebound chances ≥ 2 × the rebounds line **and** rebounds-DvP good. Rebounds over.
  Also reported with 20+ minutes.

**Backtest:** 2023-24 and 2024-25, tip lines, as above.
- **Pass:** ROI > 0 in both seasons **and** above the same ratio rule without the matchup in both seasons.
- Also reported: each matchup condition alone on top of the ratio rule, and the top-tercile versions.

**Forward:** both rules enter the side-by-side at the opener, registered with fingerprints. They ping only if they
pass. Because of the 10-game minimum, they cannot fire until opponents have played 10 games (about mid-November).

**Amendment 4: run (2026-10-27, about 09:20 UTC). Neither rule passes.**
- **Cuts (2023-24 median / top tercile):** ZONE −0.004 / 0.026; points-DvP 1.004 / 1.032; rebounds-DvP
  1.006 / 1.032.

| n, hit rate, ROI | 2023-24 | 2024-25 |
|---|---|---|
| PTS ratio (FGA 1×, 20+ min) | 962, 51.1%, −2.3% | 997, 50.9%, −3.3% |
| + ZONE good | 397, 49.9%, −4.8% | 410, 50.2%, −4.5% |
| + points-DvP good | 414, 53.9%, **+3.0%** | 355, 51.5%, −1.8% |
| PTS_MATCH (both good) | 260, 53.1%, +1.2% | 218, 50.9%, −3.2% |
| both top tercile | 119, 52.9%, +1.2% | 93, 51.6%, −1.7% |
| REB ratio (RC 2×) | 3,672, 51.8%, −4.0% | 1,991, 55.3%, +0.3% |
| REB_MATCH (+ rebounds-DvP good) | 1,455, 51.9%, −4.2% | 711, 54.1%, −2.1% |
| + 20+ min | 1,299, 51.6%, −4.7% | 604, 54.0%, −2.8% |
| rebounds-DvP top tercile | 955, 50.4%, −7.2% | 473, 54.5%, −1.0% |

**Reading:**
- **Points-DvP** is the one condition that improves the points rule in both seasons (+5.3 and +1.5 ROI points),
  but it is not positive in 2024-25.
- **The zone condition makes it worse.** The books price where a player scores against the opponent's zones,
  as the zone study found.
- **Rebounds-DvP adds nothing.**

**Forward (changed from above, before any forward run).** Neither rule passed, and neither can fire before
opponents have 10 games (about mid-November). So the forward versions are not built now; they would be
registered then if wanted. Nothing pings.

# AMENDMENT 5: PTS_DVP, forward (written 2026-10-27, about 09:25 UTC)
**User:** "yes, register it for mid-November."

- **The rule:** at a book's opener (first two-sided main, up to tip − 5), the points over when all hold:
  - his FGA per game this season ≥ 1.0 × the points line;
  - his minutes per game this season ≥ 20, with ≥ 3 games;
  - the opponent's points-DvP for his position group is > **1.0036** (amendment 4's 2023-24 median, fixed);
  - the opponent has ≥ 10 games this season.
- **DvP** is computed point-in-time from this season's box scores (nba_matchup) and position groups
  (`nba_gamelogs.positions`).
- **Registered now** (side-by-side amendment 5), so its record starts today. Because of the 10-game minimum it
  cannot fire until about mid-November.
- **No pings.** Amendment 4 failed in 2024-25 (+3.0%, then −1.8%), so it is forward-only.
