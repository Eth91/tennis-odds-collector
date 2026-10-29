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

## Amendment 1: the audit, run (2026-10-28, about 21:30 UTC). Exploration on 2023-24 only
`nba_minutes_audit.py`. Bias = actual − model, so positive means under-projected.

**Target A (the blend), all: bias +2.0, MAE 5.81 (n 1,204):**
- **no past starts: +6.0** (n 173). 1–2 starts +2.5; 3–5 +0.6; 6–10 +1.1;
- **his season mpg under 15: +5.0**; not started before for this X +4.2 (with: +1.3);
- absence game 1 +2.4 (game 3 +0.8); Oct–Nov +3.2 (April +0.9); a big out (X in group C) +2.9;
- team means from NYK +5.8 to PHX −0.4;
- **hindsight:** blowouts (20+) −0.2 against close games +2.9; overtime +4.8 (n 53).

Without past starts the blend falls back to V3, which is built on his bench role. Those players actually played a
median of 28 minutes (10th–90th percentiles 18–37) while V3 said 21.6.

**Fixes sized on 2023-24 (MAE all / no starts):**

| | all | no starts |
|---|---|---|
| current | 5.81 / 8.15 | |
| K = 1, 2, 5 | 5.79–5.86 | 8.15 |
| floor at the team's starter minutes | 5.53 (bias −1.5) | |
| floor at X's minutes | 5.63 (bias −1.4) | |
| V3 + 2 | 5.56 | 7.23 |
| **V3 floored at 24 / 26 / 28** | 5.31 / **5.29** / 5.34 | 5.56 / **5.40** / 5.52 |

After the 26 floor, every pre-game bucket is within ±0.6 minutes, except the layoff bucket (+2.6, n 11). That covers
absence game, month, X's group, no starts, starters out, rest, rotation, and team starter minutes.
- **Team means do not persist:** the correlation between 2023-24 and 2024-25 team biases is −0.07 over 30 teams, so
  there is no coach adjustment.
- **What is left is hindsight:** blowouts −1.8, close games +1.0, overtime +3.6.

**Target B:** the fitted model out of fold (5 folds by date within 2023-24) has MAE 5.45 and bias −0.2, against V3's
6.02. Every bucket is within ±0.4 (the layoff bucket −0.8, n 18). Nothing is missing.

# AMENDMENT 2: A v2, the 26-minute floor (2026-10-28, before it was run on 2024-25 or 2025-26)
**User:** chose "26 minutes" and "show me first".
- **A v2:** w × his last-10-starts mean + (1 − w) × max(V3, 26.0), with w = n / (n + 3). The floor was chosen by
  looking at 2023-24, so 2024-25 and 2025-26 are the test.
- **Pass:** v2's MAE is below the current blend's in both 2024-25 and 2025-26, for confirmed starters. Projected
  fives are reported too.
- **Bets (information):** STEP-style flags from v2 against the v1 blend, at 2024-25 tip lines.
- **If it passes,** the result goes to the user before anything changes live.

# AMENDMENT 3: the spread test (planned 2026-10-28; to run once there are 300+ games with lines)
**User:** "yes, once there's enough data." Blowouts and overtime are the largest remaining error, and only the spread
can foresee them.
- **Data:** `nba_lines.sqlite` `game_lines` (FanDuel/DraftKings spread and total, from 2026-10-25), and this season's box
  scores.
- **Measure:** each starter's minutes minus his own last-10 mean, against |spread| (FanDuel's last before tip;
  DraftKings' if FanDuel has none) and the total.
- **Bucketed,** then a one-coefficient linear fit (minutes per point of |spread| beyond 6), on games before the run date.
- **Run when** 300 games have a spread and box scores (around early December). The first 150 games fit the
  coefficient; the next 150 test it.
- **Pass:** a STEP projection with the spread term has lower MAE than v2's on the new starters in the test games.
  With few step-ins there, starters as a whole are reported too.

**Amendment 2: run (2026-10-28, about 21:40 UTC). PASS for confirmed starters; WORSE for the projected five.**
MAE (bias as model − actual):

| A | 2024-25 | 2025-26 | first-time starters 2024-25 / 2025-26 |
|---|---|---|---|
| confirmed, v1 → **v2** | 5.33 (−1.3) → **4.99** (−0.0) | 5.20 (−1.1) → **5.02** (+0.0) | 8.72 → 5.26 / 8.87 → 5.56 |
| projected, v1 → v2 | 5.54 (+1.5) → 5.85 (+2.2) | 5.27 (+1.1) → 5.55 (+1.8) | n 4 / n 5 |

