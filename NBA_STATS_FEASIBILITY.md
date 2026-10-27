# NBA.com/stats for Pickz projections: feasibility (Phase 1)

2026-10-26. Research only; nothing here changes `proj-1.0`, its config (`a17d85db69`), its logs, its scorecard,
or its frozen results. No collector was written, no model was changed, nothing was deployed. Not legal advice.

## Bottom line

1. **No authorized access.** NBA.com's terms do not let its statistics be used in connection with gambling,
   and its FAQ says the stats are not for download. There is no public NBA.com feed or license for this use.
   Under this task's own rule, the work stops here: no new NBA.com collector, no NBA.com feature in a model.
2. **The engine already depends on NBA.com data the same way.** `proj-1.0`'s box-score history comes from
   `stats.nba.com/stats/leaguegamelog` and `cdn.nba.com` liveData, fetched with browser-impersonating
   requests. Several other modules do the same (table below). This is an existing exposure the owner should
   decide on, separate from this task.
3. **Even with rights, richer production stats are not where the gap is.** The diagnostic below (development
   after exposure) shows the model's deficit to FanDuel's close doubles when a regular teammate is out, and
   that the same model *with the minutes known* beats the close by ~0.055 log loss. The market's edge is
   minutes and availability information. Tracking, hustle and play-type stats describe per-minute
   production; a pre-registered tracking test (NBA_TRACKING_PREREG.md) was already **killed**.
4. **The compliant path with real potential** is licensed data (the NBA's exclusive distributor is
   Sportradar) and a pre-registered availability-aware minutes model, judged only on prospectively logged
   forecasts. Nothing in this report shows the engine can beat the books; it shows where it would have to.

## Access and terms (checked 2026-10-26)

