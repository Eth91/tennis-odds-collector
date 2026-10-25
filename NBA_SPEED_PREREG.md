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

**Amendment 5, clarification (2026-10-23, before any reaction time was computed).** Per-minute follow
polling went live on the VM at **2026-10-23T20:13:30 UTC**. Earlier triggers were seen only through the 10-minute
cycle, which cannot see a move inside 2 minutes. So **only triggers detected at or after 2026-10-23T20:13:30 count
toward the 20 and the reading rules.** Earlier ones are listed, marked coarse, and excluded.

---

# AMENDMENT 6 — a with/without split must come from the beneficiary's current team (2026-10-24)

**The defect.** The wowy tier reads `nba_wowy.pairs` by (absent player, beneficiary) only. It checks
that the beneficiary is on the absent player's team tonight, but not that the split was **measured on
that team**. On 2026-10-23, Al Horford was flagged at Golden State from a split measured in 2 Boston
games without Kristaps Porziņģis. Both have since moved to Golden State, so that is a different
rotation and a different role.

The registered universe is `nba_pricing_realline.walk()`, which every backtest used. It measures splits
inside one franchise's games, so these flags were never of the registered type. The **priced** tier
(the decision tier) already measures its split live on the current franchise and is unaffected.

**The fix.**
- wowy uses only pairs whose `team` is the current team.
- For the cold tier, "has a prior split" (the rule that keeps a beneficiary out of the cold tier) also
  means a split on the current team. A beneficiary whose only split is from a former team is
  cold-eligible, as the cold-start registration defines.

**Flags already logged.** Every wowy flag is re-checked under the corrected rule, past and future. A flag
whose split came from another team gets `void_reason = 'amend6: …'` and is excluded from every cell,
counted as void. This is the same mechanism as amendment 3.

**Disclosure — unlike amendment 3, outcomes are known.** The defect was identified in writing *before*
tip on 2026-10-23: the pre-game review listed Horford's Boston split as a weak spot. But it is codified
here after those games were graded. The affected opportunities are all Horford, 2026-10-23:
- PRA o13.5 — loss
- PTS o6.5 — loss
- REB o3.5 — win
- FD beat the close on none of the three.

The void is mechanical and applies the same rule to every flag. But it moves that night's numbers in the
model's favour, so the scoreboard is recorded here before and after.

**Before** (2026-10-24 06:39 UTC), wowy/h0:
- FD yardstick: 14 opportunities closed, 12 with an FD close, beat close 25.0% (3/12), as flagged
  +49.7% vs at close +39.4% (12 graded).
- FD+DK yardstick: beat 28.6% (4/14), as flagged +28.6%.
- Priced and cold are unaffected.

**Applied 2026-10-24 07:22 UTC** (`nba_flags.py --amend6`, under the cycle lock). It voided exactly the 7 Horford
flag rows: 3 opportunities and their re-flags. A second run voided 0, so it is idempotent. **After**, wowy/h0:
- FD yardstick: 11 closed, 10 with an FD close, beat close 30.0% (3/10), as flagged +63.7% vs at close
  +49.1%.
- FD+DK yardstick: beat 36.4% (4/11), as flagged +49.3%.

Priced and cold are unchanged. Voided flags excluded from every cell: 14 (7 under amendment 3, 7 under
amendment 6). The decision tier (priced) is untouched by this amendment, and one night decides nothing.

---

# AMENDMENT 7 — the wowy tier is computed live, with the backtest's formula (2026-10-24)

**The defect.** The wowy tier read its numbers from `nba_wowy.sqlite`, built at the end of last season,
and nothing rebuilt it:
- `baselines.last_date` ≤ 2026-04-12, and 0 of 614 rows contain a 2026-27 game;
- on 2026-10-24, 130 of 334 players' stored minutes were ≥ 6 off this season's, 50 were ≥ 10 off, and
  107 had changed teams;
- flagged examples: Jrue Holiday projected on 31.4 min (this season 20.6, 26.5); Toumani Camara on 33.3
  (22.6, 27.3).

The registered wowy rule is the margin rule (`nba_pricing_realline.collect`'s margin rows, the code the
margin test ran). It recomputes from each player's games up to the bet date, so the live tier was not the
registered tier. Priced and cold already compute live and are unaffected.

**The fix — wowy computed live from `apps`.** `apps` is the same 400-day pool plus this season's box
scores that priced and cold use. The backtest's formulas are applied exactly, team-scoped:
- X: ≥ 10 appearances for this franchise and ≥ 28 min trailing-10 (as priced). B: on X's team tonight,
  not Out, ≥ 5 appearances for this franchise.
- Since X's first appearance for the franchise in the pool:
  - b_out = B's games X missed, b_in = B's games with X;
  - require ≥ 2 and ≥ 3.
- base_min = B's mean minutes over his last 10 franchise games.
- d_min = (mean min without X − mean min with X) × n_out / (n_out + 3).
- rate = (stat without X + base_rate × 60) / (min without X + 60), with base_rate = B's stat per minute
  over those last 10 games.
- proj = rate × (base_min + d_min). Flag the over when proj − main line ≥ 3 points / 2 rebounds / 5 PRA
  (unchanged).
- **cold**: "has a split" means exactly this live split (≥ 2 without, ≥ 3 with), as the cold-start
  registration defines it. `nba_wowy.sqlite` is no longer read by the flag pass.

**Flags already logged — not voided, not pooled.** Every wowy flag logged before this fix used the
frozen numbers. Outcomes are already known for 2026-10-23 (9-2 after amendment 6). So instead of voiding
them, they are **relabelled tier `wowy_v0`**: their own reported cell, never pooled with wowy. The
original label is kept in `void_reason`-free form; only `tier` changes. The main wowy cell starts empty
at the cutover, recorded below. The decision tier (priced) is unaffected.

**Amendment 7, correction (before any code was deployed).** The text above gives the cold tier's "has a
split" as ≥ 2 without and ≥ 3 with. The cold-start registration (`nba_coldstart_realline`) actually
defines it as **B appeared in ≥ 2 of X's missed games since X's first franchise game**, with no with-X
minimum. That registered definition is the one implemented. The ≥ 3-with requirement belongs to wowy
only.

**Applied 2026-10-24** under the VM cycle lock: the new code was deployed at 07:31:36, and **cutover was
2026-10-24T07:31:40 UTC**. All 29 wowy rows logged before it were relabelled `wowy_v0` (0 wowy rows left).
Every flag in tier `wowy` from here on is computed live. A dry run on 2026-10-24's slate produced 36 live
wowy candidates and 3 flags, with the cold tier at 27 candidates.

---

# AMENDMENT 8 — three tracked filter cells (2026-10-24, information only, forward only)

Registered before any of these cells has been computed on any flag. The ideas came from looking at
2026-10-23's 14 scored plays, which is exactly why they are scored **only on flags logged after this
amendment's cutover** (recorded below), never on that night. None changes what is flagged, the tiers, or
this test's verdict lines.

**Cell 1 — STALE LINE (the speed thesis made precise).** T_news is the flag's `news_at`. FanDuel's main
rung M(t) is `nba_clv.close_of(..., books=("fd",))` at time t.
- **STALE:** FanDuel had a two-sided main rung for that player-stat at T_news, and at the flag's
  `logged_at` it was unmoved: same line, over price within 0.03 decimal. The book posted the line before
  the news and had not reacted when we flagged.
- **LATE:** FanDuel had the rung at T_news but moved it (line, or price ≥ 0.03) before our flag.
- **POSTED-AFTER:** no FanDuel rung at T_news. The line was set with the news already known.
- **UNKNOWN:** no `news_at`.

Expectation, stated now: if a speed edge exists, STALE beats the close more often than POSTED-AFTER.

