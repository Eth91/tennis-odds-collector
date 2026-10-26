# PRE-REGISTRATION: proj-1.1, NBA.com/stats families + availability on top of proj-1.0

Written 2026-10-26, **before any proj-1.1 feature has been built or scored.**

**Already seen before writing this:**
- proj-1.0's results (`PROJECTION_RESULTS.md`).
- The 2023-24 and 2024-25 absence / known-minutes diagnostic (`NBA_STATS_FEASIBILITY.md`).
- That the NBA.com families download, one game date per call (smoke test on 2024-01-10: row counts only).

proj-1.0 (config `a17d85db69`), its log, its scorecard and its frozen results are not changed. proj-1.1 is a
separate version that runs beside it. Data use is the owner's decision (2026-10-26), recorded in
`NBA_STATS_FEASIBILITY.md`.

## Question
Do NBA.com stat families, or availability and lineup information, make the projection more accurate and
better calibrated, measured against proj-1.0 and against FanDuel's close at FanDuel's lines?

## Data
`nba_stats_fetch.py` stores each family per game date (DateFrom = DateTo), raw and compressed, with its
fetch time. Values are as stored now, i.e. as of the game's end plus any later stat corrections. A
feature for a game on date d uses values from dates **< d** only.

The one exception is family F0's "this game" inputs (below). Historically they come from the game's
final lineup file and box score. That is an **optimistic proxy** for what is known at tip − 30: late
scratches and late lineup changes leak. It is reported as such.

## Model
proj-1.1 keeps proj-1.0 whole and adds one residual layer.

**Residual targets**, for each player-game:
- minutes: r_min = log((min + 1) / (μ_min + 1));
- each count stat s: r_s = log((s + 0.5) / (μ_s + 0.5)) − r_min, the per-minute residual.

μ is proj-1.0's M1 mean for that row (walk-forward, unchanged).

**Learner:** ridge regression on standardized features, one model per target (8 targets).
- It is refit at the start of each calendar month on every row dated earlier, starting 2022-11-01. So
  every prediction is out of sample.
- λ is chosen from {1, 10, 100, 1000} × n_features. The choice is made once, on 2023-24 normalized CRPS, for
  the all-families model, and then fixed for every arm.
- Implemented in numpy (the VM has no scipy or sklearn).

**New mean:** μ'_min = (μ_min + 1)·exp(r̂_min) − 1, and μ'_s = (μ_s + 0.5)·exp(r̂_min + r̂_s) − 0.5,
floored at 0.

**Distribution:** proj-1.0's analog ensemble, unchanged in construction: same K, same feature space,
built on μ' for targets and for the pool. All 8 stats are rescaled within each draw, so combos stay sums
within one draw.

## Feature families (the ablation units)
Every rate is an EWMA over the player's previous appearances, half-life 15 games. Each is a per-minute
rate, or a share of team totals where the stat is a share. It is shrunk toward his position group's
league rate from earlier dates using 100 pseudo-minutes (or 10 pseudo-games for shares). It enters as
log(rate / group rate). Missing means the group rate, plus a missing indicator.

| id | family | NBA.com source (kind) | features |
|---|---|---|---|
| F0 | availability & lineups | `lineups` (daily lineups file), box scores | starts this game (proxy); his starts share, last 10; teammates out: count of regulars out (7 of last 10, 24+ min), their minutes share and usage share; opponent regulars out: count, usage share; interactions: teammates-out usage share × his usage, starts × his minute share |
| F1 | advanced & usage | `adv`, `usage` | USG%, AST%, OREB%, DREB%, TOV%, PIE, possessions per minute; %FGA, %FTA, %AST, %REB, %TOV of team while on court |
| F2 | tracking | `pt_Possessions`, `pt_Drives`, `pt_Passing`, `pt_Rebounding`, `pt_CatchShoot`, `pt_PullUpShot`, `pt_ElbowTouch`, `pt_PostTouch`, `pt_PaintTouch`, `pt_SpeedDistance` | touches, time of possession, front-court touches, drives, passes, potential assists, secondary assists, rebound chances (off, def), contested rebounds, catch-and-shoot FGA and 3PA, pull-up FGA and 3PA, elbow/post/paint touches, distance: all per minute |
| F3 | shooting profile | `shotloc`, `scoring` | FGA share by zone (restricted area, paint, mid, corner 3, above-break 3), FG% by zone (shrunk), % of points by type, % of FGM assisted |
| F4 | hustle & defense | `hustle`, `defense`, `pt_Defense` | deflections, contested shots, loose balls, screen assists, box outs, charges (per minute); STL%, BLK%, defensive rating; opponents' FG% at rim |
| F5 | team & opponent context | `team_adv`, `team_opp` | own team's pace and offensive rating; opponent's pace, defensive rating, and opponent-allowed FGA, 3PA, REB, AST and TOV per possession (team EWMAs, half-life 10 games) |
| F6 | misc scoring | `misc`, `pt_Efficiency` | points off turnovers, second chance, fast break, paint (per minute); points per touch, per drive, per post touch |

