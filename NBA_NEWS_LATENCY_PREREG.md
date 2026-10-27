# PRE-REGISTRATION: how fast FanDuel (and DraftKings) react to official injury-report news

Written 2026-10-27, before the measurement was run. Descriptive: no betting rule and no decision. It
locates a possible edge for a later, separate pre-registration.

## Data
- `nba_news.snapshots`: every official report since 2026-10-22, published every 15 minutes.
- `nba_lines.quotes`: the FanDuel and DraftKings change logs, plus `cycles` (each successful poll).
  - FanDuel is polled about every 10 minutes, plus an immediate fetch about 20–30 s after each new report
    (nba_watch).
  - DraftKings is polled about every 3 minutes.

Reaction time is measured on that grid. "Changed by the first poll after the report" means within that
poll's delay.

## News events
- A *regular*: averaged ≥ 20 minutes over his last ≤ 10 appearances before the date.
- An event: the first report P on which a regular's status for that game is Out or Doubtful, after an
  earlier report that day listed his team with him not Out or Doubtful (or not listed).
- A first listing is not news: the team must appear on an earlier report that day.
- Also: "cleared" events, Questionable on one report to Available on the next.

## Measures (per event, for the team's other players' props on each book)
- **Before:** the main line and its no-vig P(over) at the last observation before P.
- **Moved:** the main line changes, or the no-vig P(over) at the old main changes by ≥ 0.02.
- **Lag:** minutes from P to the first poll showing a move; also the share moved at the first poll after
  P, and the share that had moved in the 60 minutes before P (news that broke elsewhere first).
- **Control:** the same move rate for props of teams in the same games with no event in that window.
  The excess over control is the reaction.
- **The absent player's own props:** minutes from P until they are pulled.

## Then
The shadow flags are diagnosed against these timings: whether FanDuel had already moved when a flag was
logged, flag latency after the report, and CLV and ROI by those splits. Any rule that comes out of it
gets its own pre-registration and is judged forward.