**Cell 2 — GAP SIZE (big disagreements are usually wrong).** LARGE means:
- wowy: proj − line > 2× the tier's margin (points > 6, rebounds > 4, PRA > 10);
- cold: proj − line > 2 × COLD_MARGIN (> 10);
- priced: EV > 0.20 (2× its 0.10 floor).

Otherwise NORMAL. Expectation, stated now: LARGE beats the close *less* often than NORMAL. The price
test found that the side disagreeing most with the market is usually the informed one.

**Cell 3 — MINUTES BAND (the WNBA's d_min band, re-tested in the NBA).** `d_min` is the projected minutes
bump with X out, as each tier computes it. It is stored on every flag from this amendment on. Bands use
the WNBA's edges: < 0, 0–3, **3–8**, > 8. Cold has no d_min and is shown as n/a.

No direction is predicted. The WNBA's best band was 3–8. The July NBA proxy backtest found 8+ best
(65.3%), and the priced tier inherits the WNBA's drop of d_min outside 0–8. This cell measures it.

**Reporting.** Every scoreboard prints these cells, pooled across tiers and for priced alone, on the
amendment-4 FanDuel yardstick: closed flags, beat-close rate with its game-clustered CI, and as-flagged vs
at-close ROI. They are read at the speed test's decision point. A cell whose beat-close CI lower bound
exceeds 50% at ≥ 100 closed flags in ≥ 30 games becomes a **candidate** for its own pre-registered tier,
through a new amendment and a new forward test. It is never a verdict here.

**Amendment 8 applied 2026-10-24.** `d_min` is stored on every flag from this deployment on. **The cells
score flags logged at or after 2026-10-24T07:43:00 UTC** (`nba_clv.AMEND8_CUTOVER`), and no earlier flag ever enters them.

---

# AMENDMENT 9 — tracked cell 4: OPPORTUNITY-CONFIRMED (2026-10-24, information only, forward only)

Registered before this cell has been computed on any flag. **The tracking-stats test** (NBA_TRACKING_PREREG.md)
replaced rebounds and assists with opportunity × conversion. It lost (−4.71% vs −3.46%) and did not
improve calibration. **This cell uses the same data differently**: as a *check* that a role bump shows up
in opportunities, not as a replacement input.

**Definition, computed at flag time and stored on the flag** (`opp_cell`, `opp_ratio`):
- Opportunity per game O:
  - rebound chances for a stat containing rebounds;
  - potential assists for a stat containing assists;
  - their sum for PRA and reb_ast.
  - Points-only flags are `n/a`.
- From B's split: the same team-scoped games since X's first franchise game that wowy uses, prior games
  only, restricted to games with a tracking row. Fewer than 2 games without X or 3 with X = `THIN`.
- ratio = mean O without X ÷ mean O with X.
- **CONFIRMED** if ratio ≥ 1.10, else **NOT CONFIRMED**.
- Cold flags have no split: `n/a`. No tracking data reachable at flag time: `NO DATA`.

**Data.** `nba_tracking.py` on the VM fetches `leaguedashptstats` per game date (Passing + Rebounding):
2025-26 backfilled for the 400-day pool, then the current season daily. Same endpoint and integrity
gate as the tracking test.

**Expectation, stated now:** probably no separation, given the tracking test. If it separates,
CONFIRMED beats the close more often than NOT CONFIRMED. Reported exactly as amendment 8's cells (all
tiers and priced alone, FanDuel yardstick, game-clustered CI). Same candidate rule. Never a verdict.

**Amendment 9, clarification (before its cutover; no flag scored yet).** "A game with a tracking row" counts
any game where B has a row. A blank component in that row counts as **0**: the Rebounding feed omits
players with no rebound chances, and per the tracking test's integrity gate 96–100% of those are
zero-rebound games. Skipping them would inflate the per-game mean.

**Amendment 9 applied 2026-10-24.** The VM's tracking backfill finished: 2025-10-21 → 2026-10-22, 27,013
player-games. The integrity gate passed for 2025-26: tracked 100.0%, AST and REB agree 100.00%, and all
2,857 missing rebounding rows are zero-rebound games. A fetch bug was fixed before the cutover: a date
returning 0 rows (not yet published) was being marked done. **The OPPORTUNITY cell scores flags logged at or
after 2026-10-24T08:03:00 UTC** (`nba_clv.AMEND9_CUTOVER`).

---

# AMENDMENT 10 — more X news sources: 62 beat writers and news accounts (2026-10-24, apparatus only)

**What changes.** The news layer (amendment 2) read one X account, @UnderdogNBA. `nba_x_beats.py`, a
second daemon on the VM (`nba-x-beats.service`), adds 62 accounts, validated by profile lookup on
2026-10-24:
- national insiders (Charania, Haynes, Stein, Fischer);
- injury and fantasy news (RotoBaller NBA, FantasyLabs NBA, Jeff Stotts);
- one to three beat writers per team.

Eight candidates were dropped: four did not resolve, and four resolved to accounts that did not look
like the reporter. The daemon reads them through X search, one request every 20 s rotating 3 chunks, so
each account is refreshed about every minute, on a separate budget from @UnderdogNBA's timeline. Posts in
an injury status are appended to the same X log, tagged with their author. Provenance is recorded as
`x:<handle>`.

**What does not change.** The rules for what a news item can trigger:
- the full name of exactly one player whose team plays on the stated date;
- the news layer's own Out classifier, add-only;
- a news-originated flag counts in a verdict only if the official report lists that player Out before
  tip. Otherwise it is an unconfirmed audit row (amendment 2).

The tiers, the yardsticks and the decision lines are unchanged.

**Why it is registered.** More sources mean more and earlier news-triggered flags. That changes the mix of
flags the test scores (more `trigger_src = news:x`, earlier `news_at`). The cutover is recorded below so
flags before and after it can be told apart. The STALE LINE cell (amendment 8) is where this pays off,
if it does: news caught before the book moves is exactly a STALE spot.

**Amendment 10 applied 2026-10-24.** `nba-x-beats.service` started at 08:46 UTC on the VM. Its first pass
marked the 64-post backlog seen without logging it, and it has been **live since 08:47 UTC**: 62 accounts,
3 chunks, one search every 20 s, rate budget 187 / 15 min (183 remaining after the first pass).

---

# AMENDMENT 11 — pings on, and a fast X path (2026-10-24, apparatus only, at the user's request)

The user asked for an ntfy push "immediately once a play is flagged, 0 latency and extreme speed". The
registration said pings would come only with PROMOTE, so this records the change.

**Pings.** `nba_ping.py` pushes one ping per play (game, player, stat) the moment its first flag row
commits, inside the flag pass:
- format: `🚨 {TEAM} {Name} {STAT} o{line} {odds} {tier} shadow`;
- a `⚠ VOID` (urgent) when a pinged play's premise dies before tip, by the board's retraction rule;
- plays that existed at go-live are seeded as already pinged.

Every tier is still **shadow**; nothing is a bet, and the ping says so.

**Fast X path.** `nba_watch.py --x-fast` (`nba-x-fast.service`) watches the X log every 2 s. When it grows,
it runs the news step for X only (fire, lines, flags, ping). On 2026-10-24 the minute cron plus the 55 s
news throttle had cost 59 s between Cooper Flagg's X post and the trigger. RotoWire and Bluesky stay on
the throttled path. The beat-writer search goes from every 20 s to every 10 s (each account every ~30 s,
90 of its 187 / 15 min budget).

**Unchanged:** what a flag is, how it is priced (the engine's logged price, never anyone's fill), the
tiers, the yardsticks, every verdict line. The cutover is recorded below.

**Amendment 11 applied 2026-10-24 21:10 UTC (3:10 PM MT).** NTFY_TOPIC was copied, on the VM, into
`~/.nba-ping.env`, which the engine's cron env and the fast service both read. 22 existing plays were seeded
as already pinged. `nba-x-fast.service` is active, and `nba-x-beats` was restarted at a 10 s cadence. Pings
fire from the next new play on.

