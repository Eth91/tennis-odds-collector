# PRE-REGISTRATION: MINUTES, the step-in's minutes when a starter is out

Written 2026-10-28 (about 20:55 UTC), before any model was built or run on any data. Research only: nothing changes
live unless the user decides after seeing the result. `nba_flags.LIVE_TIERS` stays empty.

## Why
BOOST's step-in projections failed on minutes:
- amendment 2–3 stretched bench per-minute rates to 24 minutes (McCain 10.3, which the user called unrealistic);
- amendment 5 used his 25+ minute games, but the backtest's step-ins played 21.4 minutes on average and only 30%
  reached 25 (`NBA_BOOST_PREREG.md`).
- The backtest also had to guess the step-in from minutes, because the 2023-25 logs have no starter flags.

The user: "don't shut it down but find ways to make a better minutes projection model."

## New data found
`.projdata/nba_stats_raw.sqlite`, `kind = 'lineups'`: NBA.com's daily lineups (the source BOOST reads live) as of
after the games:
- 2023-24 (160 dates), 2024-25 (163) and 2025-26 (164); 2022-23 is a 404;
- `lineupStatus` Confirmed; the five with a position are the starters.

They give real starters for 2023-26. Confirmed lineups are known about 30 minutes before tip, the same timing as the
archive's tip lines.

## The user's choices (asked 2026-10-28)
| Choice | Answer |
|---|---|
| Whose minutes | The player moving into the starting lineup, **and** the bench player who takes over his bench minutes |
| Lineup knowledge | Both: confirmed starters and the projected five, reported separately |
| Model | A simple blend and a fitted model, compared |
| Better means | Lower minutes error than last-5 and ROLE v3 on held-out seasons, **and** better STEP bets at real lines |
| The bench pickup | History (whose minutes rose most when the new starter started before), else position |
| Split | Fit on 2023-24; test on 2024-25 and 2025-26 (2025-26 has no odds, so its bets cannot be judged) |

## Spots and targets
Everything reads only games before the date, except tonight's five (confirmed: NBA.com's final lineup; projected: the
page's projected five) and who is out (the box score, hindsight as in BOOST's backtest).
- **Data:** `logs_full` 2022-23 to 2025-26 (minutes and stats), the lineups above (starter flags 2023-26), positions.
- **Usual five, projected five, pairing:** as `nba_boost` amendment 4 (the lineup tab's logic), with starter flags
  from the lineups. "Out" is a usual starter on the team who does not play.
- **A spot:** team T on date D, a usual starter X out, X's absence game 1–3. All absence games are reported for
  information.
- **Target A, the new starter S:** paired with X.
  - Confirmed: from NBA.com's final five (not in the usual five).
  - Projected: the projected five's pick.
  - Graded on S's actual minutes. A player who did not play counts as 0; that happens live too.
- **Target B, the bench pickup R:** among tonight's bench, meaning players who played for T in its last 3 games, are
  not out, and are not in tonight's five:
  - the player with the largest gain, his mean minutes in past T games (this season and last) that S started minus
    his mean in games S played off the bench;
  - he needs 3+ games of each kind;
  - otherwise the bench player sharing a position letter with S with the most minutes over T's last 10 games.

## Models (minutes)
- **Baselines:**
  - **L5:** his mean minutes over his last 5 games for T;
  - **V3:** ROLE1 v3's projection for him (`nba_role.project`, mode v3, the out rotation players absent), the live
    ROLE_OPEN model.
- **Simple blend (one per target):**
  - **A:** w × his mean minutes over his last 10 starts (any team, this season and last) + (1 − w) × V3, with
    w = n_starts / (n_starts + 3).
  - **B:** w × his mean minutes in past T games S started + (1 − w) × V3, with w = n / (n + 3).
- **Fitted:** scikit-learn HistGradientBoostingRegressor (default settings, random_state 0), one model per target and
  lineup knowledge, fit on 2023-24 spots. Features:
  - L5, his season mpg, V3;
  - his mean minutes in past starts and the number of them; his mean in games S started and the number (B);
  - X's minutes per game; whether he shares a position letter with X;
  - days of rest (capped at 4), the game's index in the season;
  - the team's rotation size (players with 10+ minutes a game over its last 5 games);
  - the number of usual starters out tonight.

## Measures and bars
- MAE and bias of minutes, per target, per lineup knowledge, on 2024-25 and 2025-26 (2023-24 in-sample for
  information).
- **Minutes pass:** a model's MAE is below both L5 and V3 in both test seasons, for that target and lineup knowledge.
- **The fitted model is kept** only if its MAE is ≥ 0.25 minutes below the simple blend's in both test seasons;
  otherwise the simple blend is the model.
- **Bets (2024-25 tip lines; 2023-24 reported in-sample):**
  - **Projection:** the chosen model's minutes for S (target A) and R (target B) × his per-minute rates (points,
    rebounds, assists, threes; combos summed). The rates come from his games this season and last, any team,
    weighted toward this season as in ROLE1 (K = 150 minutes of last season).
  - **Flag:** the over when projection ≥ 1.15 × line, priced −150 or better. For S, X must be relevant to the market
    (BOOST rule 6). For R, every market.
  - **Pass:** ROI > 0 in 2024-25 with ≥ 100 flags, and above the live STEP rule's ROI on the same 2024-25 spots
    (the 24-minute version, with confirmed starters as its step-ins).
