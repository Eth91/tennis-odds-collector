# Pickz projected minutes by role: pre-registration

Written and committed on 2026-11-19 (about 09:40 UTC). No 2026-27 accuracy of the model below had been computed at
that point. This decides only what the Lineups tab's Projected minutes list shows. ROLE_OPEN, `nba_role.py` and every
engine rule stay as they are.

## The user's ask
- "Being a starter typically means u get more minutes in most cases"
  - Their exceptions: a regular starter off the bench can still out-play the spot starter, a spot starter can play
    11, and a big-minutes bench player plays big minutes.
  - "stuff like that needs to be wired in and tested".
- "does the engine readjust minutes projections once the starters are confirmed?"
  - V3 doesn't: it has no starter input.
  - The page reruns every 2 minutes, but a player's minutes don't change when he's named a starter.

## Already seen
- **The first test** (`NBA_PAGE_MINUTES_PREREG.md`, 2026-27, 10-26 to 11-18):
  - V3 4.76 overall and 4.99 for posted starters, with a mean error of −1.05 for starters.
  - A starter's own last-5 average did 4.81.
- **After it, on the same games:** V3's mean error by team and by how many players were available.
  - 11 available: about 0.
  - 13 available: −0.95, starters −2.25.
  - 14 available: −1.47, starters −2.78.
  - Memphis had 16 available on 11-19.
- **2025-26 (training only):** this model's whole design and its fit. See `audit/page_minutes_role/`.
  - 1,230 games and 23,948 player-games by players who played. V3 5.12 (−1.66); last-5 average 5.11.
  - The model below: 4.77 (−0.09). Starters 4.43 against V3's 5.16; bench 5.06 against 5.08.
- **2025-26 has no injury reports,** so who was available is approximated.
  - **Counted available:** everyone who played, plus a player from the team's last 3 games who sat tonight but
    played the team's next game.
  - **Counted out:** a player from the last 3 games who sat both.
  - 9.4% of those counted didn't play, against 11.3% in 2026-27.

## Model RM (fitted on 2025-26 only)
**Who's in:** the same players as V3, by the same rules: the last 3 games' players, players back from injury and
tonight's five. Out, Doubtful, NBA.com's inactive list and traded players are removed.

**Tonight's role:** starter if he's in the team's five, else bench.
- The five is NBA.com's posted five once it's up (Expected or Confirmed), else Pickz's projected five.
- So a confirmed lineup changes the minutes on the next rebuild.

**Steps:**
1. **L5:** his average over his last 5 games played. **s:** the share of those 5 he started.
2. **The role prior:**
   - A starter tonight: L5 + 9 × (1 − s).
   - Bench tonight: L5 − 6 × s.
3. **His role base:** (the sum of his last up-to-5 games in tonight's role + 4 × the role prior) / (their number + 4),
   capped at 40.
4. **His chance of playing, P:**
   - 1 for a starter.
   - For the bench, the 2025-26 rate for his bucket below.
     - **Bucket:** the share of the team's last 10 games he played (0-0.2, 0.3-0.5, 0.6-0.8, 0.9-1), and his L5
       (under 10, 10-20, 20 and up).
     - **No rate for his bucket:** P = 0.9.
5. **Fill to 240:** c = 240 / Σ P × base over everyone in. Minutes = base × c, capped at 40.
   - These are his minutes if he plays. A DNP voids a prop.

**The P table (2025-26):**

| Share of last 10 played | L5 under 10 | L5 10-20 | L5 20+ |
|---|---|---|---|
| 0-0.2 | 0.842 | 0.861 | 0.854 |
| 0.3-0.5 | 0.738 | 0.833 | 0.757 |
| 0.6-0.8 | 0.753 | 0.857 | 0.743 |
| 0.9-1 | 0.806 | 0.931 | 0.861 |

**How it was fitted:** a grid search on 2025-26 over:
- 6, 9, 12 or 15 minutes for a first start.
- 3, 6, 9 or 12 for a starter moved to the bench.
- A pull of 2, 4, 6 or 8 games.

**Fill methods tried on 2025-26 and dropped** (MAE):

| Method | MAE |
|---|---|
| Everyone scaled to 240 | 4.91 |
| No fill | 4.83 |
| Starters fixed, bench fills the rest (with or without P) | 4.94 / 5.05 |
| Absent regulars' minutes shared by position, as V3 does | 4.78 |

**A known risk:** P was fitted on the approximated pool.
- That pool counts a one-game rest or injury as available.
- The live pool removes reported Outs instead.
- So P may run low for regulars and the fill high.

## Data (2026-27, point in time; as the first test)
- **Games:** the regular-season games of 2026-10-26 to 2026-11-18.
- **Before each date:** box scores from earlier dates only (nba_matchup), with each game's starters.
- **Who is out:** the date's latest official report (Out or Doubtful) and NBA.com's inactive list from the date's
  latest lineups snapshot.
- **The five:** that snapshot's posted five. Every one of the 358 team-games has one.
- **Timing:** the latest report or snapshot of a date can come after an early game's tip. That's the same for both
  models.

## Measures
- **Population:** the available players who played (minutes > 0).
- **Error:** the minutes MAE and mean error, overall, for the posted five and for the bench.

## Decision
- **RM replaces V3 in the Projected minutes list when all three hold:**
  - RM's overall MAE is lower.
  - The 95% interval of MAE(RM) − MAE(V3) is below 0 (2,000 resamples of whole games, seed 5).
  - RM's MAE for the posted five isn't higher.
- **Otherwise V3 stays.**
- **The forward check:** games from 2026-11-19 on are scored the same way once about 100 have been played. It's
  reported, not part of this decision.

## Not changed after this point
The model, its constants, the data, the population and the decision rule above stay as written. Fixes to bugs are
allowed. Each one is listed in the result with its effect.