---

# AMENDMENT 12 — per-game FanDuel refresh at trigger time (2026-10-24, apparatus only)

**What changes.** A trigger refreshes FanDuel only for the fresh Outs' games before the flag pass
(`nba_lines.cycle(only_gids=...)`). The board replace, the change log and pulled rungs are all scoped to
those games, so no other game's rows or quotes are touched. The cycle row is logged as `game`, so the
near-tip close capture never mistakes it for a full refresh. If it raises, or FanDuel's fetch fails, the
trigger falls back to the full refresh. DraftKings (the snapshot) is ingested in full, as before.

**Measured on the VM, 2026-10-24 21:4x UTC:** full FanDuel board 3.8 s (8 games left on the slate; 11–13 s
on the morning's 12-game board), one game 2.6 s, of which about 1.5 s is fixed setup.

**Unchanged:** the price a flag records is still FanDuel's (with any fresh DraftKings snapshot) at the
moment of the flag. Everything about flags, tiers, yardsticks and verdicts is unchanged.

---

# AMENDMENT 13 — a choice is not a ruling (news classifier correction, 2026-10-24)

**The defect.** On 2026-10-22 at 9:59 PM MT, @UnderdogNBA posted: "Joel Embiid said he won't play in both
legs of Sixers' back-to-back set on Saturday and Sunday. 'I'm playing in one of them.'" The news classifier
saw "won't play" plus "Saturday" and recorded *Embiid Out 2026-10-24*. That triggered VJ Edgecombe flags.
Embiid will sit one of the two games and did not say which.

**The fix.** `nba_news_watch.status_of` treats choice wording as not an absence, the same way it treats
a hedge: "won't play (in) both", "one of them / the two / the games", "sit/rest/miss one of / either of",
"either game", "only one of". It is kept narrow:
- "will miss one game" stays an Out;
- a named night ("won't play Sunday, the second night of the back-to-back") stays an Out;
- "unclear when he returns" stays an Out.

Re-run over all 441 stored Out items, exactly one changes: this one.

**Flags already logged.** No retroactive change is needed. Under amendment 2, a news-triggered flag counts
in a verdict only if the official report lists the player Out before tip. If the league lists Embiid Out
on 2026-10-24, the Edgecombe flags count, because the premise held. Otherwise they stay unconfirmed audit
rows.

---

# AMENDMENT 14 — inferred absences from a choice (2026-10-24, news layer, apparatus only)

**Why.** A player who says he will play only one of two games has, by playing the first, told us he
will miss the second. Embiid, 2026-10-22: "won't play in both legs... I'm playing in one of them." The
moment he takes the floor in game A, he is out of game B. That can come hours before the team lists
him for B, and before the books move.

**Rule.**
1. A news item whose Out phrasing is cancelled by a choice (amendment 13) is stored with status
   `choice`, not `other`. Its player and its two games are recorded as a pending choice. The player is
   the full name of exactly one player whose team plays in the next 3 days. The two dates are the named
   days on which his team plays, or, for "both legs / both games of the back-to-back" without named days,
   his team's next two games on consecutive dates. Anything else is not recorded.
2. Resolution, checked every minute by `nba_watch`:
   - official report lists him **Out for A** → he plays B → resolved, no trigger;
   - official report lists him **Out for B** → the normal path already has it → resolved;
   - **game A has started and the live box score shows him played** → he is **inferred Out for B**.
     A news item `source = inferred` is written for B, and the trigger fires: lines, flags, ping.
   - box score shows him **INACTIVE**, or game A finishes without him playing → he plays B → resolved.
3. An inferred Out is a **news-originated trigger**. As amendment 2 requires, its flags count in a
   verdict only if the official report lists him Out for B before B's tip. If a later report lists him
   with any non-Out status for B, it is contradicted and dropped (`news_outs`).

**Stored data corrected.** The 2026-10-22 Embiid item was stored as `out` before amendment 13. It is
re-labelled `choice` and registered as pending (A = 2026-10-24, B = 2026-10-25). The Edgecombe flags it
triggered stay logged, scored under amendment 2's confirmation rule.

**Unchanged:** flags, tiers, yardsticks, verdicts.

**Amendment 14 applied (2026-10-24T21:46Z, before MIL@PHI tip 23:30Z).** Code deployed to the VM;
`nba-x-fast` restarted. `reclassify_choices()` run under the cycle lock relabelled exactly one
stored item (`x` 2113480511347945915, Embiid, x:underdog) and registered one pending choice:
Joel Embiid (PHI), A = 2026-10-24 (0022600106 MIL@PHI), B = 2026-10-25 (0022600117 DET@PHI).
Dry run on a copy of the news store (nothing written, no ping): with the inferred Out for B, the
2026-10-25 pass yields one flag, wowy PHI VJ Edgecombe PTS o13.5 at 1.88, trigger `news:inferred`.

---

# AMENDMENT 15 — Doubtful is an absence (2026-10-24, trigger definition, its own cell)

**Why.** User, 2026-10-24: "if a player is doubtful treat them as out." The league's Doubtful means
he is unlikely to play, and in practice a Doubtful player almost always sits. Until now only Out
triggered, so a star listed Doubtful (Draymond Green and Kyrie Irving tonight) produced nothing.

**Rule, written before any Doubtful-triggered flag exists.**
1. ABSENT = {Out, Doubtful}, defined once (`nba_injury_report.ABSENT`). Wherever the trigger or the
   speed layer asked "is he Out?", it now asks "is he absent?": the flag pass (triggers, the
   never-a-beneficiary set, tonight's-game count for a tomorrow flag), the report watcher's fresh Outs
   (absent now and not absent on the previous report for that date, so Doubtful -> Out is not a second
   trigger), the news layer's "report already has it", and choice resolution (amendment 14).
2. News: an item that says a player is doubtful, with no other hedge, is stored `doubtful` and
   triggers like `out`. "Upgraded from doubtful", "no longer doubtful" and a doubtful item that also
   says questionable / probable / game-time decision stay `other`. A news Out or Doubtful is
   contradicted only by a later report status outside ABSENT.
3. Amendment 2's confirmation reads ABSENT: a news-originated flag counts if an official report before
   tip lists the player Out or Doubtful.
4. Each flag stores `x_status` = the absent player's strongest status at flag time (Out if the report
   or a news item says Out, else Doubtful).
5. **Its own cell, never in the decision.** Flags with `x_status` Doubtful are scored in a separate
   `doubtful` cell. They are flagged, shown on the board and pinged like any other flag, but they are
   excluded from the h0/h1 cells and from the board's decision count (DECISION_N). The registered
   speed test was built on Out triggers, so folding Doubtful in needs a later amendment with its own
   numbers.
6. Take-back: the board retracts a flag (and a pinged play gets a VOID) when the absent player's
   newest report status is Questionable, Probable or Available. Questionable joins the list because a
   Doubtful -> Questionable upgrade breaks the premise. That applies to Out triggers too.

**Cutover.** Forward only. Flags logged before this deploy keep x_status NULL, read as Out. Doubtful
players already on tonight's report become triggers on the first pass after deploy. Those flags are
hours behind the news, which the STALE LINE cell and their latency show, and they are in the
`doubtful` cell anyway.

**Unchanged:** tiers, thresholds, yardsticks, the decision lines, every Out-triggered verdict.

**Amendment 15 applied (2026-10-24T21:58Z).** Deployed to the VM; `nba-x-fast` restarted; the
`x_status` column added by migration. Dry run first, from a staged copy against the live stores
(nothing written, no ping): Draymond Green (GSW) and Kyrie Irving (DAL), both Doubtful on the 17:45 ET
report, are now triggers, and neither yields a flag. Each is under wowy's 28-minute star bar (last-10
mean 27.7 and 24.3), so the registered rule, not this amendment, decides tonight. The prompting item,
RotoBaller's "Jalen Green doubtful" (x 2114108943777562818), named two players and so never resolved.
The official report never listed Jalen Green; the Doubtful Green is Draymond.

