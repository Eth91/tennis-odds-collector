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

---

# AMENDMENT 1 — tomorrow's-game rulings (2026-10-22, before any forward flag exists)

Committed before the code that produces these flags runs, and before any shadow flag of any kind
exists. The registration above is unchanged; this adds a second cell and one counting rule.

**What changes.** The trigger now also fires on a fresh Out for **tomorrow's** game. The league
publishes the next day's rulings the afternoon before, which is news the book must price too, and
the closing line is then a day away. Such flags carry `horizon = 1` (game-day flags `horizon = 0`).
For a tomorrow game, a player also ruled Out for **tonight** (his team playing tonight) counts that
game as a missed one: tonight's box is not final yet, so it is not in the appearance data.

**The primary test is untouched**: tier `priced`, `horizon = 0`, with every line, metric and
decision rule above. Horizon-1 flags are **never pooled into it**.

**The horizon-1 cell** is decided separately, on the same metric (beat-the-close rate, CI resampling
games), the same three verdicts (PROMOTE / EXTEND / KILL), and the same decision point (≥ 100 closed
opportunities in ≥ 30 games, or the end of the regular season, whichever first).

**One opportunity per (tier, player, stat, game) — its earliest flag.** This rule is new, and it
applies to both cells identically. A day-before flag and a game-day re-flag of the same player-stat
at a moved line are one piece of news, not two bets; counting both would double-count exactly the
cases where the line moved. An opportunity first flagged at horizon 1 belongs to the horizon-1 cell
even if re-flagged on game day, so the primary cell holds only news that broke on game day.

**Known limits specific to horizon 1.** Fewer props are posted the day before (DraftKings in
particular posts later), so more candidates have no line and the cell will fill more slowly. A day
of market movement also means more noise per flag: the cell can show a larger move in either
direction, and needs the same sample bar, not a smaller one.

---

# AMENDMENT 2 — a news layer ahead of the official report (2026-10-22, before any forward flag)

Committed before the code that lets news trigger a flag runs, and before any shadow flag exists.
The registration and amendment 1 are unchanged; this adds a second trigger source.

**What changes.** Besides the official report, an Out can now be **originated by news**
(`nba_news_watch.py`: RotoWire's wire and Bluesky search today; an X reader that stays benched until
the user configures it). News is **add-only**: it can add an absence before the report lists it, it
never clears an official Out, and an official report published after the news item that lists the
player with any non-Out status for that game withdraws the news Out from then on. Every flag
records `trigger_src` — `report`, or `news:<source>` when news came first — and `news_at` is the
earliest time the absence was public to us.

**The confirmation rule (what keeps parser errors out of the verdicts).** A news-originated
opportunity counts in its horizon cell **only if an official report published before tip lists that
player Out for that game.** Confirmed, it keeps its earlier flag time and price — that is the speed
the layer exists to buy. Unconfirmed (the player played, or the item was misread), it goes to an
`unconfirmed news` audit cell: reported, never pooled into any verdict. Report-originated
opportunities are unaffected.

**What is measured about the layer itself** (`nba_news_watch.py --journal`, information only): per
source, the lead of each news Out over the league's first published Out for the same player-game,
and the unconfirmed rate. Measured on day one, RotoWire's injury items cited the official report's
PDF as their own source — downstream of it — so a lead is not assumed for any source.

**Primary test**: unchanged — tier `priced`, horizon 0, same lines — now over report-originated and
confirmed news-originated opportunities alike, i.e. the engine as it actually runs.
