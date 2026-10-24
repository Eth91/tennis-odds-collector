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