---

# AMENDMENT 16 — the 24-28 minute band for wowy (2026-10-24, its own cell)

**Why.** User, 2026-10-24: "why not look at changing that to like 24+ mins." Tonight two Doubtful
starters were triggers but not "stars here": Draymond Green (last-10 mean 27.7 min) and Kyrie Irving
(24.3). The 28-minute bar is inherited from the Phase-0 backtest. It was never tuned.

**The check, run before this text.** The wowy real-line backtest (nba_margin_refit's population and
formulas, the shipped wowy MARGIN, best US over price at the main line, 2023-10-26 to 2025-04-13), with
the bar at 24 and each row tagged by X's trailing-10 minutes:

| X minutes | flags | dates | hit | ROI | 95% CI (date-clustered) |
|---|---|---|---|---|---|
| 28+ (today) | 2,585 | 282 | 51.7% | −3.83% | −8.6% to +1.1% |
| 24-28 | 820 | 169 | 52.3% | −2.33% | −11.4% to +6.5% |

The 24-28 band is no worse than 28+. Both lose a little at the historical (late) lines, which is
why speed is the open thesis. Beneficiaries gain less (median d_min +0.90 vs +1.30), so expect smaller
line moves. REB in the band (n = 57, +21.6%) is noise and is not acted on.

**Rule.**
1. wowy only: X qualifies at a last-10 mean of 24 minutes for this franchise (`WOWY_STAR_MIN`). priced
   and cold keep 28, because their own tests were not re-run.
2. Every flag stores `x_min` (X's last-10 mean at flag time).
3. **Its own cell, never in the decision.** wowy flags with x_min < 28 are scored in an `x24-28` cell,
   excluded from h0/h1 and from the board's decision count, like amendment 15's `doubtful` cell. A flag
   that is both goes to `doubtful`. They are flagged, shown and pinged as usual.

**Cutover.** Forward only, from this deploy.

**Unchanged:** priced, cold, margins, yardsticks, decision lines, every 28+ verdict.

**Amendment 16 applied (2026-10-24T22:03Z).** Deployed to the VM; `nba-x-fast` restarted; the `x_min`
column added by migration. Dry run first, from a staged copy against the live stores: the 2026-10-24
pass goes from 4 to 7 flags. The 3 new ones are all wowy GSW Gui Santos (PRA o21.5, PTS o12.5, REB
o5.5), triggered by Stephen Curry Out (last-10 mean 27.3 min), so they belong to the `x24-28` cell.
Draymond Green (27.7) and Kyrie Irving (24.3) now qualify as X, but no teammate clears the margin.

---

# AMENDMENT 17 — list posts are read player by player (2026-10-24, news layer, apparatus only)

**Why.** User, 2026-10-24: "if a tweet from one of those accounts says doubtful treat them as out, do not
wait for the official report, we need speed, so treat jalen green as out due to that report. If
rotoballer, underdog nba or the official reports lists an injury status then that is what we trust."
RotoBaller (21:37:38Z): "Jalen Green doubtful, Oso Ighodaro out for Warriors vs. Suns on Saturday". It
names two players, so the one-player resolver dropped it, and Jalen Green never triggered. (The official
report has not listed him; the user has decided to act on RotoBaller's word.)

**Rule.**
1. When an item's text names two or more players (full names, teams playing on the item's date), it is
   read clause by clause. Clauses are split on line breaks, commas, semicolons, "and", "&" and sentence
   ends. A line of the form "Doubtful: A, B" gives every named player that line's label.
2. A clause naming exactly one player gets its own status from the same classifier (amendments 13 and
   15). Each `out` / `doubtful` clause is stored as its own news item, id `{item}#{pid}`, with the parent
   item's detection time and provenance, and triggers like any news item. Clauses whose status is not
   an absence are not stored.
3. A one-player item is read as before. Surname-only mentions still never resolve ("Green doubtful"
   stays unresolved).
4. Scoring is unchanged: amendment 2 still scores a news-originated flag only if an official report lists
   the player Out or Doubtful before tip. Acting is immediate; the confirmation rule only decides the cell.
5. One-off: today's unresolved items are re-read under this rule, and any resolved absence fires once.
   Its news time is the time we first saw the parent item.

Also (apparatus): the cycle lock is a directory. A plain file at its path (left by an ad-hoc script on
2026-10-24 21:46Z, which blinded the watcher until 22:07Z) is now removed as stray, by both the watcher
and the cycle script.

**Unchanged:** tiers, thresholds, yardsticks, verdicts.

**Amendment 17 applied (2026-10-24T22:11Z).** Deployed; `nba-x-fast` restarted. Preview before the
one-off: today's unresolved posts yield 10 per-player absences. 9 match the official report exactly
(Veesaar, Horford ×2, Draymond Green ×2 Doubtful, Duren, Ighodaro ×3); Jalen Green (RotoBaller, Doubtful)
is the one the report does not list. `reread_lists()` under the cycle lock stored all 10. Only Jalen Green
fired (the rest were already on the report): news time 21:37:38Z, flagged 22:11:56Z, so 34 min late
because of the resolver gap. New wowy flags: PHX Dillon Brooks PTS o16.5 @1.96 and PHX Collin Gillespie
PTS o8.5 @1.80 (x_status Doubtful, x_min 25.6, so `doubtful` cell). All 5 new pings delivered.
The stray lock file was removed at 22:07Z. Watcher blind 21:46-22:07Z: cycles at 21:53 and 22:03 were
skipped, and the 18:00 ET report was processed 7 min late.

---

# AMENDMENT 18 — the card: what is pinged and shown (2026-10-24, selection layer, record unchanged)

**Why.** User, 2026-10-24: "is there a rule regarding picking the best one play from a player instead of
playing multiple different prop types... also only picking one player's points instead of playing o
Gillespie o Brooks points." The priced tier already has the WNBA card rules (nba_pricing.select and the
sticky top-2 disjoint slot). wowy and cold had none: tonight that meant Gui Santos PRA + PTS + REB and
PHX Brooks PTS + Gillespie PTS.

**The check, run before this text.** wowy on real lines (bar 24, live stats PTS / REB / PRA, shipped
MARGIN, 2023-10-26 to 2025-04-13). "Best" was fixed before looking as excess = (proj − line) / MARGIN.
- Win/loss correlation: same player, two props r = +0.61 (1,065 pairs); two teammates both PTS
  r = +0.002 (696); two teammates, any props r = −0.003 (2,688). A player's props are nearly one bet;
  teammates are independent, not negatively correlated.
- | rule | n | ROI | fit | hold | sd of a night's units |
  |---|---|---|---|---|---|
  | all (wowy today) | 2,383 | −1.9% | −3.0% | −1.0% | 3.46 |
  | one per player | 1,460 | −1.6% | −2.6% | −0.7% | 2.24 |
  | one per player + top-2 disjoint per team-game | 927 | −0.6% | −1.9% | +0.6% | 1.82 |
  All CIs overlap (top-2 disjoint: −7.5% to +6.1%). The case is variance, which halves, with ROI no
  worse. It is not a proven edge.

**Rule.**
1. **The record does not change.** Every flag is still logged and scored as registered (all tiers,
   cells, verdicts). The card only decides what is PINGED and SHOWN on the board.
2. Each flag stores `card` (1 on the card, 0 logged only; NULL before this amendment = shown).
3. priced: unchanged (its own selection and sticky slots). Every inserted priced flag has card = 1.
4. wowy and cold, in one pass: priced first, then the rest by excess, highest first. A flag is
   carded unless (a) its player already has a carded play for that game date (any tier: one per
   player), (b) its tier already has 2 carded plays in that team-game, or (c) it shares a P/R/A
   component with a carded play of its tier in that team-game.