- **Either way** the user decides what goes live. Nothing is deployed from this file without asking.

## Result (2026-10-28, about 21:00 UTC)
`python3 nba_minutes.py --json .projdata/minutes_result.json` (68 s). Spots in absence games 1–3; MAE in minutes (bias).

| target, knowledge | season | actual | L5 | V3 (live) | blend | fitted |
|---|---|---|---|---|---|---|
| A new starter, confirmed | 2024-25 (1,403) | 28.4 | 8.26 (−6.7) | 6.32 (−1.8) | **5.33** (−1.3) | 5.11 (+0.1) |
| | 2025-26 (1,437) | 28.1 | 7.71 (−6.0) | 6.19 (−1.3) | **5.20** (−1.1) | 5.27 (+0.3) |
| A new starter, projected | 2024-25 (896) | 26.7 | 6.68 | 5.81 | **5.54** | 5.42 |
| | 2025-26 (844) | 26.3 | 6.47 | 5.69 | **5.27** | 5.21 |
| B bench pickup, confirmed | 2024-25 (1,451) | 20.3 | 6.53 | 6.28 | 6.25 | **5.67** |
| | 2025-26 (1,453) | 19.9 | 6.32 | 6.00 | 6.09 | **5.63** |
| B bench pickup, projected | 2024-25 (1,466) | 21.3 | 6.95 | 6.01 | 6.84 | 6.14 |
| | 2025-26 (1,465) | 21.7 | 6.75 | 5.89 | 7.11 | 5.95 |

**Minutes:**
- **A, confirmed: PASS, the blend.** It is 16% below V3's error. The fitted model is not 0.25 better in both seasons.
- **A, projected: PASS, the blend.**
- **B, confirmed: PASS, the fitted model.** The blend fails 2025-26.
- **B, projected: FAIL.** Nothing beats V3.
- **The headline:** a real new starter plays about 28 minutes (26–27 for the projected pick). Last-5 misses by 6–7
  minutes low, and V3 by 1–2.
- The fitted models' 2023-24 errors (about 2) are in-sample fits, not evidence.

**Bets (projection ≥ 1.15 × line, −150 or better):**

| | 2023-24 (minutes in-sample) | 2024-25 (held out) |
|---|---|---|
| new model, all | 708, +19.3% | **549, +0.5%** (90%: −5.8%, +7.0%) |
| A (blend) | 220, −4.2% | 292, +5.2% |
| B (fitted) | 488, +29.8% (fitted on this season: not evidence) | 257, −4.8% |
| live STEP, confirmed starters as step-ins | 113, −8.6% | **109, +5.6%** |

**Bets: FAIL.** 2024-25 is +0.5%, below the live STEP's +5.6% on the same spots. Both hit about what the book's
no-vig price implied (51%).

**Reading:**
- The better minutes are real, but at tip lines (with confirmed lineups) the books price the starter's bigger role.
- Also new: with real starters as its step-ins, the live STEP rule's backtest is −8.6% and +5.6%, not the +11% and
  +16% it showed with the minutes-guessed step-ins. Its evidence is weaker than it looked.
- Openers before the lineup is known cannot be tested with this archive.

# AMENDMENT 1: the audit (2026-10-28, about 21:20 UTC, before it was run)
**User:** "audit the new minutes model, dial it in even more, find the little nuances that it's missing right now."
(The blend went live for STEP as BOOST amendment 6.)

**Protocol:**
1. **Explore on 2023-24 only,** the fit season. It is used only for the fitted model, and the blend has nothing fitted
   but K = 3.
   - **Target A, confirmed** (the live STEP case): residual = actual − blend, by bucket of each candidate nuance below.
     Reported as mean residual (bias), MAE and n.
   - **Target B:** the fitted model's 2023-24 residuals are in-sample, so B is explored with V3's residuals.
2. **Candidate nuances:**
   - **Known before the game:**
     - how many starts he has, and from which season;
     - whether he started before for this same X;
     - X's minutes; position match with X;
     - starters out (1 vs 2+); absence game n;
     - rest days and long layoffs (back from his own injury);
     - the game's index in the season (early season, April);
     - home or away (from the lineups files);
     - the team's starter minutes (how long its coach plays starters) and rotation size;
     - each team's mean residual (coach habits).
   - **Hindsight, to size what cannot be predicted:** the final margin (blowouts), overtime, and fouls (5+).
3. **Then:** the findings go to the user with proposed refinements and choices. Nothing is changed before that.
4. **Any adopted refinement** is written here as a v2 before it is run on 2024-25 and 2025-26. Same bars: v2's MAE must
   be below the blend's (A) or the fitted model's (B) in both test seasons. Bets as before.
