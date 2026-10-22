# PRE-REGISTRATION — the NBA speed test (forward, from 2026-10-22)

Written and committed **before any forward flag exists**. 2026-10-22.

## Why this test, and why it is different from the three before it
Three NBA tests have run on real lines — the margin rule, cold-start, and the WNBA pricing
machinery. **All three priced bets at the close, and none beat it** (best: −3.46%). But the WNBA's
own record says its money is partly SPEED. From `wnba_clv.sqlite`, forward since the 7/31 freeze:
the record's bets **beat the closing line 67% of the time** (28 of 42 with a close; the line moved
toward the bet 19 times, away 2), and **bought at the close the same bets earn +11.5% instead of
+20.2%**. A closing-price backtest cannot see that half. The NBA historical odds are tip
snapshots only, so the only way to measure it is forward. This is that measurement.

## The apparatus (all Mac-side, `~/nba-engine`)
- **News clock** — `nba_injury_report.py`: the league's official injury report, published every
  15 minutes; each ruling's first-published time is stored (`nba_news.sqlite`).
- **Trigger** — `nba_watch.py`, every minute: polls through each publication, diffs against the
  previous report, and on a **fresh Out for tonight's game** refreshes both books and runs the
  flag pass immediately (measured end to end on a synthetic report: 10 s from publication to flag).
- **Prices** — `nba_lines.py`: FanDuel + DraftKings; every move and pull is logged; in the last
  35 min before a tip the board refreshes every 2 min, so the close is minutes old.
- **Flags** — `nba_flags.py`, shadow only (`LIVE_TIERS` empty). A flag's price is the first-seen
  board price; it records the news time and the beneficiary's person id.
- **Scoreboard** — `nba_clv.py`, the canonical query for this test.

## Universe
- Trigger X: ruled **Out** on the official report for a game **tonight** (ET date), in **absence
  game 1 or 2 of the current season** (the streak resets at the season boundary — a deliberate
  departure from the pooled count the backtests used, which made every star who rested in April
  invisible in October), ≥ 28 min trailing-10 for this franchise (the tested star rule).
- Tiers, decided separately: **`priced`** (the WNBA pricing machinery, `nba_pricing` — PRIMARY),
  `wowy` (the margin rule), `cold` (cold-start). Base rung, overs only; `priced` uses the WNBA
  card's sticky top-2-disjoint per team-game.
- A flag counts once it has a reconstructed close; the result counts once graded.

## Metrics (per tier, from `nba_clv.py`)
1. **Beat-the-close rate** — the closing main line rose above the flagged line, or held and its best
   over shortened. 95% CI by bootstrap **resampling games** (flags in one game share one news
   event), 4,000 reps, seed 7.
2. Mean line move (closing − flagged).
3. As-flagged ROI vs at-the-close ROI on graded flags, flat 1 unit.
4. Latency: flag time − news time (median).

## Decision lines — tier `priced` (wowy and cold use the same lines, reported, not promoted first)
Evaluated **once**, at ≥ 100 closed flags in ≥ 30 games, or at the end of the regular season,
whichever comes first. Interim looks are allowed and may be reported, but **decide nothing**.

| verdict | condition | consequence |
|---|---|---|
| **PROMOTE** | beat-close CI lower bound **> 50%**, AND as-flagged ROI > 0, AND as-flagged ROI > at-close ROI | add the tier to `LIVE_TIERS` (paper bets) and turn on pings; real money still needs the user's call |
| **EXTEND** | beat-close point estimate > 50% but the CI includes 50% | continue to ≥ 250 closed flags, then decide once more with the same lines |
| **KILL** | beat-close rate ≤ 50% at the decision point, or the CI still includes 50% at ≥ 250 | the speed thesis is not supported for this tier; it stays shadow |

The WNBA reference point is 67% (n=42); nothing here is tuned to reach it.

## Known limits, stated now
- The Mac must be awake; gaps show in `nba_lines.cycles`. A flag whose game has no quote near tip
  has no close and is not counted.
- The close is the last FanDuel/DraftKings quote before tip — 2 minutes old at best, up to ten if
  the hot window missed.
- The trigger covers tonight's games only. Rulings published today for **tomorrow's** games are also
  news (they appear in the report from the previous afternoon) — a separate extension, not in this test.
- The official report is the only injury source. Beat reporters often break news before the 15-minute
  mark, so a book can move BEFORE the report — which makes this test CONSERVATIVE: a flag that still
  beats the close did so despite arriving after the fastest news. An earlier news layer could only
  make the engine faster.
- Flag prices are each board's best over across FanDuel and DraftKings at that moment.
