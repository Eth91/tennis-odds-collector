# PRE-REGISTRATION: T4-live, DraftKings against FanDuel's fair price (forward only)

Written 2026-10-27. **Only games tipping on or after 2026-10-28 count.** Research only: nothing is bet,
nothing is shown as a pick, and `nba_flags.LIVE_TIERS` stays empty.

## Why
T4 in `NBA_PROJ12_PREREG.md` bet DraftKings, BetMGM or Caesars at their T−30 price whenever FanDuel's no-vig
probability for that side, times the other book's decimal odds, was above 1.02. Over 2023-25 it returned
+1.44% [−0.55%, +3.38%] on 15,278 bets, with both seasons positive. That missed its pre-registered bar,
so it is not a finding.

The only honest next step is the *same* rule on data that did not exist when the rule was set. No
threshold, book, side or market is chosen from the historical result.

## Rule (identical to T4, two books)
- **Board:** the FanDuel and DraftKings boards rebuilt from `nba_lines.quotes` (the change log) as of
  tip − 30 min.
- **Candidates:** every player-game, market and line where FanDuel has a two-sided price and DraftKings
  has the same line.
- **Signal:** for each side S, if FanDuel's no-vig P(S) × DraftKings' decimal odds(S) − 1 > 0.02, record a
  signal on S at DraftKings' price.
- **Grading:** flat 1 unit; a DNP is void; a whole-line push returns 0.

## Decision
- **The bar:** ≥ 500 graded signals, and the ROI's lower 95% bound above 0 (date-clustered by ET date,
  4,000 reps).
- **Below 500 signals:** "not enough prospective evidence".
- **One look:** the decision is read once, at the first nightly grading after the 500th signal. The
  nightly running numbers are information only. A second, replication window of the next 500 signals
  must also have ROI > 0 before anything is called an edge.

**Secondary, information only:**
- ROI by side and by market;
- CLV: whether FanDuel's last pre-tip no-vig price for S rose from T−30;
- DraftKings' lag: the time between a FanDuel move and DraftKings' matching move.

## Implementation
`nba_t4_live.py --grade OUT_JSON` rebuilds the boards from the change log and grades against
`nba_matchup` box scores. It is nightly on the VM, read-only.
