# proj-1.1 — runbook (shadow only)

Pre-registration: `NBA_PROJ11_PREREG.md`. Development results: `PROJ11_RESULTS.md`. Data rights: the
owner's decision, recorded in `NBA_STATS_FEASIBILITY.md`. proj-1.1 never replaces proj-1.0 on the page, and
nothing here is a pick. It is logged beside proj-1.0 at the same cutoff, under its own version
(`proj-1.1-dev:<config hash>`), and graded nightly.

## Pieces
| file | job | where |
|---|---|---|
| `nba_stats_fetch.py` | NBA.com families per game date (season logs for six of them), raw and compressed with fetch time, in `nba_stats_raw.sqlite` | Mac (history); VM (new dates, nightly) |
| `nba_lineups_poll.py` | the daily lineups file (Expected / Confirmed starters, Active / Inactive), stored on change with fetch time, in `nba_lineups.sqlite` | VM cron, every 5 min on game-day hours (live since 2026-10-26 23:09 UTC) |
| `nba_lineups_report.py` | at tip − 30: lineup status, starters right or not, minutes from confirmation to tip | anywhere |
| `nba_proj11_feat.py` | point-in-time family features (F0..F6) | — |
| `nba_proj11.py` | the residual ridge layer, the arms, the development run (`--features`, `--run`) | Mac |
| `nba_proj11_live.py` | `--write-config` (the candidate from the development run), `--refresh` (heavy), `--forecast` (light), `--prospective` (nightly grading) | VM |

## Live data flow (VM)
1. **Nightly, after the 10:30 UTC box-score fetch:** `nba_stats_fetch.py` stores the new dates.
2. **`--refresh`** runs on the same cron as proj-1.0's refresh, skipping when nothing changed. It produces:
   - proj-1.0's means for the slate;
   - feature state through yesterday;
   - the month's ridge weights (fit on rows before the month);
   - the analog pool around μ'.

   Output: `nba_proj11_cache.pkl`.
3. **`--forecast`** runs every 5 min. It reads the newest lineup snapshot and the newest official-report
   status *as seen at that moment*. A regular is out if he is listed Out or Doubtful, or Inactive in the
   lineup file. Starts come from the lineup file (Expected or Confirmed). With no lineup yet, a player
   gets his own start share.
   - It reads the board's main lines from `docs/nba_props.json` and logs `first` / `cutoff` rows to
     `nba_proj_log.sqlite`, closed at tip − 30.
   - The audit table `p11_inputs` records what F0 rested on.
4. **`--prospective docs/nba_proj11_score.json`** runs nightly after proj-1.0's grading:
   - graded n, log loss, CLV and calibration;
   - paired proj-1.1 − proj-1.0;
   - the pre-registered decision lines, which need 2,000 graded props, then 2,000 more to replicate.

## Deploy (only with the owner's OK)
1. **Code:** merge `nba-proj11` onto the VM's current deploy branch, then run `nba_vm_deploy.sh` from
   `~/nba-engine` at that commit. The script ships *.py only.
2. **One-time data copy:** `.projdata/nba_stats_raw.sqlite` → VM `~/nba-engine/nba_stats_raw.sqlite`.
   The deploy never copies data.
3. **Config:** `python3 nba_proj11_live.py --write-config` (from `PROJ11_RESULTS.json`; copy both files).
4. **Crons:**
   - `40 10 * * *` `nba_stats_fetch.py --workers 1` (new dates);
   - `12,42 * * * *` `flock -n /tmp/nba-proj11.lock nice python3 nba_proj11_live.py --refresh`;
   - `*/5 15-23,0-3 * * *` `nba_proj11_live.py --forecast`;
   - `25 11 * * *` `nba_proj11_live.py --prospective …/docs/nba_proj11_score.json`.
5. **Check:**
   - `--refresh` prints "projected N players (proj-1.1-dev:…)";
   - `--forecast` prints "logged N";
   - proj-1.0's forecast count is unchanged.
6. **Roll back:** delete those cron lines. proj-1.0 is unaffected (separate version rows, separate cache).

## Versions logged (shadow), as of 2026-10-27
| version | config | what it is |
|---|---|---|
| `proj-1.1-dev:9075eab3ef` | `nba_proj11_config.json.proj-1.1-dev` (kept on the VM) | the original F0. **Superseded** by amendment 1 (audit C1); its 78 logged rows stay |
| `proj-1.1.1:1cc04e3140` | `nba_proj11_config.json` | F0 with one "regulars out" rule for training and live |
| `proj-1.2:69e0f8a534` | `nba_proj12_config.json` (cache `nba_proj12_cache.pkl`) | proj-1.1.1 + T1, the frozen 2023-24 mean recalibration (`NBA_PROJ12_PREREG.md`) |

proj-1.2 runs the same jobs with `--config nba_proj12_config.json`. T4-live (`NBA_T4_LIVE_PREREG.md`)
grades DraftKings against FanDuel's fair price from the quote change logs: `nba_t4_live.py --grade
docs/nba_t4_score.json`, nightly, read-only.

## Limits
- **Historical F0 is an optimistic proxy.** The starters and absences come from the game itself. Live F0
  uses only what was visible before the cutoff. Where most lineups are still "Expected" at tip − 30 (as
  on 2026-10-26), live F0 is weaker than its backtest.
- **Stat corrections.** NBA.com values are as stored at fetch time, and later corrections rewrite them.
- **No tuning.** The candidate's families and λ are fixed by the development run. A change means a new
  version and a new pre-registration.