| source | what it says | link |
|---|---|---|
| NBA.com/Stats FAQ | stats are for viewing on the site, not available for download for academic or personal use; no API, feed or licensing contact | [FAQ](https://www.nba.com/stats/help/faq) |
| NBA.com Terms of Use §1 | downloads only to a single computer for personal, noncommercial use; Basketball Content may not be reproduced or republished without written permission | [Terms](https://www.nba.com/terms) |
| NBA.com Terms of Use §9 (NBA Statistics) | attribution required; news reporting or private noncommercial use only; item (iv): not "in connection with any gambling activity"; no fantasy/commercial products; item (vii): a database of comprehensive, regularly updated statistics needs the operator's prior consent | [Terms](https://www.nba.com/terms) |
| Sportradar | official NBA technology partner and exclusive worldwide distributor of NBA data since 2021, including optical-tracking-derived data from 2023-24; supplies FanDuel | [NBA announcement](https://www.nba.com/news/nba-sportradar-announce-landmark-long-term-global-partnership), [Sportradar](https://sportradar.com/content-hub/blog/elevate-your-nba-coverage-with-sportradars-cutting-edge-solutions/?lang=en-us) |

Pickz shows sportsbook prices next to model estimates, so it is "in connection with gambling" on any reading.
Whether the terms bind, and how facts-vs-compilations law applies, is a question for counsel, not this repo.

## What the engine already fetches from NBA.com

| module | endpoint | used by | method |
|---|---|---|---|
| `nba_logs_full.py` | `stats.nba.com/stats/leaguegamelog`, `playerindex` | **proj-1.0 history** (`nba_gamelogs.sqlite`, 2022-23..2025-26) and positions (`playerindex`) | curl_cffi `impersonate="chrome"`, NBA site headers incl. `x-nba-stats-token` |
| `nba_matchup.py` | `cdn.nba.com/static/json/liveData/boxscore` (box scores); `stats.nba.com/stats/synergyplaytypes` | **proj-1.0** 2025-26..2026-27 box scores; matchup info cells | same |
| `nba_tracking.py` | `stats.nba.com/stats/leaguedashptstats` (Passing, Rebounding, one date per call) | killed tracking test; OPPORTUNITY cell | same; its docstring notes the VM is answered only with impersonation |
| `nba_profiles.py` | `leaguedashplayershotlocations`, `leaguedashteamshotlocations`, `synergyplaytypes`, `leaguegamelog` | home/away 2022-23..2024-25 for proj-1.0 (`team_games`); zone/play-type profiles | same |
| `nba_rosters.py` | `cdn.nba.com` schedule + boxscore; `stats.nba.com/stats/playerindex` | slate, rosters | same |
| `nba_injury_report.py` | `ak-static.cms.nba.com/referee/injury/Injury-Report_*.pdf` | official status (availability table, triggers) | plain download of the published PDF |

Impersonating a browser to get answers from an endpoint that refuses ordinary clients is the "bypass access
controls" this task rules out. The official injury report differs: it is a document the league publishes for
public disclosure, fetched plainly. It is still NBA.com content under §1.

## Inventory and verdict matrix

Coverage below is as NBA.com reports it (FAQ, page notes) or as already held in this repo. Coverage not held
here is **not verified**; verifying it would mean calling the endpoints this task rules out.

| family | NBA.com category / endpoint | grain, keys | coverage | vs. tip − 30 min; point-in-time history | kind; redundancy | verdict for Pickz now | if licensed |
|---|---|---|---|---|---|---|---|
| traditional box score | Box Scores; `leaguegamelog`, liveData boxscore | player-game; NBA `GAME_ID`, `PERSON_ID`, `TEAM_ID` | back to 1946-47 (FAQ); held 2022-23 → | final ~minutes after the game; past games are fixed facts (stat corrections rewrite silently) | raw outcomes; the model's core | not authorized (already in use) | **usable now**: the base of any model |
| advanced box (usage, AST%, REB%, TOV%, pace) | Advanced Box Scores | player-game, team-game | 1996-97 → (FAQ) | 10-15 min after the game (FAQ); no snapshots | derived from box score; **redundant** with rates the model already forms | not authorized | not worth modeling separately |
| four factors | Advanced / Four Factors | team-game | 1996-97 → | after the game | team-level derived; overlaps opponent/pace factors | not authorized | not worth modeling |
| tracking: touches, time of possession, drives, passes, potential assists, catch-and-shoot, pull-up, rebound chances | Tracking; `leaguedashptstats` | player-game via one-date queries | ~2013-14 → (not verified); held 2022-23..2024-25 for Passing/Rebounding (killed test) and 2025-10-21 → | after the game; no snapshots; current values only | opportunity signal, but **prior KILL** (NBA_TRACKING_PREREG.md: −4.71% vs −3.46% control, calibration unchanged) | not authorized | low priority; needs a new design + prereg |
| hustle: deflections, contested shots, screen assists, loose balls, box outs | Hustle | player-game, team-game | ~2015-16 → (not verified) | after the game; no snapshots | mostly defensive/effort; weak link to the 8 targets except stl/blk | not authorized | not worth modeling (stl/blk have historical lines only) |
| shooting by zone / shot dashboard | Shooting, Shot Dashboard; `leaguedashplayershotlocations` | player-season (aggregates), player-game with date filters | zones 1996-97 →; dashboard ~2013-14 → | season aggregates include future games unless date-filtered; no snapshots | descriptive of points/threes mix; overlaps fg3m rate | not authorized | prior-season profiles only; low priority |
| play types (Synergy), offense and defense | Play Type; `synergyplaytypes` | player-season, team-season | ~2015-16 → (not verified); held 2022-23..2023-24 + one 2026-10-26 snapshot | **season-to-date snapshots only**; historical values include later games (leakage) | context; **amendment 30 rejected** pace × matchup as a projection change | not authorized | prospective snapshots only; low priority |
| defensive dashboard / opponent shooting | Defensive Dashboard, Opponent Shooting | player-season, team-season | ~2013-14 → | season aggregates; no snapshots | opponent context; overlaps the model's opponent-allowed factor | not authorized | not worth modeling |
| lineups, on/off, rotations | Lineups (from 2007-08, FAQ); on/off splits | lineup stint, player-season | 2007-08 → | after the game; no snapshots | **role/minutes signal**: the family aimed at the actual gap | not authorized | **high priority**: drives the minutes model |
| play-by-play, shot chart events | Play-by-play, Shot Chart | event, shot | 1996-97 → | live and final | raw; would rebuild rotations/minutes patterns | not authorized | medium: only as the source for rotation features |
| team / opponent pace and efficiency | Teams / Advanced | team-game | 1996-97 → | after the game | already modeled (pace factor from box-score possessions) | not authorized | redundant |
| clutch / situational | Clutch | player-season | 1996-97 → | season aggregates | tiny samples, unstable ratios | not authorized | not worth modeling |
| official injury report | `ak-static.cms.nba.com` PDF (not NBA.com/stats) | player-game-date, status | held 2026-10-22 → (every report) | **published before tip, timestamped**; genuine point-in-time | availability: the second half of the gap | already collected; NBA.com content (§1); owner's call | **usable only prospectively** (no history before 10/22) |
| starting lineups | not an NBA.com/stats product | team-game | not collected | announced near tip | strongest minutes signal | not collected | licensed feeds carry it; high priority |

## Evidence on value (independent of rights)

Prior pre-registered tests on this repo's data:
- **Tracking opportunity** (rebound chances, potential assists) in the pricing model: KILL, worse than control,
  calibration unchanged (`NBA_TRACKING_PREREG.md`).
- **Pace × matchup-vs-position** as a projection change: rejected, 2024-25 card +$236 vs +$1,535 (amendment 30).
- **proj-1.0** (`PROJECTION_RESULTS.md`): beats simple baselines on CRPS on both held-out seasons, loses to
  FanDuel's close at its lines (+0.024 log loss, 2024-25), and the blend adds nothing.

New diagnostic, `nba_proj_diag.py`: **development after exposure** on 2023-24 (tuning) and 2024-25 (spent).
FanDuel's de-vigged close vs. proj-1.0 at the same lines, pushes excluded, date-clustered 95% intervals
(2,000 reps). "Regular out": a teammate who appeared in 7+ of the team's previous 10 games averaging 24+
minutes is not in this game's box score.

| model log loss − close | 2023-24 | 2024-25 |
|---|---|---|
| all props (n 85,914 / 82,697) | +0.0181 [+0.0153, +0.0212] | +0.0237 [+0.0210, +0.0265] |
| a regular teammate out (n 33,954 / 35,758) | +0.0269 [+0.0219, +0.0321] | +0.0341 [+0.0285, +0.0397] |
| no regular out (n 51,960 / 46,939) | +0.0124 [+0.0097, +0.0152] | +0.0158 [+0.0132, +0.0186] |
| same model, minutes known (upper bound) | −0.0582 [−0.0619, −0.0546] | −0.0535 [−0.0571, −0.0498] |

Reading:
- The "all props" row reproduces the frozen results (+0.0181, +0.0237), so the harness matches.
- The deficit roughly **doubles** when a regular teammate is out. The model ignores absences; the close does not.
- It is still positive with nobody out. The market knows more than a box-score model even on quiet nights
  (minutes limits, rest, lineup news for non-regulars).
- "Minutes known" keeps every analog's per-minute production and scales it to the minutes actually played.
  It **overstates** what any pre-game minutes forecast could reach, because actual minutes carry game-script
  information (blowouts, fouls, overtime). Even so, the size of the swing locates the market's edge in
  minutes and availability, not in per-minute production. Better production stats can only work on the part
  left after minutes, which is where the model already does well.

## Compliant alternatives

1. **Licensed data.** Sportradar is the exclusive official distributor: box scores, play-by-play, injuries,
   lineups, tracking-derived stats, licensed for betting-adjacent use by contract. Its self-serve trial keys are
   time- and quota-limited (reported: 30 days, ~1,000 requests), far too small for history, so a real
   test needs a commercial agreement. Others (SportsDataIO, balldontlie) sell NBA data in tiers. Their terms for betting-adjacent use
   were **not verified** here; read them, or ask sales, before building.
2. **Data already owned by the user.** Book prices (FanDuel/DraftKings boards, the paid odds-history store)
   and the prospective forecast log are the user's own records. Their source terms are separate from NBA.com's.
3. **No-data option.** Keep proj-1.0 running as-is for its pre-registered forward test (2,000 graded props),
   and treat its page copy as the honest summary it already is.

## Recommended path, only after the rights question is settled

`proj-1.1` (new version, new prereg, proj-1.0 untouched alongside):
- **Availability-aware minutes.** Use the official status at tip − 30 min for the player and his teammates.
  Redistribute absent players' minutes and usage within the team, with redistribution shares learned from
  earlier games and shrunk for thin samples. Starting lineups go in if a licensed feed supplies them.
- **Joint draws unchanged**, so combos stay coherent.
- **Evaluation:**
  - Historical as-of-game-end absences can be used for development only, labeled optimistic, because late
    scratches leak.
  - Confirmation comes only from prospectively logged forecasts at the same cutoff as proj-1.0, with one
    primary metric pre-registered: model − close log loss at FanDuel lines, with an interval.
  - Minimum sample at least 2,000 graded props, no tuning on the forward record, and replication on a
    second window before any claim.
- **Not recommended:** a kitchen-sink model of tracking, hustle, play-type or zone stats. Prior tests and
  this diagnostic give no reason to expect it to move the close comparison.

## What was not done, and why

- **No NBA.com collector.** There's no authorized access, and the task forbids undocumented endpoints and
  bypassing access controls.
- **No new feature in any model**, so no new version, no preregistration, and no prospective comparison.
  Phases 2-5 have nothing to evaluate.
- **No deploy, no VM change.**
- **Files:** this report, `nba_proj_diag.py` (the diagnostic), and `test_nba_proj_diag.py`.
