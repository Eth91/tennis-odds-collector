# The replay tool and the side-by-side test

Rules and bars: `NBA_SXS_PREREG.md`. Code: `nba_replay.py` (the replay), `nba_sxs_rules.py` (the rules and their
registry), `nba_sxs.py` (the nightly runner). Scoreboard: `docs/nba_sxs_score.json`, nightly at 12:27 UTC.

## What it fixes
Our backtests knew who sat from the box score, bet at one archived tip snapshot, and reused two seasons tuned
on 30+ times. The replay reads only what the logs held at each moment:
- each book's board at its latest poll;
- the injury reports published so far;
- box scores from before the date.

The nightly run executes the same code over each finished day, so a rule's replay and its live record are the
same thing.

## Testing a new idea
1. Write a rule class in `nba_sxs_rules.py` (or any module), using only the `View` it is handed:
   - `on_obs(v, book, seen)`: a book just observed these games;
   - `on_report(v, t, rows, prev, seen_before)`: an injury report was published;
   - `on_tick(v, gid, minutes)`: tip − 30 or tip − 5.

   It returns signals: game, player, market, side, line, book, price.
2. Replay it for a development record:
   `python3 nba_replay.py --rule nba_sxs_rules:MY_RULE --from 2026-10-22 --to 2026-11-15`.
3. To make it count, pre-register it in `NBA_SXS_PREREG.md` (an amendment). Add it to `RULES` and add its
   fingerprint and registration time to `REGISTRY`. Only signals after that time are forward.
4. Changing a registered rule changes its fingerprint. The tests fail until it is registered again, and its
   forward record restarts.

## Development record (replayed 2026-10-22..25, before registration; not verdicts)

| rule | signals | CLV (EV at FanDuel's close) | ROI |
|---|---|---|---|
| NULL_TIP30 (control) | 965 | −5.9% | −5.0% (478-487) |
| NEWS_FD | 254 | −5.4% | −12.1% (118-136) |
| NEWS_DK | 127 | −6.7% | +3.0% (70-57) |
| DK_LAGS_FD | 424 | +2.9% | −4.2% (195-228) |
| T4_TIP30 | 48 | +3.5% | +1.9% (23-25) |
| ENGINE_CARD | 8 | −10.9% (2 of 8 with a close) | −8.3% (4-4) |
| S1 | 0 | | |
| DEPTH_NEXT (amendment 1) | 39 | −3.1% (26 with a close) | +5.8% (22-17) |
| DEPTH_NEXT_TIP30 | 129 | −5.7% | +8.5% (74-55) |
| NEW_STARTER (one night of lineups) | 14 | −4.6% | +3.1% (8-6) |
| LOST_START (one night) | 8 | −7.4% | −49.8% (2-6) |

The volume rules (amendment 1, the user's "volume is king") replay from the same logs. Their lineup-based rules
have only one night of lineups so far. Forward, they all start at 2026-10-27 12:00 UTC.

**The control reads about the vig, as it should.** Two rules are positive on CLV, both "DraftKings is slower than
FanDuel" ideas: DK_LAGS_FD and T4_TIP30. Four nights tell us nothing about profit. The forward record starts
with games after 2026-10-27 12:00 UTC.
