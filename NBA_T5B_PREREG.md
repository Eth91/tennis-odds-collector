# PRE-REGISTRATION: T5b, T5 with three selection filters, each aimed at a mechanism (forward only)

Written 2026-10-27, after the T5 audit (`nba_t5_audit.py`, games 2026-10-22..25) and **before these filters
were applied to any data.** Research only: nothing is bet, nothing is shown as a pick, and
`nba_flags.LIVE_TIERS` stays empty. T5 itself keeps running unchanged as registered.

## What the audit found (253 development signals; post hoc, a hypothesis source only)
- **ROI −9.5%, CLV −1.1 points.**
- **Not stale FanDuel prices.** FanDuel's price was under 5 minutes old for 202 signals. Its next poll
  moved toward DraftKings in only 9.
- **FanDuel's own early moves reverted.** 152 signals fired because FanDuel moved toward the under while
  DraftKings held. By tip, FanDuel's no-vig under probability had fallen back: CLV −1.3 points, ROI −11.6%.
- **The player's own status matters.** All 5 signals whose player's own report status changed after the
  signal lost.
- **The model helps CLV a little.** When proj-1.1.1's P(under) at the line was above FanDuel's, CLV was −0.6
  points, against −1.7 otherwise. ROI did not separate.
- **Earlier was less bad:** 6 h+ −1.7%, 2–6 h −19%, under 2 h −14%.

## The filters (all three apply; each targets one mechanism, none is tuned)
A T5 trigger becomes a T5b signal only if all three hold:
1. **Confirmation**, against reverting noise. At FanDuel's next successful poll after the trigger
   (status ok, partial or game), FanDuel's no-vig P(under at L) × DraftKings' under odds at that moment − 1
   must still be above 0.02. The signal is placed at that moment, at DraftKings' price then.
2. **Clean status**, against unresolved minutes. The player is not listed Questionable, Doubtful or Probable
   in the newest official report published before the signal.
3. **The model agrees**, a second opinion. The newest proj-1.2 forecast made before the signal
   (`forecast_pmf`) gives P(under at L | no push) above FanDuel's no-vig P(under at L). If no proj-1.2
   forecast exists before the signal, there is no signal.

Everything else is T5's rule:
- one signal per player-game and market;
- flat 1 unit;
- a DNP is void and a push returns 0;
- the board is cut off at tip − 30.

## Decision
- **Confirmatory sample:** games tipping on or after **2026-10-28**, the same as T5.
- **Bar:** at least 500 graded signals with the ROI's lower 95% bound above 0, read once; then 500 more
  with ROI > 0.
- **Below 500:** "not enough prospective evidence".

**Reported with it, no decision:**
- ROI and CLV for signals 6 h+ before tip;
- each filter's own effect, meaning the signals that pass T5 but fail each single filter.

**In-sample check:** what the filters would have done on 2026-10-22..25 is reported once and labeled
in-sample, not evidence. That window chose them.
