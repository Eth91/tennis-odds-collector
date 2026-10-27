# PRE-REGISTRATION: T5, early unders at DraftKings against FanDuel's fair price (forward only)

Written 2026-10-27, **before the rule has been run on any data.** Research only: nothing is bet, nothing is
shown as a pick, and `nba_flags.LIVE_TIERS` stays empty.

## Where the idea comes from (all post hoc, which is why only new games decide)
The owner proposed combining three leads:
1. **Bet early.** The historical odds only have tip − 30, FanDuel's sharpest price. Earlier prices are
   untested.
2. **Unders.** FanDuel's no-vig over probability ran +1.7 / +0.6 points above the realized over rate
   (2023-24 / 2024-25). In T4's historical run, its unders returned +3.0% and its overs −0.9%.
3. **Books that copy FanDuel.** T4 (DraftKings, BetMGM or Caesars against FanDuel's fair price) returned
   +1.44% [−0.55%, +3.38%] and failed its pre-registered bar.

Points 2 and 3 were picked after seeing those results, so no historical number can confirm T5.

## Rule
For each player-game and market on the live boards (`nba_lines.quotes`, FanDuel and DraftKings), replay the
change log from the first quote until tip − 30 min.
- **Trigger:** the first moment at which, at the same line L, FanDuel has a two-sided price and DraftKings
  has an under price with
  `(1 − FanDuel no-vig P(over at L)) × DraftKings under decimal odds − 1 > 0.02`.
  That moment produces one signal on the under at DraftKings' price.
- **At most one signal per player-game and market** (the first one), so alt lines are never counted twice.
- **Grading:** flat 1 unit; a DNP is void; a whole-line push returns 0.

## Decision
- **Confirmatory sample:** games tipping on or after **2026-10-28** only.
- **Bar:** at least 500 graded signals, and the ROI's lower 95% bound above 0 (date-clustered by ET date,
  4,000 reps). The decision is read once, at the first nightly grading after the 500th signal.
- **Replication:** the next 500 signals must also have ROI > 0 before anything is called an edge.
- **Below 500 signals:** "not enough prospective evidence".

**Reported, no decision:**
- ROI by how early the signal came: more than 6 h, 2–6 h, and under 2 h before tip;
- CLV, the change in FanDuel's no-vig P(under) at L from the signal to its last pre-tip price;
- ROI by market.

**Development look:** games from 2026-10-22 to 2026-10-27, already played, are graded once and reported
as *development, not evidence*. No setting is changed after it.

## Limits written down now
- Early prices come with low limits, and books limit accounts that win. A real edge here would be small
  in size.
- **Sampling delay:** DraftKings is sampled about every 3 minutes (Mac push) and FanDuel about every 10
  (VM cycle), so "the first moment" is the first sample, not the first posting.

## Development look (2026-10-27, games 2026-10-22..25). Information only; nothing changed after it
- **T5:** 255 graded signals. ROI −9.2% [−16.3%, +13.2%].
  - By timing: 6 h+ −2.4% (n 123), 2–6 h −18.4% (n 79), under 2 h −11.4% (n 53).
  - **CLV −1.05 points**, positive on only 25% of signals. FanDuel's no-vig under probability usually
    *fell* between the signal and tip, so FanDuel's early price was a poor reference for "fair".
  - Median signal time: 5.7 h before tip.
- **T4 on the same window, for comparison:** 48 signals, ROI +1.9% [−23%, +12%], CLV −0.3 points.

Four nights cannot decide either test. The rule stands as registered, and the confirmatory sample starts
2026-10-28.