- With the projected five, the pick sometimes does not start, so a 26-minute floor over-projects.
- The floor belongs only to confirmed starters (NBA.com's lineup posted).

**Bets (2024-25 tip lines, confirmed starters):** v1 292 flags, +5.2%; v2 351, +3.9% (90%: −4.3%, +11.7%). In 2023-24
both are −4.2%. The better minutes do not make better bets at tip lines. Nothing changes live until the user decides.

# AMENDMENT 4: the error floor (2026-10-28, about 21:35 UTC; a bound, not a model)
**User:** "run a constant improvement loop until you get that minutes error under 3 minutes, and also make an FGA, FTA,
3PA projection model for each of these players jumping into the lineup." Before any loop, the floor was measured on
target A with confirmed starters (absence games 1–3).
- **Oracle:** his mean over his next 10 starts this season, which uses future games that no model can know. This bounds
  what perfect knowledge of his role would give.

| MAE | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|
| minutes, v2 (on rows with 3+ future starts) | 4.93 | 4.66 | 4.71 |
| minutes, oracle | 4.97 | 4.69 | 4.70 |
| minutes, established starters (20+ starts) against their own season mean, in-sample | 4.29 | 4.14 | 4.15 |
| minutes, v2 + final margin + overtime + 5 fouls (hindsight, in-sample) | 5.15 (v2 5.29) | | |
| FGA: his per-minute rate × v2 minutes / oracle | 2.96–3.06 / 3.10 | 3.06 / 3.10 | |
| FTA | 1.64 / 1.63–1.67 | 1.64 / 1.67 | |
| 3PA | 1.62 / 1.66 | 1.74 / 1.79 | |

**Reading:**
- A minutes MAE under 3 is below the floor: established starters themselves vary about 4.1–4.3 minutes around their own
  mean.
- v2 already equals the oracle on role. The game script, through the spread, is the only pre-game information left,
  and even in hindsight it is worth about 0.15.
- Shot volume from his per-minute rate × v2 minutes is also at the oracle bound. Rates from his starts are no better.

# AMENDMENT 5: shot volume in the STEP ping (2026-10-28, about 21:40 UTC)
**User** (after the floor): "put FGA/FTA/3PA in the pings."
- Each BOOST_STEP ping adds his projected FGA, FTA and 3PA: his per-minute rates (`nba_boost.rates`, last season worth 150
  minutes) × his STEP minutes. Amendment 4 shows that rate × minutes sits at the oracle bound.
- This is information only: no flag decision changes. The four BOOST rules are re-registered at 2026-10-28T22:30 UTC,
  because the data they load now carries FTA and 3PA.

# AMENDMENT 6: minutes for backups whose position-mate is out (2026-10-29, about 05:45 UTC, before code)
**Why:**
- On 2026-10-28, V3 gave Clint Capela 11.1 minutes with Alperen Sengun out. He played 22 (Oscar Tshiebwe, F-C, 14);
  his two under pings lost.
- **The cause:** `nba_role.project` spreads an absent rotation player's minutes over the whole active roster by base
  minutes, with only 3× weight on his position group. A team's one or two backups at his spot get far less than they play.
- **User:** "fix the minutes projection for guys like Capela": test both fixes and keep the better one. The under
  pings move to it only if the under backtest holds.

**Rows:** every player who played in 2023-24 and 2024-25, with V3 as in `nba_tests4.player_games` (outs from the box
score, absent = `ROLE.Season.absences`). The truth is his minutes.

**Target nights ("Capela-type"):** he is not in his team's usual five, and an absent rotation player shares a position
letter with him (G, F, C; "F-C" has both).

**Fix S, position slots:** a share α of each absent X's minutes goes to the active players sharing a position letter
with X, split by base minutes × V3's share factor. The rest is spread as V3 does now, so α = 0 is V3.
- α per X's position group (G, F, C), from {0, 0.1, …, 1}.
- Fit on 2023-24 by coordinate descent (two passes), on the MAE over every player-game on nights with an absent rotation
  player.

**Fix H, his history without X:**
- His team's games this season and last, before tonight, in which every absent X was on the team and sat and he
  played; his mean minutes over the last 10 at most, n games.
- Minutes = (1 − w) × the model's + w × that mean, w = n / (n + K), with K from {1, 2, 3, 5, 8} fit on 2023-24.

**Candidates:** S, H, and S then H. The pick is the lowest 2024-25 MAE on target nights (α and K from 2023-24 only).

**Gate 1, minutes:** the pick cuts 2024-25 target-night MAE by ≥ 0.3 minutes against V3 and raises 2024-25 overall MAE
by no more than 0.05. Else FAIL and nothing changes.

**Gate 2, unders (the user's condition):**
- UNDER20's ping set (30–50% below, under −150 or better, not threes, best FanDuel/DraftKings at tip), with the
  projection = the pick's minutes × the same rates.
- Its 2024-25 ROI must be at least V3's (+15.0%) − 1 point. 2023-24 is shown, in-sample for α and K.
- **If both pass:** the under pings move to the new minutes, deployed after the user's OK, and a new side-by-side rule
  tracks them.
- **If only gate 1 passes:** the new minutes are shadow-tracked only.

**Also reported:**
- Capela on 2026-10-28 under the pick.
- MAE on all absence nights and for starters.
- Out of scope: V3 counts X as absent only after 3 games this season, so the first games of a season redistribute nothing.
