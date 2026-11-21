# Pickz projected minutes: pre-registration

Written and committed on 2026-11-19 (about 09:00 UTC), before any accuracy below was computed. This decides only what
the Lineups tab's Projected minutes list shows. ROLE_OPEN, nba_role.py and every engine rule stay as they are.

## The user's ask
- A list per team on the Lineups tab: projected minutes for every available player in that game, from our minutes
  engine.
- "can our minutes projection engine be trained on coach tendencies and 2026-27 season data so our projections are
  more accurate?"

## Already seen
- **How it was spotted:** the list was built and run once on the VM against the 2026-11-19 slate. That run is the whole
  observation.
- **What it showed:** with ROLE1 v3 as it is, most regulars came out 1-5 minutes under their last-5 average, including
  on teams with nobody out.
- **The likely cause:** 13-15 players count as available, and v3 scales their minutes to 240. A deep-bench player's
  last 5 averages only the games he played, so that sum runs over 240 and everyone gets squeezed.
- **Why the engine's backtests never showed it:** they used who actually played, so the sum fit.
- No accuracy of any model below has been computed on any data.

## Models
Each gives a player's minutes if he plays. A DNP voids a prop.

| | Model |
|---|---|
| V3 | `nba_role.project(..., mode="v3")` as the page calls it (`nba_research.projected_minutes`). |
| V3-P | the coach's rotation: V3's minutes × c, capped at 40. |
| L5 | his average over his last 5 games played (v3's base). Reference only. |

**V3's inputs:**
- **Who can play:** the last 3 games' players, players back from injury and tonight's starters.
- **Removed:** Out, Doubtful, NBA.com's inactive list, and anyone the roster puts on another team.
- **Shared out:** the minutes of a regular in absence games 1-3.

**V3-P's c:** c = 240 / Σ P·V3 over the team's available players.
- **P** is the share of the team's last 10 games (all of them if fewer) in which he played.
- **P = 1** for the night's posted starters and for a player back from injury.

## Data (2026-27, point in time)
- **Games:** the regular-season games of 2026-10-26 to 2026-11-18. The lineup snapshots start 10-26.
- **Before each date:** box scores from earlier dates only (nba_matchup).
- **Who is out:** the date's latest official report (Out or Doubtful, as the page reads it) and NBA.com's inactive
  list from the date's latest lineups snapshot.
- **Starters:** that snapshot's five.
- **Timing:** the latest report or snapshot of a date can come after an early game's tip. That is the same for every
  model.
- **Positions:** the VM's `nba_gamelogs.sqlite` positions table, as live.

## Measures
- **Population:** the available players who played (minutes > 0).
- **Error:** the mean absolute error of the minutes and the mean error.
  - Reported overall, for posted starters and for the bench.
- **The DNP rate** among the available is reported, not scored.

## Decision
- **The list shows V3-P instead of V3** when V3-P's overall MAE is lower, the 95% interval of MAE(V3-P) − MAE(V3) is
  below 0 (resampling whole games), and V3-P's MAE for starters is not higher.
- **Otherwise V3 stays.**
- **If L5 beats both:** it is reported, and the switch waits for the user.

**Coach tendencies:**
- V3 already reads this season only for minutes: the last-5 base, the shared-out minutes and this season's games
  without the absent players.
- P is the coach's rotation: who he actually plays.
- How a coach spreads an injured starter's minutes, per team, needs more absence cases than 3 weeks give. It is not
  tested here.

## Not changed after this point
The models, data, population and decision rule above stay as written. Fixes to bugs are allowed. Each one is listed in
the result with its effect.

## Result (2026-11-19; `audit/page_minutes/`)
**Data:**
- 179 games, with 3,890 player-games by available players who played.
- 11.3% of the available didn't play (498 of 4,388).
- No bug fixes were made after the pre-registration.

Each cell is the minutes MAE, with the mean error in brackets.

| | All (3,890) | Posted starters (1,790) | Bench (2,100) |
|---|---|---|---|
| V3 | **4.76** (−0.70) | 4.99 (−1.05) | **4.57** (−0.40) |
| V3-P | 4.82 (+0.78) | 4.92 (+0.87) | 4.74 (+0.70) |
| L5 | 4.85 (−0.45) | **4.81** (−0.96) | 4.88 (−0.01) |

- **MAE(V3-P) − MAE(V3):** +0.058, with a 95% interval of −0.010 to +0.132.
- **Decision: V3 stays.** V3-P isn't more accurate. It overshoots: V3 runs 0.7 minutes low on average, and V3-P runs
  0.8 high.

**Read:**
- **The squeeze is smaller than the 11-19 slate suggested.** V3 runs 0.7 minutes low overall and 1.0 low for
  starters.
- **V3 is the most accurate of the three overall and for the bench.**
- **For starters, his own last 5 does slightly better** (4.81 against 4.99).
- **What could help later,** as a new pre-registration with fresh games:
  - Starters' minutes from their own last 5.
  - A scale between V3 and V3-P.
