# The replay tool and the side-by-side test

Rules and bars: `NBA_SXS_PREREG.md`. Code: `nba_replay.py` (the replay), `nba_sxs_rules.py` (the rules and their
registry), `nba_sxs.py` (the nightly runner). Scoreboard: `docs/nba_sxs_score.json`, nightly at 12:27 UTC.

## What it fixes
Our backtests knew who sat from the box score, bet at one archived tip snapshot, and reused two seasons tuned
on 30+ times. The replay reads only what the logs held at each moment:
- each book's board at its latest poll;
- the injury reports published so far;
- box scores from before the date, of games final by then, and tracking stored by then (amendment 8).

The nightly run executes the same code over each finished day, so a rule's replay and its live record are the
same thing.

## Testing a new idea
1. Write a rule class in `nba_sxs_rules.py` (or any module), using only the `View` it is handed:
   - `on_obs(v, book, seen)`: a book just observed these games;
   - `on_report(v, t, rows, prev, seen_before)`: an injury report was published;
   - `on_tick(v, gid, minutes)`: tip − 30 or tip − 5.

   It returns signals: game, player, market, side, line, book, price.
   A rule module that reads box scores or tracking from its own store paths lists them in `PIT_STORES`
   (as `nba_sxs_rules` does). The replay then points them at copies as of each moment (amendment 8).
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

## Amendment 8: what the look-ahead fix changed (measured 2026-10-28, after the code)
Replayed 2026-10-22..27 on read-only copies of the VM's stores, old replay vs new. Fingerprints are identical.
- **Box scores (games final by t): no signal changed.** Of 19 back-to-back team spots (10-24..27), every prop was
  first quoted at least an hour after the previous game's tip + 3 h. The look-ahead had not happened yet.
- **Tracking (dates stored by t): 71 graded signals changed, all in the development record, none forward.**
  - Tracking landed 2–3 days after the games: 10-20 and 10-21 on 10-24 at 08:01 UTC, 10-23 and 10-24 on 10-26 at
    11:20, 10-25 on 10-27 at 11:20. The old replay read all of them at openers posted before they were stored.
  - RATIO_PA: 11 removed, 10 added, 2 different. RATIO_RC: 21, 19, 1. RATIO_PA28: 2 removed, 8 added.
  - Development ROI moved from +8.3% to −2.8% (RATIO_PA), from +5.0% to −11.6% (RATIO_RC), and from +26.1% (4
    signals) to +6.0% (9) for RATIO_PA28. These are small development records, not verdicts.
- **Every other rule:** identical.
- **Cost:** 16 s instead of 13 s for the six days on the Mac, with peak memory 456 MB instead of 441 MB.