5. Sticky, like priced: a carded play stays carded, and a re-flag of the same play (same date,
   player, stat, any line) inherits its card value. Nothing is ever un-carded or re-pinged.
6. Tracked cell (information only): CARD · ON / OFF on the FD yardstick, from the cutover, so the
   forward record shows whether the card beats the rest.
7. One-off: tonight's wowy/cold flags (2026-10-24) get card values by the same rule, in logged order
   then excess, so the board shows only the card. Pings already sent are not recalled.

**Unchanged:** every tier, threshold, yardstick, verdict and the decision count.

**Amendment 18 applied (2026-10-24T22:24Z).** Deployed; `nba-x-fast` restarted; `card` column added.
The backfill preview on a copy of the shadow store found one gap first: tonight's older flags carry
tier `wowy_v0` (amendment 7's relabel), and the backfill skipped them, so they would have stayed shown
and blocked their players. Fixed before running it: `wowy_v0` shares wowy's card slots. `card_backfill`
for 2026-10-24 and 2026-10-25, under the cycle lock: 3 of 12 wowy-family plays carded, priced rows
all carded, no NULL left. Tonight's card: PHI Edgecombe PTS o12.5 (wowy_v0); DAL Christie PTS o11.5 and
Washington R+A o8.5 (priced); DEN Murray PTS o22.5 and Gordon R+A o9.5 (priced); PHX Gillespie PTS o8.5;
GSW Santos PRA o21.5. Logged only: Santos PTS/REB, Brooks PTS, Murray wowy PRA/PTS, Edgecombe's others.

**User veto (2026-10-24, display only).** User: "take edgecombe off as hes no longer a flag." A `vetoes`
table in the shadow store holds (game date, player, reason). The board moves a vetoed player-game to the
OFF strip with its reason, never hides it, and a pinged play gets a VOID through the same path. The
record is untouched: Edgecombe's 2026-10-24 flags stay logged and are scored under amendment 2 (they
count only if an official report lists Embiid Out before tip).

---

# AMENDMENT 19 — singles first on the card, and a forward combo cell (2026-10-24, selection layer)

**Why.** User, 2026-10-24: "what about the wnba selection rule about combo plays being worse than single
stats" ... "yes wire it in". The WNBA's own registered combo cell (wnba_slip, 2026-08-04) never reached its
n = 20 decision. Forward it went combos 6-0 (+5.62u) vs straights 23-17 (+4.55u), against the hypothesis.
So the WNBA did not establish the rule.

**The NBA check, run before this text** (wowy real lines, bar 24, live stats PTS/REB/PRA, 2023-10-26 to
2025-04-13). FOUND BY SLICING, so this is a hypothesis, not a result:
- All flags: PRA n = 821, −2.3% vs PTS + REB n = 1,562, −1.8%. No difference.
- On the amendment-18 card (best excess per player): PRA picks n = 94, −20.0% (CI −39.4% to +0.8%;
  halves −29.3% / −13.1%) vs single picks n = 833, +1.6% (halves +0.8% / +2.3%). PRA does badly
  exactly when its excess beats the player's singles, i.e. a big elevation stacked over three stats.
  That is the WNBA's proposed mechanism.
- A card that takes the best SINGLE first (PRA only when the player has no single): n = 947, +0.3% (halves
  −0.2% / +0.7%) vs the live card n = 927, −0.6% (−1.9% / +0.6%). No worse in either half; not significant.
- NBA forward so far: combos 2-1 (+0.77u), singles 9-2 (+5.80u). Too small to count.

**Rule.**
1. **The record does not change** (every flag logged and scored as registered).
2. Card ranking for wowy/cold, per pass: each player's LEAD is their best single stat by excess, or their
   best combo if they have no single. Leads are carded in excess order under amendment 18's rules (one
   per player, ≤ 2 per tier per team-game, no shared P/R/A component). A player's other plays in that pass
   are logged only. priced keeps its own selection. Sticky as before; forward only. Tonight's carded plays
   stand (Santos PRA was pinged at 22:11Z).
3. **Forward combo cell, decision fixed now.** Population: wowy/cold flags logged from this cutover, one
   per play (date, player, stat), graded at the flagged line and price, ON or OFF the card. Combo = PRA,
   P+R, P+A, R+A. Information line: STAT TYPE · COMBO / SINGLE.
   **Decision at n ≥ 60 graded combo plays:** combo units ≤ 0 → combos are never carded (logged only).
   Combo units > 0 → the card reverts to best excess (amendment 18 ranking).
   Operating characteristics (binomial, price 1.87, break-even 53.5%; exclude iff wins ≤ 32 of 60):
   P(exclude) by true hit rate: 45% → 92%, 50% → 74%, 53.5% → 54%, 55% → 45%, 60% → 18%, 65% → 4%.
   Accepted as the WNBA did: a losing cell costs more than a missed one.

**Unchanged:** tiers, thresholds, yardsticks, verdicts, the decision count.

**Amendment 19 applied (2026-10-24T23:29Z).** Deployed; `nba-x-fast` restarted. AMEND19_CUTOVER =
2026-10-24T23:30:00Z; the combo readout shows 0/60 at deploy. Tonight's carded plays stand (sticky).

**User re-card of 2026-10-24 (display and ping layer only).** User: "Update the board to represent the
new flagged plays." Tonight's wowy-family card values are recomputed under amendment 19 (an exception to
"carded plays stand", by the user). Santos PTS replaces Santos PRA; nothing else changes. Coherence
(feedback_ping_board_coherence): a play that was pinged but is off the card is listed in a PINGED · OFF
CARD strip with its reason (1 PER PLAYER or TEAM SLOT) until its game starts. It is never a retraction,
so it never sends a VOID. The record is untouched.

---

# AMENDMENT 20 — prediction markets (Kalshi): a shadow collector and three registered tests (2026-10-24)

**Why.** User, 2026-10-24: "Can we incorporate prediction markets into this model as well like looking for
big money being put on the markets on certain props or big discrepancies between the prediction markets
and FanDuel."

**What exists (checked live, 2026-10-25 00:10Z).** Kalshi lists NBA player props as threshold contracts
("Jarrett Allen: 25+ points", floor_strike 24.5), which map one-to-one onto a FanDuel over at the same
line. Series: KXNBAPTS, KXNBAREB, KXNBAAST, KXNBA3PT, KXNBAPRA. Tonight, 8 games: points 339 markets,
880k contracts, median spread 4¢; rebounds 356, 284k, 5¢; assists 295, 459k, 5¢; threes 394, 229k, 5¢;
PRA 135, 25k, 24¢ (thin). Much of that volume is in-game. The public REST API needs no key. Polymarket's
NBA game events carry ~$1k-14k each in total volume, so it is not collected (revisit if that grows).

**Collector (apparatus, information only).** `nba_pm.py --loop 60` (service `nba-pm`): every minute, every
open Kalshi NBA prop market whose game has not tipped and tips within 36 h. A row is stored in
nba_pm.sqlite `pm_quotes` only when bid, ask or volume changed. Fields: ticker, game date, player
(resolved to the NBA person id within the two teams, never a surname guess), stat, line = floor_strike,
bid, ask, last, cumulative volume, OI, tip. Kalshi is not a book anyone bets here: nothing is flagged,
pinged or carded from it until a later amendment wires a test that passed.

**Definitions.** Kalshi fair k = (bid + ask) / 2, used only when ask − bid ≤ 0.10. FanDuel fair at the
same line: the over's implied probability de-vigged against the under when FD posts both sides,
otherwise raw 1/odds (marked RAW). Gap = k − FD fair. Pre-game only: quotes at or after tip are ignored.

