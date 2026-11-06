# NBA WOWY per-36 × minutes: pre-registration

Written and committed on 2026-11-06 (about 21:10 UTC), before any projection below was computed and while the
2023-24 lineups were still being built. Research only: nothing changes live. `nba_flags.LIVE_TIERS` stays empty.

## The theory (the user's words)
"We take WOWY per 36 splits - convert to the per36 to either our projected number of minutes based on our highly
complex formula we create or their average minutes without that player in the game or the averag of their last 3-5
games"

A projection is a per-36 rate × projected minutes / 36. The rate is the WOWY tab's: the player's per-36 with the
teammate off the court.

## Already seen (so not evidence for anything below)
- **The 2025-26 carry-over fit** (`NBA_WOWY_SELECT_PREREG.md`): over his overall per-36, the game the teammate misses
  carries about 1/5 of the off-court gap for points (+0.17), rebounds +0.15 and assists +0.32.
- **The 2024-25 selection test at tip lines** (same file): all 7 criteria FAIL.
  - "Star out" and "next man up" were real (+1.1 to 1.2 points) but already priced.
  - Those 2024-25 lines have been used before. None of the projections below has been computed on them.
- **The minutes models** (`NBA_MINUTES_PREREG.md`):
  - V3, the live role model, misses a new starter's minutes by 6.2-6.3.
  - Last-5 misses them by 7.7-8.3 and runs 6-7 minutes low.
- **2023-24:** the lineups have not been built or looked at.

## Data
- **Lineups:** the 2023-24, 2024-25 and 2025-26 regular seasons, rebuilt from cdn.nba.com play-by-play by
  `nba_onoff.parse`.
  - 2023-24 and 2024-25 starters and names come from the cdn.nba.com liveData box scores.
  - 2025-26 comes from the 2026-11-03 VM backup of `nba_matchup`.
- **The engine's minutes:** `nba_role.project(..., mode="v3")`, the role model ROLE_OPEN runs.
  - It reads `logs_full` from `nba_gamelogs.sqlite` (priors from the season before).
  - The code is used as it is, read-only.
- **Lines:** `basketball_nba_odds_hist.sqlite`, snap_kind `tip` (about 30 minutes before tip), 2023-24 and 2024-25
  regular seasons.
  - The main line is the one with both sides posted and the closest two prices.
  - FanDuel's main line is used first, then DraftKings'.
  - Players are matched by name within the game, as in the selection test.

## Events (point in time: only games before g)
These are the same as the selection test:
- **Teammate Y** is a regular (10+ games and 20+ minutes a game for this team before g).
  - He doesn't play in g.
  - He played in at least one of the team's 3 games before g. These are absence games 1-3.
- **Player X** has 300+ prior minutes for the team, with 60+ of them with Y on the court and 60+ with Y off it.
- **X played in g.** A DNP is void.
- **Two or more regulars out:** Y is the one with the most minutes a game before g. That makes one projection per
  player, game and market.
- Who is out comes from who played, as in the engine's own backtests. That stands in for the injury report and is
  the same for every projection.

## The projections
**Rates (per 36, X's prior minutes for this team this season):**

| | Rate | Role |
|---|---|---|
| W | per-36 in lineups with Y off the court (the WOWY tab) | the theory |
| O | overall per-36 | control: the same minutes with no WOWY |
| S | O + k·(W − O), with k = 0.17 for points, 0.15 for rebounds and 0.32 for assists | control: WOWY shrunk to what carried in 2025-26 |

**Minutes:**

| | Minutes | Needs |
|---|---|---|
| E | the engine's role model, V3 | X on the engine's active roster: played in one of the team's last 3 games, and plays tonight |
| WO | his average minutes in this season's earlier games for this team that Y missed | 2+ such games |
| L3 | average of his last 3 games for this team | 3 games |
| L5 | average of his last 5 games for this team | 5 games |

For the engine, active is the last-3 roster who play tonight. Absent is the last-3 rotation players who don't. Those
are the engine's own `tip_props` conventions.

There are 3 rates × 4 minutes = 12 projections, in points, rebounds and assists. Each is computed only where its
minutes source exists.

## Measures
**A, accuracy (all three seasons).** The events are those where all four minutes sources exist. In 2023-24 and
2024-25 the event must also have a tip line in that market.
- Per projection and market: mean absolute error against what he did, and the mean error.
- **The yardstick:** the tip line's own error, 2023-24 and 2024-25.
- **Minutes:** each minutes source's error against his minutes.
- **Does WOWY help:** MAE(W) − MAE(O) at the same minutes, with a 95% interval from resampling whole games.
  - "WOWY helps" for a minutes source and market means W's MAE is below O's in all three seasons and the pooled
    interval is below 0.
  - The same test is run for S against O.

**B, the lines.** 2023-24 is discovery; 2024-25 is confirmation.
- **The bet:** over when projection − line ≥ T, under when line − projection ≥ T.
  - Points: T = 1, 2 or 3.
  - Rebounds and assists: T = 0.5, 1 or 1.5.
- **Staking:** a flat unit at the posted tip price. A push is refunded and a DNP is void.
- **Combos:** 3 rates × 4 minutes × 3 markets × 3 thresholds × 2 sides = 216.
- **Discovery (2023-24):** of the combos with 100+ bets and ROI above 0, the top 3 by ROI carry forward. If none
  qualifies, nothing carries and every combo fails.
- **Confirmation (2024-25), the carried combos only:**
  - **PASS:** the ROI's 95% interval (resampling whole games) is above 0.
  - **PROMISING:** ROI above +3%, but the interval includes 0.
  - **FAIL:** anything else.
- **Baseline:** every over and every under in the event population at tip.
- **Every W combo** is also reported for both seasons, so the theory is shown in full. Those rows carry no verdict.

With 216 combos, the best of the discovery season will look good by chance. That is why only the confirmation
season judges. Even a PASS only earns a forward shadow on 2026-27 with nothing bet, under its own pre-registration.

## Not changed after this point
The events, rates, k values, minutes sources, thresholds, line rule and pass rules above stay as written. Fixes to
bugs are allowed: name matching, parsing, or a wrong join. Each one is listed in the result with its effect.
