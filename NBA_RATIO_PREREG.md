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