**T1 — agreement as a filter (tracked cell).** For each closed flag logged from this cutover, Kalshi at
the flag's player, stat and line: the latest quote at or before logged_at, no older than 15 min. Cell
KALSHI · AGREES (gap ≥ +0.03), DISAGREES (≤ −0.03), NEUTRAL, NO MARKET; FD yardstick. Decision at
≥ 60 closed flags in each of AGREES and DISAGREES: if AGREES beats the FD close at least 10 points more
often than DISAGREES, with a game-clustered 95% CI of the difference excluding 0, a later amendment may
make it a card filter. Otherwise it stays information.

**T2 — Kalshi leads FanDuel (the speed thesis, applied to markets).** Event: a Kalshi market's fair
moves ≥ 0.08 within ≤ 10 min (spread ≤ 0.06 at both ends) while FD's quote for the same player, stat and
line is unchanged over that window. Outcome: FD moves the same way within 30 min (line ≥ 0.5, or the
over's implied probability ≥ 2 points). Control: windows on the same markets with |Δk| < 0.02. Decision
at ≥ 50 events: follow rate − control rate ≥ 15 points with a game-clustered CI excluding 0 → a later
amendment may make it a trigger. Otherwise information.

**T3 — big money.** Event: a pre-game minute with Δvolume ≥ 2,000 contracts on one market, or ≥ 500 and
≥ 10× its trailing 30-min average per minute; direction = sign of Δk over that minute (0 → not an event).
Outcomes: FD follows within 30 min (as T2), and the prop's result at the FD line and price at that minute
(flat units). Decision as T2 at ≥ 50 events.

**Unchanged:** every tier, flag, card, ping, verdict.

**Amendment 20 applied (2026-10-25T00:19Z).** `nba-pm` service installed and enabled on the VM (poll every
60 s, ~1,460 markets, ~115 change per minute; 100% of stored markets resolved to an NBA person id).
Two bugs found on the first live poll and fixed before the service started: (1) Kalshi's
occurrence_datetime is ~tip + 3 h, so markets for games in progress were stored. Tip times now come from
the NBA schedule, which also supplies the game id. (2) The FanDuel lookup did not pass gid, so it scanned
the whole quotes table; it now uses the index. First look at 00:25Z, before any test counts: on
two-sided (de-vigged) lines, Kalshi vs FanDuel median |gap| 0.014, none ≥ 0.05, mean −0.013. On over-only
ladder rungs (RAW) the mean gap is −0.057: FanDuel's margin, not disagreement. `--gaps` therefore shows
de-vigged lines by default. The definitions above are unchanged.
**Deploy regression, 2026-10-25 00:16Z–01:23Z (apparatus).** Deploying amendment 20 from a branch cut before
amendment 19 merged reverted 19 on the VM: no singles-first card, no STAT TYPE cell, no PINGED · OFF CARD
strip. No flag and no ping was logged in that window (checked), so no card value was set under the old
rule. Only the off-card strip was missing from the board. Fixed by merging 19 into the branch and
redeploying at 01:23Z. `nba_vm_deploy.sh` now refuses a deploy whose HEAD does not contain the commit the
VM runs (tested by recording a commit HEAD lacks: REFUSED).

---

# AMENDMENT 21 — the silence check: a news absence the report keeps omitting is contradicted (2026-10-25)

**Why.** 2026-10-24: RotoBaller's "Jalen Green doubtful" (21:37Z) was wrong. Jalen Green played 26 min;
the doubtful Green was Draymond. Read under amendment 17, it fired two PHX flags (Gillespie, Brooks) that
stayed on the board until tip, although every official report from 21:45Z on listed PHX without him.
User: "yes add the silence check."

**The check, on data, before this text.** 38 news absences (out/doubtful, resolved, not seeded, not
inferred). The report listed the player first 28 times; the news came first 8 times (to the first report
listing: median 28 min, then 28, 29, 37 for same-day items; 279 and 859 min for items about later
games); 2 were never listed (Jalen Green 10/24 RotoBaller; Cooper Flagg 10/30 bsky:globalnews3).
Simulated: judge silence on the first report published ≥ G minutes after the news that lists the team
for that game. For every G from 15 to 120 min, it silences Jalen Green and no real item. Restricted to
game-day reports with G = 60, it silences Jalen Green at 22:45Z and no real item.

**Rule.**
1. A news absence for player P (team T, game date D, first seen t) is SILENCED when the first official
   report that is (a) published on D (ET, by its mark), (b) published ≥ 60 min after t, and (c) lists at
   least one player of T for D, has no row for P. Implemented once in `nba_silence.py` (no dependencies).
2. A silenced item is dropped by `news_outs` (it no longer triggers), exactly like a contradicting status.
3. The board takes back a flag whose absence is news-only (the newest report does not list X as Out or
   Doubtful) and silenced: "{X} NOT ON REPORT". A pinged play gets a VOID (the existing path).
4. Exempt: `inferred` items (amendment 14). That is a deduction from the player's own words and the box
   score, which the team often lists only on game day.
5. A report that later lists P Out or Doubtful brings P back as a report-originated trigger (unchanged).
6. Scoring is unchanged (amendment 2 already scores such flags as unconfirmed audit rows).

**Unchanged:** tiers, thresholds, yardsticks, verdicts, the card.

**Amendment 21 applied (2026-10-25T09:42Z).** Deployed through the guarded script; `nba-x-fast` restarted.
Dry run first, on a staged copy against the live stores: no 2026-10-25/26 news absence is silenced (Embiid
inferred: exempt; Duren DET and Edey MEM: kept), and the board is unchanged.

---

# AMENDMENT 22 — the audit's fixes: stale-line card, minutes gate, aggregator confirmation (2026-10-25)

**Why.** The 2026-10-25 audit, then the user: "do all 4 and then run an audit again after that."
Findings (forward: 33 graded, 9 games; history: 2023-10..2025-04 real lines):
- **Timing.** 26 of 33 forward flags were on FanDuel props first posted AFTER the news (FD posts ~20 h
  before tip; the report usually precedes it), so no speed edge was possible. Those beat FD's close
  8/25. The 7 with a line before the news beat it 4/6. Report-triggered flags beat the close 7/24.
  The projection alone does not beat late lines: wowy −1.9% on 2,383 historical flags.
- **Minutes.** Historical slope of actual minute change on d_min = 0.34 (8+ band: predicted +9.8,
  actual +5.3). ROI by d_min: < 0 −8.7%, 0-3 −2.5%, **3-8 +0.9% (fit +1.2% / hold +0.6%)**, 8+ −7.9%
  (hold −13.6%). The WNBA's band gate was never ported to the NBA wowy tier.
- **Sources.** Resolved absences: Underdog 26, 8 first, 0 never on the report; X beat writers 10, 4
  first, 0 never; Bluesky 22, 1 never; RotoBaller 5, 1 never (Jalen Green, 10/24).
- **Per-minute rate.** Actual +2.8% pts / −0.1% reb over baseline; the X-out rate predicts no better
  than baseline. **No change (deliberate):** revisit after this amendment has data.

**Rules (the record is unchanged: every flag is still logged and scored as registered).**
1. **Stale-line card.** A flag goes on the card (pinged, shown) only if, at flag time, its STALE LINE
   value (amendment 8's definition, nba_clv.cell_stale) is STALE: FanDuel quoted this player and stat
   before the news time, and its main line and price are unmoved at flag time. POSTED-AFTER, LATE and
   UNKNOWN are logged only. All tiers, priced included (priced keeps its own slots).
2. **Minutes gate.** A wowy flag goes on the card only if 3 ≤ d_min ≤ 8. Logged either way; the MINUTES
   BAND cell keeps tracking all bands.
3. **Aggregator confirmation.** Aggregator sources: every Bluesky account, x:RotoBallerNBA,
   x:FantasyLabsNBA, and RotoWire items not citing the official report. An absence reported ONLY by
   aggregators does not trigger (news_outs, news_step) until a trusted source (Underdog, the X beat
   writers, RotoWire citing the report, an inferred absence) or the official report has it. The news
   time stays the earliest item, so the stale-line rule judges from first public word.
4. The card rules of amendments 18-19 still apply after 1-2. Sticky as before; forward only.

**Decision readout.** CARD · ON vs OFF (amendment 18's cell) is the measure: at ≥ 40 closed carded flags
in ≥ 15 games, if ON does not beat FD's close more often than OFF, the stale-line card is reviewed.

**Unchanged:** tiers, thresholds, yardsticks, verdicts, the decision count, the per-minute rate model.

**Amendment 22 applied (2026-10-25T09:58Z).** Deployed (the deploy guard first refused it falsely: the VM
ran the squash-merged amendment-21 branch, and this branch edits the same lines; the guard now also accepts
a VM change that reverse-applies onto origin/main when HEAD is built on main, and a real rollback is still
refused). `nba-x-fast` restarted. Preview at 10:01Z: tonight's four logged flags (Bane AST, Wagner REB
priced; Reed PRA/PTS wowy) are all POSTED-AFTER, and Reed is also out of band (d_min 12.6), so all four are
logged only. Replay of 10/23-10/24 (33 graded) through amendments 18-22: STALE 5, LATE 2, POSTED-AFTER 26.
The replayed card has 3 plays, 1-2, −1.12u, beating FD's close 1/2. POSTED-AFTER went 17-9 +5.73u but beat
FD's close only 8/25. Two nights decide nothing; the CARD cell's decision line does.

---

# AMENDMENT 23 — recalibrated wowy minutes: procedure and acceptance rule, fixed BEFORE fitting (2026-10-25)

**Why.** The 2026-10-25 audit: wowy projects proj = rate × (base_min + d_min), and d_min overstates the
minute change about 3× (slope 0.34 on all 2023-25 data). Every margin decision runs on that inflated
projection. User: "yes fix the minutes." An earlier quick check (out_rate × (base + 0.34·d_min): hold
+3.1%, fit −2.0%) leaked: its slope was fitted on all data, the hold half included. This amendment fixes
the procedure first.

**Procedure (history: nba_margin_refit's population and real main lines, bar 24, absence game 1-2,
stats PTS / REB / PRA; chronological split at the median date, 2024-10-28).**
1. **Minutes model, fit half only.** One row per player-game: OLS of (actual min − base_min) on d_min
   gives intercept a and slope k. New projected minutes = base_min + a + k·d_min. (d_min itself, its
   shrinkage and the band gate of amendment 22 are unchanged; the gate stays on raw d_min.)
2. **Margins, fit half only.** For each stat, the margin m ∈ {0.0, 0.5, …, 10.0} with the most fit-half
   units, among those with ≥ 100 fit-half flags. The rate (X-out shrunk rate) is unchanged.
3. **Evaluate on the hold half, once.** Recalibrated (a, k, new margins) vs current (d_min as is, MARGIN
   pts 3 / reb 2 / pra 5), each on its own flags, with and without the 3-8 gate.
4. **Adopt iff** the recalibrated projection's hold-half ROI ≥ the current projection's hold-half ROI,
   with ≥ 150 hold-half flags, in BOTH the ungated and the 3-8-gated versions. Otherwise nothing changes,
   and the result is recorded here.

**If adopted:** wowy_live projects with base_min + a + k·d_min and the new margins; flags store the same
fields; GAP and other cells read the new margins. Forward only.

**Scope.** wowy only. priced (WNBA machinery, its own elevation) and cold (redistribution) were not measured
here; that is noted as open, not changed.

**Amendment 23 result and adoption (run 2026-10-25T10:0xZ, exactly as registered).** Split at 2024-10-28
(25,454 rows). Fit-half minutes model (3,954 player-games): actual change = +0.980 + 0.356·d_min. Fit-half
margins: pts 5.0 (n 153, +6.3u), reb 1.0 (n 635, +14.6u), pra 6.5 (n 146, −4.0u: the best PRA margin with
n ≥ 100 still lost on the fit half). Hold half, evaluated once:
| | current | recalibrated |
|---|---|---|
| ungated | n 1,248, 51.8%, −0.78% | n 995, 52.5%, +0.04% |
| 3-8 gated | n 594, 52.7%, +0.60% | n 283, 56.5%, **+6.83%** |
The rule (recalibrated ≥ current in both, n ≥ 150) is met: **ADOPTED.** Not significant on its own (283
bets: roughly ±11% at 95%). Deployed 10:10Z; AMEND23_CUTOVER = 10:12Z. Preview on the live slate: Paul
Reed's PRA/PTS no longer clear the new margins (+12.6 d_min now ~+5.5 projected minutes), and Jalen Suggs
REB o3.5 appears (POSTED-AFTER, out of band: logged only).

---

# AMENDMENT 24 — priced and cold off the card; their minutes recalibration, registered (2026-10-25)

**Why.** Audit of the other tiers' projected minutes on their own real-line backtests (2023-25):
- **cold** (3,414 player-games): actual change = +3.11 − 0.18 × projected change. The proportional
  redistribution has no signal: projected +7.6 → actual +2.2; projected +1.8 → +3.3. Cold flags −5.7% (172).
- **priced** (6,430 candidate player-games): slope 0.67, but on the 2,092 it priced: projected +3.0,
  actual +1.0. Selections −4.7% (1,967); its own registered verdict (2026-10-22) was KILL, −3.46%.
User: "yes do option 3" (off the card now, recalibrate, put back what passes).

**Rule now.** priced and cold are not carded (logged only, never pinged) from this deploy. The record is
unchanged; re-flags of plays already carded keep their value (sticky). wowy's card is unchanged.

**Recalibration procedures (history; chronological split 2024-10-28; fit half only for every fitted
number; the hold half judged once).**
- **cold.** Projected minutes = base + a + k·(redistributed − base), by OLS on fit-half player-games.
  Margins per stat (PTS / REB / PRA) from {0.0, 0.5, …, 10.0}: the most fit-half units with ≥ 50 fit-half
  flags. Back on the card iff hold-half ROI ≥ 0 with ≥ 100 hold-half flags.
- **priced.** The minutes passed to prop_edges become with_min + a + k·(proj − with_min), where proj is the
  current final projection (split, position-compat, recent-5 floor). OLS on fit-half candidate
  player-games. Everything else in the WNBA machinery is unchanged (EV bar, shrink, guards, selection);
  the candidate gate keeps using the uncalibrated projection. Back on the card iff hold-half ROI of base-rung
  overs ≥ 0 with ≥ 150 hold-half bets.
- A tier that passes returns to the card by a later note in this file; one that fails stays logged only.

**Amendment 24 results (run 2026-10-25T10:2xZ, exactly as registered; split 2024-10-28; hold judged once).**
- **cold.** Fit-half minutes (1,897 player-games): actual change = +3.271 − 0.212 × projected change (the
  proportional split has no signal even in-sample: rotation players gain ~+3 min regardless). Fit-half
  margins: pts 2.0, reb 1.0, pra 3.0. Hold: current n 78, −19.09%; recalibrated n 161, −11.11%.
  **Fails (< 0). cold stays logged only.**
- **priced.** Fit-half minutes (3,036 candidates): actual − with = −0.272 + 0.880 × (proj − with). Relative to
  the with-X baseline the minutes are nearly honest, so priced's loss is not mainly minutes (its registered
  verdict: overconfident by 10-17 points of probability). Hold: current n 1,073, −4.66%; recalibrated n
  1,033, −3.78%. **Fails (< 0). priced stays logged only.**
Neither constant set is adopted. The card is wowy only (recalibrated, 3-8 gated, stale-line), plus inferred
plays already carded. Off-card rule deployed 10:17Z.

**User re-card of 2026-10-25 under the current rules (display and ping layer only).** User: "yes re-card
tonight." The verification audit found tonight's four carded plays (Reed PTS, Bane AST, Wagner REB, Edgecombe
PTS) were carded and pinged on Saturday night under the old rules; none passes amendments 22-24. `recard()`
replays each logged pass in order through the current card rules (stale-line judged at each flag's own
time). Pending rows are marked −1, because CARD_ON reads NULL as carded for pre-card flags. Pings are not
touched, so nothing is re-sent and no VOID is sent. Every card decision now stores its reason (`card_why`);
the board's PINGED · OFF CARD strip shows it. The record is untouched.

