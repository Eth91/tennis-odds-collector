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

---

# AMENDMENT 3 — the absence count across the season boundary (2026-10-23, before any flag closed)

Committed after 19 shadow flags existed for 2026-10-23's games but **before any of them closed,
was graded, or had an outcome** — so no result could have informed it.

**The defect.** The registration reset the absence streak at the season boundary, to stop stars who
rested the last games of April (Mitchell: last app 04-08, sat 04-10 and 04-12) reading as
"absence game 3" in October. It reset **every** streak: on 2026-10-23 all 51 players ruled Out
counted as absence game 1-2, including players out since February whom the book priced long ago.

**The corrected rule** (`nba_flags.absence_index`): games missed at the end of the previous season
carry over only when they are a real streak — more than `MAX_ABSENCE_GAME` (2). One or two missed
games at season's end (rest) still reset; a longer streak continues into the new season. Effect on
2026-10-23: 11 of the 51 Outs are long-term absences and are no longer triggers.

**Flags already logged.** Each of the 19 is re-checked under the corrected rule; a flag whose trigger
fails it gets `void_reason = 'amend3: …'` and is excluded from every cell (reported as a count). The
corrected rule is applied identically to every flag before and after this amendment.

---

# AMENDMENT 4 — the apparatus moves to the always-on VM; FanDuel becomes the primary book (2026-10-23, before any flag closed)

Committed at 09:2x UTC on 2026-10-23. Shadow flags exist for that night's games, but **none has
closed, been graded, or had an outcome**. The first tip is 23:00 UTC, so no result could have
informed this.

**Why.** The registration's first known limit, "the Mac must be awake", turned out to be the binding
one. Night one captured 1 of 2 closes, with a median capture lag of 348 s, because the Mac slept. On
2026-10-23 every input was probed from the Oracle VM, 3× each with a played game's file:
- reachable with curl_cffi Chrome impersonation: the official injury PDF, cdn.nba.com (schedule,
  scoreboard, box scores), stats.nba.com, FanDuel, ESPN;
- blocked by IP: **DraftKings only.**

The note that cdn.nba.com blocked the VM was a misreading. cdn.nba.com answers 403 for a game file that
does not exist, the same as a block.

**The change.**
1. **Apparatus:** the report poller, the per-minute trigger, the FanDuel collector, the flag pass, close
   capture and grading run on the VM. The X news layer is already there. DraftKings is collected
   wherever it can be reached (a GitHub Actions runner, which DraftKings serves; or the Mac when awake)
   and fed to the VM's quote log. The cutover time is recorded below as an operational note.
2. **Primary metric is FanDuel-only.**
   - The flagged line and price are FanDuel's main rung at the flag's `logged_at`: the two-sided rung
     whose over is nearest even money, rebuilt from the change log exactly as the close is.
   - The close is FanDuel's main rung at tip.
   - Beat-the-close, line move, as-flagged ROI vs at-close ROI and latency are computed on those, with
     the **same decision lines, thresholds and minimum counts** (≥ 100 closed flags in ≥ 30 games),
     counted on flags where FanDuel was two-sided at both moments.
3. **The registered two-book measure** (best over of FanDuel and DraftKings) is kept and reported as a
   **secondary cell**. It no longer decides. When DraftKings was not collected, it reduces to FanDuel.

**Why FanDuel and not both.** A primary that depends on DraftKings depends on whether a second machine
happened to be reachable. One book captured every night is a cleaner yardstick than two books captured
on some nights. FanDuel is also the book the WNBA record was graded on.

**Unchanged:** the universe, tiers, triggers (amendments 1–3), one opportunity per (tier, player,
stat, game), clustering by game, and the WNBA reference point. The flag engine still prices on the best
of whatever books it holds at that moment. Only the yardstick changes.

**Flags logged before the cutover** (on the Mac) move to the VM with the shadow DB, keep their records,
and are scored the same way.

**Operational note — the cutover (not a rule change).** Amendment 4 was committed at 09:17:46 UTC on
2026-10-23 (commit 54909539d7; the "09:2x" in its first line was an estimate). The Mac's nba-cycle and
nba-watch stopped at **09:30 UTC**. Live data was copied with SQLite's backup API: 21 shadow flags, 7 of
them void, and 137,624 quotes. The VM's cron took over at **09:34:43 UTC**. Every flag has `logged_at`
before 09:30 (Mac) or after 09:34 (VM). The Mac now runs only `nba_dk_push.sh` (DraftKings snapshot,
every 3 min). No game tipped during the gap.

---

# AMENDMENT 5 — how fast FanDuel reacts to the news (2026-10-23, information only, before any reaction data is examined)

Committed before any reaction time has been computed or looked at. The change log has existed since
2026-10-22 at 10-minute resolution. Nobody has analysed it for this question.

**Why.** The speed test asks whether a flag's price beats the close. It takes ~100 closed flags to
decide. A more direct question answers sooner: **after the news, how long does FanDuel take to move the
affected players' lines?**
- Within a minute or two: no manual bettor can catch it, and a speed edge would need automation.
- Ten minutes or more: there is a window.

**The apparatus change (data only).** For FOLLOW_MIN = 20 minutes after every trigger (official report
or news), `nba_watch` refreshes FanDuel every minute. The 10-minute cycle is too coarse to time a
reaction. Flags, tiers, books and the speed test's yardstick are unchanged. The near-tip close capture
now times its 2-minute refresh from FanDuel's own last fetch.

**What is measured** (`nba_reaction.py`):
- **Unit:** (trigger, player, stat) for every player on the absent player's team in that game. Team
  comes from the season player index. The player must have a FanDuel two-sided main rung at the news
  time T0.
- **T0:** the official report's `published_at` for report triggers; the news item's time for news
  triggers.
- **Reaction:** the first change in FanDuel's main rung after T0, rebuilt from the change log exactly as
  nba_clv rebuilds a close.
  - LINE (primary): the main line number changes.
  - PRICE: the over price on the same line moves by ≥ 0.03 decimal.
  - Reported as minutes after T0, with the gap since the previous FanDuel poll (the resolution).
- **Window:** T0 to the earlier of T0 + 60 min and tip. No line move in it = held.
- **Pre-moved:** the main line at T0 differs from the main line 30 min before T0. The book had the news
  before the official report.
- **Control:** at the same T0, players in games with no trigger within ±60 min. This is the background
  rate of line moves.
- The **flagged opportunities** (shadow flags created by that trigger) are reported as their own cell.

**Reading rules, fixed now.** Read once at ≥ 20 triggers that each have at least one measured player-stat.
1. **FAST:** among affected lines that moved within 60 min, at least half moved within 2 min, AND the
   affected 60-min move rate is ≥ 2× the control's. The book reacts faster than a person can bet;
   any speed edge needs automation.
2. **WINDOW:** the median first move among affected movers is ≥ 10 min, and the affected rate is ≥ 2×
   the control's. A minutes-long window exists.
3. **NO REACTION:** the affected rate is < 2× the control's. Lines do not respond to this news
   beyond background churn, so the flag thesis has no market reaction to beat.
4. Otherwise, **a window of a few minutes.**

Separately: if ≥ 50% of affected lines were **pre-moved**, the official report is too slow a news clock,
and earlier sources (X) carry whatever speed edge exists.

**None of this changes the speed test's verdict lines** (the amendment 4 yardstick and the original
PROMOTE / EXTEND / KILL). It is information about the mechanism. Nothing bets.
