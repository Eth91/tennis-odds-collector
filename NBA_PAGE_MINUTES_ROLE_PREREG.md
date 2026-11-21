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

## Result (2026-11-19; `audit/page_minutes_role/`, `result.20261119.json`)
**Data:**
- 179 games, with 3,890 player-games by available players who played. 11.3% of the available didn't play (498 of 4,388).
- **The one bug fix:** a base under 0 counts as 0.
  - Without it, a bench player with a tiny last 5 who had started could come out below 0.
  - In 2025-26, 189 player-games sit at 0, nearly all players with no games yet (V3 gives them 0 too).
  - The fit stays 4.769. In this test 1 player-game sits at 0.

Each cell is the minutes MAE, with the mean error in brackets.

| | All (3,890) | Posted five (1,790) | Bench (2,100) |
|---|---|---|---|
| V3 | 4.76 (−0.70) | 4.99 (−1.05) | **4.57** (−0.40) |
| RM | **4.69** (+0.58) | **4.76** (+1.30) | 4.64 (−0.04) |
| L5 | 4.85 (−0.45) | 4.81 (−0.96) | 4.88 (−0.01) |

- **MAE(RM) − MAE(V3):** −0.067, with a 95% interval of −0.155 to +0.025.
- **Decision: V3 stays.** The interval reaches above 0.

**Read:**
- **RM is better for the five** (4.76 against 4.99) and slightly worse for the bench.
- **The known risk happened.** RM runs high, +1.3 for the five.
- **The cause:** the 2025-26 chance-of-playing table came from the approximated pool.
- **This season's real pool** (reports and inactive lists, 10-26 to 11-18):
  - A bench player under 10 minutes plays 47-77% of the time (2025-26's table: 74-84%).
  - One at 20+ plays 98-100% (2025-26's: 74-86%).
- **The user's examples:**

  | Game | Player | Role | Actual | V3 | RM |
  |---|---|---|---|---|---|
  | 11-18 UTA | Hayes | bench | 25.4 | 23.5 | 18.3 |
  | 11-18 UTA | Bamba | start | 22.6 | 17.9 | 29.4 |
  | 11-17 POR | Kent | start | 27.2 | 13.2 | 22.1 |
  | 11-17 POR | Holiday | bench | 30.9 | 27.5 | 29.2 |

  - For Kent and Holiday, RM is closer.
  - For Hayes and Bamba, RM is further off: the regular starter off the bench still played his minutes.

## RM2: pre-registration (fresh games only)
Written and committed on 2026-11-19, after RM's result above and before any game of RM2's test was played.

**Model RM2:** RM with one change. The bench's chance of playing comes from 2026-27's real pool.
- The pool is 10-26 to 11-18, built as the page builds it (`fit_2026_p.py`, `p_2026.json`).
- A bucket with under 50 players takes its L5 column's rate.
- Everything else is RM's, unchanged: 9, 6, 4 and the 0-to-40 range.

**RM2's table:**

| Share of last 10 played | L5 under 10 | L5 10-20 | L5 20+ |
|---|---|---|---|
| 0-0.2 | 0.473 | 0.909 | 0.990 |
| 0.3-0.5 | 0.552 | 0.770 | 0.990 |
| 0.6-0.8 | 0.617 | 0.878 | 0.978 |
| 0.9-1 | 0.773 | 0.956 | 0.992 |

**Already seen:**
- RM2 on the same 179 games is in-sample, since its table was fitted on them.
- 4.67 overall (+0.21); 4.76 for the five (+0.82); 4.59 for the bench. Against V3: −0.095.
- It is information only, not a test.

**The test:**
- **Games:** the first 150 regular-season games from 2026-11-19 on (`nba_page_minutes_role_fwd.py`; the data from
  `extract_vm_fwd.py` on the VM, read-only).
- **Method:** point in time, with the same population and measures as above.

**Decision:**
- **RM2 replaces V3 in the Projected minutes list when all three hold:**
  - Its overall MAE is lower.
  - The 95% interval of MAE(RM2) − MAE(V3) is below 0 (2,000 resamples of whole games, seed 5).
  - Its MAE for the posted five isn't higher.
- **Otherwise V3 stays.**
- **RM as registered** is scored on the same games and reported, not decided on.
- **Until then the page shows V3.**

## Not changed after this point (RM2)
RM2, its table, the games, the population and the decision rule above stay as written. Fixes to bugs are allowed. Each
one is listed in the result with its effect.

## The user's choice (2026-11-20): the most accurate model for each team's top 8
Written and committed before any of these numbers were computed.

**The user:** "just use the most accurate starter model like what model predicts the top 7-8 minutes getters cause
you cant even bet on more than like 7-8 guys on nba teams".
- This replaces the decision rules above for what the page shows now.
- RM2's forward test still runs and is reported.

**Who counts:**
- In each team-game, the 8 available players with the most season-average minutes. That's this season's games for
  the team before the date; ties go by player id.
- Only those who played are scored. The top 7 is reported too.
- No model uses the season average, so the choice of players doesn't favor one.

**Candidates:** V3, RM, RM2 and L5.
- RM2's table was fitted on 10-26 to 11-18, so it is in-sample there.
- **RM2h:** RM2 with its table fitted on 10-26 to 11-06 only, the same way (`fit_2026_p.py`, a bucket under 50 takes
  its L5 column's rate).

**Decision:**
- On 11-07 to 11-18 every candidate is out of sample, with RM2h standing in for RM2.
- **The page shows the candidate with the lowest top-8 MAE there.**
- **If that's RM2h:** the page uses RM2, its table from all of 10-26 to 11-18, as registered.
- **Reported, not decided on:**
  - The full window (10-26 to 11-18; RM2 in-sample).
  - The top 7.
  - Each candidate minus V3, with a 95% interval (2,000 resamples of whole games, seed 5).

### Result (2026-11-20; `nba_page_minutes_top8.py`, `result_top8.20261120.json`)
RM2h's table (10-26 to 11-06) is in `p_2026_h1.json`.

Each cell is the minutes MAE, with the mean error in brackets.

| Top 8 | 11-07 to 11-18 (90 games, 1,424; decides) | 10-26 to 11-18 (2,833; RM2 in-sample) |
|---|---|---|
| V3 | 4.821 (−0.38) | 4.704 (−0.36) |
| RM | 4.781 (+1.03) | 4.626 (+1.08) |
| RM2 | 4.753 (+0.56) | 4.590 (+0.65) |
| RM2h | **4.746** (+0.46) | 4.586 (+0.56) |
| L5 | 4.865 (−0.19) | 4.737 (−0.22) |

- **The top 7 ranks them the same way:** RM2h 4.763, RM2 4.769, RM 4.788, L5 4.803 and V3 4.814 on 11-07 to 11-18.
- **Minus V3 on 11-07 to 11-18:**
  - RM2h: −0.075 (−0.212 to +0.062).
  - RM: −0.039 (−0.200 to +0.124).
  - L5: +0.044.
- **Minus V3 on the full window:**
  - RM2: −0.114 (−0.209 to −0.010), in-sample.
  - RM: −0.078 (−0.186 to +0.040).
- **Decision: the page shows RM2.** It is the lowest on 11-07 to 11-18, by the user's rule.
  - Its edge over V3 is about 0.08 minutes a player, and the interval reaches above 0.
  - RM2 runs about 0.5 minutes high for the top 8.
- **RM2's forward test** (the first 150 games from 11-19 on) is still scored and reported.