**Re-card applied (2026-10-25T10:4xZ, under the cycle lock).** 8 flags for 2026-10-25 recomputed: 0 on the card
(Edgecombe and Reed: LINE POSTED AFTER NEWS; Bane and Wagner: PRICED OFF CARD); the four pinged ones are in
the PINGED · OFF CARD strip. No ping or VOID sent.

**Backtest of the current card (information, not a decision; user: "does the new model backtest well?").**
The backtestable part only (no stale-line rule, no source rules: historical lines are late), on real lines
2023-10..2025-04: wowy bar 24, absence game 1-2, amendment-23 minutes and margins, 3-8 gate.
| | fit half (constants fit here) | hold half |
|---|---|---|
| all gated flags | 263 bets, 57.0%, +6.84% | 283 bets, 56.5%, +6.83% (CI −5.2% to +18.1%) |
| the card (singles-first, 1/player, top-2 disjoint) | 159 bets, 54.7%, +2.34% | 196 bets, 59.2%, +11.33% (CI −0.5% to +22.5%) |
Hold-half card by month: +15.6u of its +22.2u came in 2025-03; without March, +4.5%. About 1.8 bets per
slate night; worst drawdown 6.2u. The first wowy version positive in both halves (every earlier version and
tier was negative: −1.9%, −4.7%, −5.7%), but not significant: every CI includes 0.

