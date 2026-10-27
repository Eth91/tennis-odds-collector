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

---

## Results (2026-10-27, about 10:15 UTC; `nba_early.py`)
**Part 1, games 2–5** (n, hit rate, ROI; 2023-24 | 2024-25):

| rule | games 2–5 | baseline 2–5 | the same rule in games 6+ |
|---|---|---|---|
| E1 FGA ≥ line, 20+ min | 99, 50.5%, −3.4% \| 94, 56.4%, +7.3% | −6.8% \| −2.4% | −2.1% \| −4.1% |
| E2 blended | 87, −2.8% \| 71, −14.1% | | −3.1% \| −0.7% |
| **E3 volume surge** | **149, 53.0%, +2.4% \| 146, 54.1%, +3.9%** | −6.8% \| −2.4% | **746, −9.8% \| 1,186, −2.9%** |
| E4 potential assists 2× | 200, −9.0% \| 175, −12.6% | −9.6% \| −13.8% | −3.0% \| −3.0% |
| E5 rebound chances 2× | 411, −4.6% \| 239, −3.1% | −6.5% \| −6.7% | −3.9% \| +0.5% |

- **E3 passes,** and the same rule loses after game 5. That fits the user's thesis: early in the season the line
  lags a player's new volume.
- **The samples are small** (about 150 a season).

**Part 2, vacated shots:**

| | absence games 2–3: 2023-24 \| 2024-25 | absence game 1 (hindsight) |
|---|---|---|
| V1 projected FGA ≥ line | 244, 53.7%, +1.9% \| 233, 51.9%, −1.2% | −9.4% \| −0.0% |
| V0 season FGA ≥ line | 163, 51.5%, −2.0% \| 171, 49.7%, −5.8% | +1.0% \| +3.5% |
| baseline, 20+ min | 49.3%, −4.7% \| 50.2%, −3.5% | −8.3% \| −5.3% |

V1 fails (−1.2% in 2024-25). Counting vacated shots still improves the volume rule by about 4 ROI points in both
seasons over plain season FGA.

# AMENDMENT 1: EARLY_SURGE, forward (written before it ran)
- **The rule:** E3 at a book's opener (first two-sided main, up to tip − 5). The points over in the player's games
  2–5 when all hold:
  - this season's FGA/g ≥ 1.2 × last season's (last season ≥ 20 games, from `logs_full`);
  - this season's mpg ≥ 20;
  - this season's FGA/g ≥ 0.8 × the line.
- **Data:** this season's FGA and minutes from nba_matchup.
- **Registered** at 2026-10-27T13:00:00 UTC (side-by-side amendment 7).
- **No pings,** as registered above, until a forward record exists. The user can change that.
- The window is short (games 2–5), so this season's record comes in the next week or two.

# AMENDMENT 2: EARLY_SURGE pings on (2026-10-27, at the user's request)
**User:** "yes, turn on shadow pings for early surge. I was looking at Harper and Achiuwa too, so this does have
some credibility."

- `nba_role_open.py` (every minute) pings "🟡 EARLY" (SHADOW) at each new points opener that passes
  `nba_early.early_surge`, the same decision the side-by-side's EARLY_SURGE replays.
- Only props opened after the deploy ping; lines already up are not pinged retroactively.
- The rule and its registration are unchanged; it is still judged by the side-by-side's bars.
