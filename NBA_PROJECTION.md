# NBA projection engine — how it works, what it uses, how it is checked

Research only. The page shows these as **model estimates**, apart from book prices, never as picks or
bets. The pre-registration (decision rules written before any held-out run) is `NBA_PROJECTION_PREREG.md`;
the results are in `PROJECTION_RESULTS.md`.

## Modules
| file | role | where it runs |
|---|---|---|
| `nba_proj_data.py` | box scores → one row per appearance (DNPs apart), opponent, home/away, team possessions; book prices (historical −29 min snapshot; 2026-27 change log rebuilt at the cutoff); player-name matching | both |
| `nba_project.py` | B1/B2/M1 means (one walk-forward pass), the analog-ensemble distribution, exact over/under/push, the frozen config, the live slate path (`for_payload`), the availability table, the prospective forecast log | both |
| `nba_proj_eval.py` | tuning on 2023-24, the pre-registered evaluation (`--final`), the nightly grading of the forecast log (`--prospective`) | Mac (`--tune`, `--final`); VM (`--prospective`) |
| `nba_research.py` | calls `nba_project.for_payload` in the 2-minute build; adds `proj` to each prop, `proj_players`, `proj_meta` to `nba_props.json` | VM |
| `nba_research_ui.py` | the player page's Model Projection card, the MODEL column of the alt-line ladder, "proj" on list rows, the model status and scorecard | VM (static page) |

Flow on the VM: cron (every 2 min) → `nba_research.py` → `nba_project.for_payload` (cached per day:
recomputed only when the box-score stores or the slate change) → `docs/nba_props.json` → the page.
Each build also writes forecasts to `nba_proj_log.sqlite` (the first and the last before tip − 30 min).
Nightly at 11:15 UTC, `nba_proj_eval.py --prospective` grades them into `docs/nba_proj_score.json`.
`dashboard.py` is not touched.

## The prediction
- Target: `(min, pts, reb, ast, fg3m, stl, blk, tov)` for a player who **appears**. Books void a DNP.
  P(appears) is shown separately, from the official status (2026-27 reports, with the n behind it).
- Cutoff: tip − 30 min. The only box scores used are from **earlier dates**.
- Output per prop: mean, median, 10th/90th percentiles, the full integer pmf, and P(over), P(under)
  and P(push) at any line (computed on the page from the pmf). Also the model + market blend where a
  book prices both sides of that line.
- Combos are sums of components **within each joint draw** (one analog = one draw of all 8 stats).

## Feature registry
| feature | definition | source | coverage | point-in-time rule | missing → |
|---|---|---|---|---|---|
| minutes EWMA | exponentially weighted minutes over his appearances, half-life `h_m`, shrunk to the 60-appearance EWMA by `k_m` | box scores | 2022-23 → | appearances on earlier dates | league default 12 min (debut) |
| per-minute rates | EWMA sums (half-life `h_r`) of each count over minutes, pooled toward the group's league rate with `k_<stat>` minutes | box scores | 2022-23 → | earlier dates | the group's league rate |
| group league rate | per-minute rate of all G / F / C players, this season to date + last season | box scores + positions | 2022-23 → | earlier dates | built-in defaults (first day of data only) |
| opponent factor | what the opponent allowed to his group per possession ÷ league, this season blended with last season by 15 games, ^`a_opp` | box scores, team possessions | 2022-23 → | the opponent's earlier games | 1.0 |
| pace factor | mean of both teams' possessions per game ÷ league (blended the same way), ^`a_pace` | team possessions (FGA + .44 FTA − OREB + TOV) | 2022-23 → | earlier games | 1.0 |
| home / away | multipliers measured on 2022-23 only, frozen | team_games (profiles, matchup) | 2022-23 → | schedule (known) | none applied |
| back-to-back | played the day before (his last appearance); multipliers measured on 2022-23 only, frozen | dates | all | his earlier appearances | not b2b |
| history depth, rest | appearances so far; days since his last one (capped at 30) | dates | all | earlier dates | 0 / 30 |
| position group | the player index's position, first letter's family (G/F/C) | `positions` (static) | all players in logs | static label (a stated limit) | F |
| market price (blend only) | FanDuel's de-vigged probability at that line (DraftKings' when FanDuel has none) | odds hist (−29 min) / change log | 2023-24, 2024-25; 2026-10-22 → | at or before the cutoff | the blend is not shown |
| official status (availability only) | the latest report status before the cutoff | `nba_news.snapshots` | 2026-10-22 → | published before the cutoff | "not on the report" |

**Not used, and why**: injuries and teammate absences inside the projection (no point-in-time history
before 2026-10-22, so no way to test them historically). Starting lineups (never collected before
tip). Travel, referees, play types (not validated).

## Monitoring (in `proj_meta`, shown on the page)
Version and config hash, tuned-on season, box scores "through" date and **stale** (more than 3 days
before the slate), coverage (props projected, thin-history count), the availability table with its n,
`error` (on any failure the page shows no projection, never a stand-in number), and the number of
forecasts logged. Nightly: realized log loss for the model, the blend and the close, CLV, and n.

## Known limits
Historical minutes are whole numbers. Positions are static. The historical market (−29 min) knows the
injuries and lineups the historical model does not. Steals and blocks have historical lines only.
Turnovers have no line anywhere. Regular season only.