**Apparatus bug and one void (2026-10-25T20:1xZ).** `latest_lines` and `board_ladders` keyed lines by player
and stat, not by game (the board's own key also lacks the game). A back-to-back player's flag for tomorrow
could take tonight's line. Found while checking tonight: the 10/25 VJ Edgecombe PTS flag (inferred from
Embiid, 2026-10-24T23:42Z) records o13.5 at 1.85, which is the 10/24 board row. Neither book had a 10/25 line
for him then; FanDuel first posted it at 11:03Z on 10/25, at 14.5. Audit of all 64 flags: 63 used their own
game's line; this is the only one that did not. Fix: both are keyed by (game, player[, stat]), and the flag
pass looks up the candidate's own game (test + 2 mutants; staged dry run on the live slate finds every line).
**Void:** that flag, reason "line from another game (lines keyed without the game)". Its line never existed for
its game, so grading it would score a number nobody could bet. The Embiid inference itself was right: he was
first listed Out for 10/25 at 17:00Z, 17 h 18 min after the inference.

---

# AMENDMENT 25 — the stale-prop lab, game lines, DraftKings morning seeds (2026-10-25, measurement only)

**Why.** The 2026-10-25 audit. The card fills on ~8% of wowy flags (3 of 38 were STALE), so its 40-play
decision is a year away. Meanwhile the broad test (every teammate prop FanDuel had posted when an absence
broke; over at the news-time main line; 15 final games) found: news-first props beat FD's close on 86% of
moved lines (62/72) vs 40% for report-triggered (256/644) and 40% for control (620/1,550). But 3 of the 4
news events had false premises (over hit 29%, −43%). DraftKings was dark 9 AM to ~12:20 PM MT on both
days: the chain ends at 06:00Z and the single 15:05Z seed was delayed 3 h+. No game spreads or totals are
stored, so blowout and pace cannot be tested. User: "yes do 1, 3 and 4 then after do 2 and 5."

**1. The stale-prop lab (`nba_stale_lab.py`, information only).** Unit: every teammate prop with a FanDuel
main line at a trigger's T0 (nba_reaction's affected set), earliest trigger per (game, player, stat). Taken:
the OVER at FD's main line and price at T0. Graded: FD's main line at tip (beat close, as amendment 4),
the box score (won, flat units; DNP void), and the PREMISE (did the absent player play that game?).
Joined: the model's view at first sighting. The flag pass now logs every wowy and cold candidate it
computes, before any margin, in nba_shadow.sqlite `cands` (first sighting per game date, absent player,
player, stat: projection, threshold, d_min, line, price, trigger, news time). That gives the excess
(proj − line) / threshold. Fixed slices: source (news / report) × premise (sat / played); stat; excess
band (no projection, < 0, 0-1, ≥ 1). Each slice reports beat-close (of moved lines), over hit, ROI, and
a game-clustered 95% CI. **Decision:** none here. At ≥ 300 graded news-first, premise-confirmed props, a
later amendment may redefine the card from the lab with a fit/hold split, registered before it is run.

**2. Game lines.** Every FanDuel fetch already downloads the league page, which carries each game's
moneyline, spread and total. They are now stored in nba_lines.sqlite `game_lines` (change log; pre-game
games only, matched to the NBA game id like the props). For a later, registered blowout/pace test.

**3. DraftKings morning seeds.** Extra schedule seeds at off-peak minutes from 15:13 to 17:41Z, so the
daily chain restarts within the news window even when GitHub delays a tick. The concurrency group already
keeps it to one running chain.

**Unchanged:** every tier, rule, card, ping and verdict.

**Amendment 25 — correction (2026-10-25T20:4xZ, before any lab decision).** (1) The lab's unit is one
ABSENCE × one prop: the earliest trigger for that absent player, per teammate prop. The text above said
"earliest trigger per (game, player, stat)", which folds a later absence into an earlier trigger for
another player. The first run did exactly that: the 10/24 RotoBaller "Jalen Green" news (premise false)
disappeared under an earlier report trigger on the same PHX props. Regression test + mutant. (2) **A false
statement in the "Why" above:** "3 of the 4 news events had false premises" is wrong. Per news event with
affected props: Spencer Jones (DEN 10/22), Podziemski, Flagg, Patrick Williams, Essengue and Smart all sat;
only Jalen Green played; Embiid's choice news had no affected props. The news-first slice's −43% (over hit
29%) was those games going against the overs, not false premises. The 86% beat-close figure stands.

---

# AMENDMENT 26 — premise watch and rebounds-tilt watch (2026-10-25, measurement with registered review lines)

**Why.** The audit's items 2 and 5. User: "then after do 2 and 5." Early news is where the CLV is (lab:
news-first, premise held, beat FD's close 68%), and a false premise turns that CLV into a loss. The
historical card is ~80% rebounds, yet rebounds react least to news (lab: 36% beat close).

**Premise watch (`nba_stale_lab.premise_events`, in the morning check).** Event = one news-originated
absence (out/doubtful item, resolved, not seeded) per player-game, after the game is final. Premise HELD if
he did not play. Classed by the strongest source that reported him: inferred, underdog, beat writer
(trusted X), aggregator-only. Also: whether an official report ever listed him Out/Doubtful.
**Review line:** over any rolling 14 days with ≥ 10 trusted-source (non-aggregator) events, if fewer than
90% held, a new premise guard is proposed by amendment, sized on the failures.

**Rebounds-tilt watch (nba_clv tracked cell CARD STAT).** Carded flags by stat on the FD yardstick.
**Review line:** at ≥ 20 closed carded flags, if rebounds are > 60% of them and beat FD's close < 45%, the
card's stat ranking (excess with REB margin 1.0) is reviewed by amendment.

**Unchanged:** every rule, card, ping and verdict. These are watches with pre-set review lines, not rules.