## Periods
- **2022-23:** history and training only.
- **2023-24: development.** Fit (walk-forward), choose λ, and make the family keep/drop decisions.
- **2024-25: development after exposure.** proj-1.0 was tested here and the absence diagnostic was run
  here, so it is not fresh. The new families' results have not been seen. It is reported, labeled, and
  run **once** for the final candidate and the ablations.
- **2025-26: stats only** (no FanDuel lines). The same one run, CRPS and MAE.
- **2026-27 on: prospective, the only confirmatory test** (below).

## Arms (all walk-forward, same rows, same lines)
- **A0:** proj-1.0 (reproduced).
- **A_k:** proj-1.0 + family k alone, for k = F0..F6.
- **A_all:** all families.
- **A_all−k:** all minus k.
- **A_keep:** the families kept by the rule below. This is the proj-1.1 candidate.
- A_keep is also run without F0's "this game" proxies (**A_keep−proxy**). That shows what is left when
  lineups are not known.

## Metrics (as in NBA_PROJECTION_PREREG.md)
- **Stats:** MAE, RMSE, CRPS and log score per stat; normalized CRPS over the 8 stats.
- **FanDuel lines:** log loss, Brier and reliability at the −29 min line.
  - De-vig: proportional, both sides required.
  - Pushes are excluded (whole-number lines). A DNP is void.
- **Blend:** the logit blend with the de-vigged FanDuel price, w fitted on 2023-24 for each arm.
- **Intervals:** date-clustered bootstrap, 4,000 reps, seed 7.
- **Breakdowns:** by market, by minutes cohort, by history depth, and by regular-teammate-out vs not.

## Keep rule (2023-24 only)
A family is kept if, added alone to A0 (A_k vs A0), both of these hold:
- the normalized CRPS difference has an upper 95% bound < 0 after **Holm correction across the 7
  families** (one-sided, α = 0.05);
- the FanDuel-line log loss point estimate does not get worse (A_k − A0 ≤ 0).

## Decision lines
**On 2024-25 (development after exposure), information only:**
- A_keep vs A0 and vs the close, with intervals.
- No claim about the books comes from historical data.

**Prospective (2026-27), proj-1.1 logged beside proj-1.0 at tip − 30 with its version and config hash:**
1. *proj-1.1 better than proj-1.0:* (proj-1.1 − proj-1.0) log loss at FanDuel lines has an upper 95% bound
   < 0 at ≥ 2,000 graded props.
2. *Beats FanDuel's close:* (proj-1.1 alone − close) log loss has an upper 95% bound < 0 at ≥ 2,000 graded
   props. Reliability must be within 3 points in every bucket with n ≥ 200. It must then **replicate** on
   the next 2,000 graded props (upper bound < 0 again). The blend version of this line is secondary.
3. Below 2,000 graded props: "not enough prospective evidence."

Prospectively, F0's lineups come from `nba_lineups_poll.py` snapshots seen before tip − 30 (Confirmed or
Expected, as recorded), and from the official injury report. Nothing seen after the cutoff is used.

## Guards
- **Leakage (F1–F6):** every feature for date d is unchanged when all rows dated ≥ d are altered. Tested.
- **Leakage (F0):** the proxy inputs come only from lineup status and box-score presence, never from
  minutes or stats. Tested.
- No tuning on 2024-25, 2025-26 or the forward record.
- A family or arm not listed here is not added after seeing results. If one is, it gets a new version,
  a new pre-registration and its own prospective test.
- All arms are reported, including the ones that fail.
