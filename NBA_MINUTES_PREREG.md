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
