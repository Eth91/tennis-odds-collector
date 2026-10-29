# PRE-REGISTRATION: an NFL projection model (2026-10-29, about 22:00 UTC, before code)

**User:** "build a real nfl projection model and test it." The NBA rule failed on a plain per-game average
(`NFL_UNDER_PREREG.md`). This model is volume × share × efficiency, with the game's script, the injury report and the
opponent. `nfl_model.py`, Mac only.

**Data (nflverse):**
- weekly player stats 2022–2025;
- schedules (the closing spread and total);
- the official injury report (game status by week).
- **Lines:** as `NFL_UNDER_PREREG.md` (near kickoff, the FanDuel/DraftKings main rung, the best of the two prices).
- History is everything before the game's (season, week); the next game is never read.

**Fit and test:**
- Every fitted number comes from 2023 (with 2022 as history): the team-volume regressions, the error distributions
  and the calibration.
- 2024 and 2025 are held out; nothing is fit on them.

## The model
- **1. Team volume per game:**
  - Three quantities: targets, pass attempts and carries.
  - Each is an OLS fit on 2023 team-games: the team's average (this season before the game, last season counted as 4
    games), the team's spread (+ = favored) and the game total.
- **2. His share:**
  - Target share, carry share and pass-attempt share.
  - Each is his total over his team's totals, in his games this season, with last season's games counted as 4 games
    (any team).
  - He needs 3+ games across the two seasons.
- **3. The injury report:**
  - Teammates listed Out or Doubtful that week, from the pool who played in his team's last 4 games, give their
    shares away.
  - Each out player's share goes to the active pool in proportion to share × (2 for the same position, else 1).
- **4. Efficiency:**
  - Catch rate, yards per target, yards per carry, completion %, yards per attempt.
  - Each is his rate over the same games, shrunk toward his position's 2023 average by 40 targets, 60 carries or 150
    attempts.
  - Times the opponent's allowed rate to his position (this season before the game, last season as 4 games) over the
    league's, pulled halfway to 1.
- **5. Projections:**
  - receptions = team targets × target share × catch rate; receiving yards = team targets × target share × yards per
    target;
  - rush attempts = team carries × carry share; rush yards = rush attempts × yards per carry; rush + rec yards = the
    sum;
  - pass attempts = team pass attempts × his share; completions = attempts × completion %; pass yards = attempts ×
    yards per attempt.
- **6. Probabilities:**
  - P(under) is the 2023 empirical distribution of actual ÷ projection, per market and projection tercile, read at
    line ÷ projection.
  - Then a logistic recalibration fit on 2023: logit P = b0 + b1 logit(model) + b2 logit(the book's no-vig under).

## The tests (2024 and 2025)
- **A, accuracy:**
  - Per market and pooled: the model's MAE against the plain per-game average's (the failed test's projection).
  - Also the line itself as a forecast.
  - **Passes** if the model beats the average pooled, and in at least 6 of the 8 markets, in both seasons.
- **B, the book:**
  - Log loss of the recalibrated P(under) against the book's no-vig on every headline prop.
  - **Passes** if lower in both seasons.
- **C, bets:**
  - Every headline prop where the recalibrated p × the best price − 1 ≥ 5% on either side.
  - **Passes** if pooled ROI > 0 with the 90% interval's low end > 0, and ROI > 0 in both seasons.
- **Also (information):**
  - The under rule's ping set with the model's projection (30–50% below, −150 or better).
  - The bets by market and side.

A pass on C is a candidate for the forward record (NFL 2026, shadow), not a betting edge. No live change without the user.

## Result (2026-10-29, about 22:15 UTC): A FAIL, B FAIL, C FAIL
- **Fit on 2023:**
  - Team volume (1, team average, spread, total): targets 11.0 + 0.42 avg + 0.01 spread + 0.18 total; attempts
    13.8 + 0.39 + 0.01 + 0.16; carries 19.9 + 0.43 + 0.20 − 0.11.
  - The calibration puts 0.12 on the model and 0.85 on the book.
  - 33,616 props have a projection.

| | 2023 (fit) | 2024 | 2025 |
|---|---|---|---|
| **A** MAE, model / plain average / the line | 15.56 / 15.76 / 14.50 | 16.52 / 16.47 / 15.05 | 15.91 / 15.74 / 14.55 |
| markets where the model beats the average | 7 of 8 | 2 of 8 | 3 of 8 |
| **B** log loss, model / book | 0.68960 / 0.69042 | 0.69004 / 0.68922 | 0.68912 / 0.68899 |
| **C** EV ≥ 5% bets | — | 403, 48.1%, −5.1% | 329, 47.4%, −3.9% |

- **C pooled:** 732 bets, −4.6% [−11.1, +1.5]; unders −2.2%, overs −7.5%.
- **Information:** the ping set with the model's projection made +4.5% | −0.3% | +4.5% (332 | 402 | 293).
- **Checks (after the result):**
  - The injury report moved 1,143 of 4,015 2024 receiver-games' target shares by half a point or more.
  - The team-target fit's 2024 MAE is 5.98 against the team's own average's 6.00.
  - The parts work, but they add almost nothing over a plain average.
- **Reading:**
  - The line is a far better forecast than either (about 9% lower MAE in every market).
  - Its edge is information public box scores don't carry: practice reports, beat news, role changes, weather.
  - The small 2023 gain was fitting noise.
  - Nothing here goes forward.
