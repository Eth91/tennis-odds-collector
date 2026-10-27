# PRE-REGISTRATION: the early-season window, and vacated shots

Written 2026-10-27 (about 10:05 UTC), before either test was computed. Research only: nothing is bet.

**User:** "yes, backtest games 2-5 with last season as the prior. I feel like this system works." And: "he likely sees
increased volume or maintains volume with Duren out, as Paul Reed doesn't take as many shots, so add that to the
criteria as well."

## Common setup
- **Data:** 2023-24 and 2024-25 (last seasons 2022-23 and 2023-24, from `logs_full`), at the archive's tip lines
  (FanDuel/DraftKings main, best over price).
- **No hindsight:** features use games before the date only.
- **Pass, for each rule:** ROI > 0 in **both** seasons and above its baseline in both.
- **Forward:** a passing rule enters the side-by-side at the opener (registered then). Pings come only after a
  forward record.

## Part 1: games 2–5 (the player has 1–4 games this season before tonight)
"Blended" means (this season's total + last season's per-game × 3) ÷ (this season's games + 3). Last season needs
≥ 20 games; without it, this season alone is used.

- **E1:** points over when this season's FGA/g ≥ the points line, with this season's mpg ≥ 20.
- **E2:** the same on **blended** FGA/g and mpg.
- **E3, the volume surge:** points over when this season's FGA/g ≥ 1.2 × last season's FGA/g, this season's
  mpg ≥ 20, and this season's FGA/g ≥ 0.8 × the points line. This is the user's "elevated role the books haven't
  caught up to."
- **E4:** assists over when this season's potential assists/g ≥ 2 × the assists line (tracking, this season
  only).
- **E5:** rebounds over when this season's rebound chances/g ≥ 2 × the rebounds line (the same).
- **Baseline:** all overs in games 2–5 in that market. The same rules in games 6+ are reported beside them, to
  answer whether early is different.

## Part 2: vacated shots (ROLE1's conserved team volume)
- **The spot:** a rotation player X (≥ 17 min, ≥ 3 games this season) out tonight, in absence game **2 or 3**.
  He also missed the previous game, so there is no late-scratch hindsight. Absence game 1 is reported separately,
  with the caveat.
- **The projection:** each active teammate B's projected FGA tonight from ROLE1 v3 (`nba_role.project`):
  minutes redistributed by position, WOWY blended in, and team FGA conserved. X's shots go to the others in
  proportion to minutes × FGA rate, so a low-volume replacement leaves shots for the shooters.
- **V1:** points over when B's projected FGA ≥ the points line and his season mpg ≥ 20.
- **V0, the comparison:** the same spots with B's plain season FGA/g ≥ the line, which ignores the vacated shots.
- **Baseline:** all points overs in the spots at 20+ mpg.
