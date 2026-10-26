# What the WNBA tracked model is, and what the NBA port actually ported

Research pass, 2026-10-22, day 2 of the NBA season. Companion to the real-line arbiter
(`nba_margin_refit.py`) run the same day. Every claim below is cited to code.

---

## 1. The WNBA model in one sentence

> **The gap between ELEVATED-ROLE production and a line the book anchored to the SEASON AVERAGE.**
> — `wnba_tonight.prop_edges` docstring, `wnba_tonight.py:515`

The book prices a player off who they have been. An injury makes them someone else for one
night. The model's whole claim is that the book is slow to that, and the edge is *priced*, not
*thesis-shaped* — see `project_wnba_beneficiary_drivers` (big WOWY/usage/minutes deltas are
monotone ANTI-signals). This matters enormously for the port: the thing that makes money is the
price machinery, not the beneficiary idea.

## 2. The eight mechanisms, in execution order

| # | mechanism | where | why it exists |
|---|---|---|---|
| 1 | absence → beneficiary via WOWY, needs ≥2 games without | `wnba_alert.py` (`W.wowy_multi` ~:286) | the trigger |
| 2 | minutes projection; bump must exceed 0.3 | `wnba_alert.py` | kills noise flags |
| 3 | **elevated sample**: player's own games at `min ≥ max(proj−4, ROLE_FLOOR=22)` | `wnba_tonight.py:529` | judge them in the role they're ABOUT to play, not their season |
| 4 | **minutes-honest rescaling**: each elevated game scaled to tonight's projected minutes, **cap 1.35×** (2.2× in breakout fallback) | `wnba_tonight.py:546-556` | without it the model cherry-picks a player's 26-min games to project a 19-min role |
| 5 | **credibility shrinkage toward the BOOK's implied probability, k=11** | `wnba_tonight.py:540-544`, `:645`, `:752` | raised 6→11 because the empirical hit read **64% shrunk vs 51% realized** — favourable-role games regress |
| 6 | **EV bar**: over 0.10 / under 0.04 / ladder 0.20 / volume 0.07 | `wnba_tonight.py:305-333` | asymmetric on purpose: unders on reduced roles beat baseline +6-9pts, overs on elevated roles regress |
| 7 | portfolio + veto: thin-sample guard (n<7 & jump>10, unless cold-start margin ≥5), won't post an over on a stat that DROPS without the out player, one-per-P/R/A pool, TOP-2 disjoint per team-game, `suppressed()` | `wnba_tonight.py:309-311`, `:638`, `wnba_slip.py` | stops correlated stacking and premise-break bets |
| 8 | record discipline: graded **overs** → drop tier `n1` → `current_selection` → base rung only | `wnba_headline.py:19-22` | the raw pool is NOT the record |

**The load-bearing parts are 3-6.** 1-2 find a candidate; 3-6 decide whether it is a *bet*.
Step 5 is the subtle one: the model never trusts its own hit rate. It blends it with the book's
implied probability, weighted by how much evidence it actually has.

## 3. What the NBA port implements

`nba_flags.py:175`, in full:

```python
if proj - line < MARGIN[stat]:
    continue
```

That is the entire bet decision. `MARGIN = {"pra": 5.0, "pts": 3.0, "reb": 2.0}`
(`nba_flags.py:42`), and `proj = rates[stat] * (base_min + d_min)` (`:170`).

So of the eight mechanisms, the NBA port has **1, 2, and a fragment of 8.** It is missing the
elevated sample, the minutes-honest cap, the shrinkage, the EV bar, and the portfolio layer.

### The consequence: price never enters the decision

Grep `nba_flags.py` for `price` — every hit is logging or line-selection. The best over price
across books is fetched (`:102`), used to pick the main rung (`:130`), and written into the
ledger (`:178`) — **and never consulted about whether to bet.** The engine takes a fixed
projection margin at whatever odds the book is offering.

That is the mechanical reason the real-line arbiter found nothing today: you cannot beat a
6.95% median hold with a rule that does not look at the price. The null is −6.56%
(CI [−8.76, −4.46], excludes zero) and no margin cell clears it with an interval that excludes
zero. **The NBA port never ported the model. It ported the thesis** — and the thesis is the half
that `project_wnba_beneficiary_drivers` already showed does not pay on its own.

## 4. The data gap, which is worse than it looks

`nba_gamelogs.sqlite.logs` persists **5 stat columns**: `min, pts, reb, ast, fg3m`
(`nba_beneficiary_backtest.py:45-47`).

`stats.nba.com/stats/leaguegamelog` returns **32 columns** (probed live from this Mac,
2026-10-22, season 2025-26, 26,651 rows):

```
FGM FGA FG_PCT FG3M FG3A FG3_PCT FTM FTA FT_PCT OREB DREB REB AST STL BLK TOV PF PTS PLUS_MINUS ...
```

The fetch reads the response and throws 27 of them away — including **FGA, FTA and FG3A.**

Why that specific loss is fatal: the WNBA model's per-stat decision map is

```python
STAT_DRIVER = {"points": "fga", "rebounds": "reb", "assists": "ast", "pra": "fga", ...}
# "FGA is a POINTS driver only; it's noise for reb/ast."   wnba_tonight.py:345-349
```

**FGA is the primary points driver**, and the volume layer (`PRIMARY_FGA = 13.0`,
`wnba_tonight.py:333`) is built entirely on it — it is what separates a room-to-grow role player
(who absorbs the vacated shots) from a primary option (whose shot count does not rise off an
injury, the Mabrey case that lost −38% on real lines). The NBA port cannot run either, because
the column is not in the database. Not unavailable — **discarded on ingest.**

## 5. What NBA adds that the WNBA can never have

All four probed live and working from this Mac today:

| endpoint | cols | what it gives |
|---|---|---|
| `leaguedashplayerstats&MeasureType=Usage` | 53 | **`USG_PCT`**, `PCT_AST`, `PCT_PTS` |
| `...=Advanced` | 79 | `AST_PCT`, `REB_PCT`, `OREB_PCT`, `DREB_PCT`, `OFF_RATING`, `EFG_PCT`, `POSS` |
| `...=Scoring` | 53 | `PCT_PTS_PAINT/3PT/FT`, **`PCT_UAST_FGM`** (self-created vs assisted) |
| `leaguedashptstats&PtMeasureType=Passing` | 18 | `AST_POINTS_CREATED`, potential assists |

`reference_wnba_advanced_stats` records that the WNBA has none of this and that **FGA is the best
usage signal available**. NBA measures directly what the WNBA model has to infer.

### The one that actually matters: `USAGE_RATE_ADJ`

```python
USAGE_RATE_ADJ = False     # OFF pending a proper gate (2026-08-06).   wnba_tonight.py:414
```

Read `_usage_mult`'s docstring (`wnba_tonight.py:446`). It exists because:

> The beneficiary path selects on a MINUTES bump and projects from the player's own elevated
> games — which include the games the out player PLAYED. **A player who absorbs usage without
> absorbing court time is therefore invisible.** Carleton with Barker: 30.24 min / 13.76 pts.
> Without: 31.00 min / 18.75 pts. That is +0.76 minutes and +5.0 points — a 33% jump in
> per-minute scoring, the largest on the team, and the model ranked four smaller MINUTES bumps
> above it.

It is switched **off** because the only way to estimate it in the WNBA is a rate ratio off a 3-5
game WOWY split, credibility-shrunk and capped [0.85, 1.30] — too noisy to gate properly.

**NBA has `USG_PCT` as a measured quantity.** This is the single place where the NBA does not
merely port the WNBA model but *repairs a component the WNBA had to disable.* It is the highest-
value item on this list by a distance.

## 6. Order of work (and why this order)

The temptation is to add NBA's rich stats first, because that part is fun and the data is sitting
there. That would be adding features to a margin screen — more precise projections feeding a rule
that still ignores the price.

1. **Port mechanisms 3-6** into the NBA path: elevated sample, minutes-honest cap, shrinkage
   toward the book (k=11 is a WNBA fit — re-derive, do not inherit), EV bar. This is the only
   change that could plausibly beat the hold, because it is the only one that prices the bet.
2. **Stop discarding columns.** Re-fetch with all 32 (one call per season, the fetch already
   exists) → FGA/FTA/FG3A → the points driver and the room-to-grow volume tier become runnable.
3. **Then** layer `USG_PCT` and turn on the usage adjustment the WNBA could not.
4. **Re-measure on real lines** with `nba_margin_refit.py` after each step, holdout untouched.
   The EV bar replaces `MARGIN` as the thing being fitted.

### Constraints to respect
- `stats.nba.com` is **Mac-only** (blocks CI/datacenter). Mac produces lookup tables, VM consumes.
  That hand-off has broken twice — see `reference_wnba_line_shopping`.
- Real-line odds history (`basketball_nba_odds_hist.sqlite`) runs **2023-05-04 → 2025-06-23**,
  2.0M rows, 10 markets. **The 2025-26 season has game logs but NO odds** (`reference_odds_api_key_gone`:
  no API key since 8/24), so it cannot serve as a real-line holdout. Forward paper from today is
  the only clean out-of-sample left.
- Do **not** port the WNBA guard-rebound gate (`project_nba_port`) — NBA guard-forwards genuinely
  rebound.
- `nba_injuries.json` last wrote **2026-08-14**. The trigger feed for all of this is dead; fix
  before anything downstream is meaningful.

## 7. Status of the claims here

Mechanisms and line numbers: read from code today. Endpoint columns: probed live today.
The real-line verdict: `nba_margin_refit.py` + `nba_margin_ci.py`, date-clustered bootstrap,
every positive cell's 95% CI crosses zero. **Nothing here is a validated NBA edge** — it is a
diagnosis of why the port has not been tested on its merits yet, and the order that would test it.

---

## 8. Addendum, same day: fixing the feed exposed the next blocker

The injury feed was fixed (see below) and immediately revealed that **12 of 13 OUT players in
the news window resolve to ZERO WOWY pairs.** All 26 ESPN abbreviations map to valid tricodes
and all 30 teams are present in `pairs` — the mapping is fine. The problem is that
`nba_wowy.sqlite` was built trailing-400d through **2026-04-12**, so it encodes *last season's*
rosters, and the pair lookup is **team-scoped** (`pairs` PK = `(team, x_id, b_id)`).

Every summer move therefore misses: Coby White is on CHA now and his pairs are filed under CHI;
Porziņģis is on GSW and his are under his old team. Rookies (Boswell, Diop, Tomlin, Sorber,
Bittle, Carlson) have no history at all.

A rebuild does **not** fix this yet — WOWY derives roster membership from game logs, and there
are only one or two days of 2026-27 games to fold in. The structural answer is the one already
specified and validated: the **cold-start tier** (proportional minutes redistribution over the
12-32 min rotation, margin ≥5 → 63.7%, ≥8 → 67.8% on 1,345 flags), listed in `project_nba_port`
as *"TODO P2: add the same cold-start fallback to nba_flags.py"*. It is no longer a nice-to-have:
**without it the engine is blind to ~92% of tonight's actual absences.**

Note this is also a *measurement* warning for §6 step 1. Any re-fit of the margins on
`basketball_nba_odds_hist.sqlite` is fitting the WOWY-tier population only. The cold-start tier
is a different population with a different (lower) ceiling, and it is most of the live volume in
October. Fit them separately or the blend will be wrong.

---

## 9. Addendum: the VM's NBA engine was blind four ways at once

Checked read-only on the board VM, 2026-10-22. `vm_loop.sh` runs `nba_injuries.py` **and**
`nba_flags.py` (not dry-run) every ~30 min with stdout to `/dev/null`. It has never logged an NBA
bet (`bet_ledger`: 0 rows), and not because the nights were quiet:

| # | blind input | evidence |
|---|---|---|
| 1 | every injury row had a blank tricode | VM `nba_injuries.json`: 71 of 71 blank |
| 2 | **nothing collects NBA prop lines** | VM `wnba_lines.sqlite` has only `wnba`; Mac `fanduel_props.sqlite` has no `nba`; Actions runs `dk_collect.py --wnba` only, and its NBA/injury steps were deleted (the comments remain) |
| 3 | no slate | `cdn.nba.com` 403s the Oracle VM even with browser impersonation, so `todays_games()` returned `{}` |
| 4 | stale rosters | team-scoped WOWY lookup; 12 of 13 OUTs matched no pairs |

Each failure was caught and turned into an empty result, and every combination printed the same
`0 flags`. **Correction to an earlier commit message (52dacdc):** it says nothing ran the feed.
The VM did run it, every 30 minutes; the Mac copy was stale only because the VM's copy is the one
that gets committed. The Mac cron that commit's work added was a duplicate and has been removed.

**Topology now:** slate, rosters and this season's box scores are **Mac-only** (`curl_cffi`
impersonation from a residential IP), like `stats.nba.com` and DraftKings. `nba_flags.py` exits 2
with the reason on a host that cannot reach them, so after merge the VM will log
`nba_flags fail` to `~/loop_fail.log` every ~30 min. That is true, and loud on purpose; removing
the line from `vm_loop.sh` is the operator's call. The blocker that remains on every host is #2:
**until something collects NBA lines, the engine has nothing to price against.**

---

## 10. Addendum: the NBA line collector (blocker #2 closed)

`nba_lines.py`, run on the Mac every 10 min by `nba_cycle.sh` (deployed to
`~/cron-jobs/nba-cycle.sh`, cron `*/10`): injuries → lines → shadow flags → grade.

**Both books answer from the Mac** (2026-10-22): FanDuel sbapi over `requests` (urllib has no CA
certs here; NY and NJ regions returned identical NBA boards), DraftKings via `curl_cffi`. First
cycle: FanDuel 2,351 rungs, DraftKings 2,994, every game in the next 24h covered, 0 unresolved
players. The parsers are `fd_collect.extract` and `dk_collect.collect_league`, unchanged.

**`nba_lines.sqlite`**, three tables:
- `board` — current pre-game board per book, replaced only on a successful fetch. `nba_flags`
  reads it, taking **every book's** latest board inside 90 min. The old reader took
  `MAX(collected_at)` across books, which would have silently kept one book and killed line shopping.
- `quotes` — append-only **change log**: a row when a rung first appears or its price moves.
  The 2.0M-row history is tip snapshots only; this is the first NBA data that can measure CLV
  and the news-window move. Starts 2026-10-22.
- `cycles` — per-book status, row counts, event-match and name-resolution coverage.

**Identity is a person id, resolved within the game's two rosters** (exact folded name → no
suffix → first initial + surname, each only if unique; else NULL and counted). `nba_flags` now
joins lines on that id. Current rosters come from `stats.nba.com/stats/playerindex`
(`nba_rosters.player_index`, 519 active players): "team of last appearance" was wrong for every
summer move (DeRozan read SAC, he is DEN; Watson read DEN, he is CLE) and placed no rookie.

**Bugs found while building it, fixed before any data was relied on:**
- *Fake price moves.* Books post one bet twice — the O/U over 14.5 and the "15+" milestone, at
  slightly different prices (120 FanDuel / 131 DraftKings rungs). The board flipped between them
  and every flip logged a move: cycle 2 "moved" 251 rungs in 90 s, and none had. The board now
  keeps the best price per rung. The fake rows were purged and the log re-seeded from the
  corrected board.
- *`timeout` does not exist on macOS.* Under a bare cron environment every step would have
  exited 127. The wrapper uses `perl -e 'alarm…'`; checked: a 10 s sleep dies at 2 s, rc 142.

**What still limits it:** the Mac has to be awake. A sleeping laptop is a gap in `quotes`, and
`cycles` shows where. The VM cannot take this job — every input is blocked there.

---

## 11. Addendum: the WNBA pricing machinery, ported — and measured

Done as §6 ordered it: pricing before features. Pre-registered in `NBA_PRICING_PREREG.md`, result
appended there. **KILL at the close** (−3.46%, n=1,186), better than the margin rule and the null.

**How it was ported: by calling, not copying.** `nba_pricing.py` binds NBA inputs to the WNBA's
frozen functions — `wnba_tonight.prop_edges`, `wnba_alert.position_compat`,
`wnba_slip.current_selection` — with the four pre-registered NBA departures as process-local
overrides (`ROLE_FLOOR` 26.4; volume layer off; guard-rebound gate off; DvP off). The backtest and
`nba_flags` tier `priced` both import it; refactoring the test onto it left the output
byte-identical.

**Prerequisites it forced:**
- `nba_logs_full.py` — the 32-column game logs (FGA/FTA/FG3A) and positions, in new tables beside
  `logs`. The conviction gate passes an over on minutes > 2 **or** FGA > 1 and treats a missing FGA
  split as a fail, so without shot columns the machinery bets nothing. Verified row-for-row against
  `logs` (one 2022-23 0-minute DNP row the league has since dropped; reported, not a failure).
- `nba_rosters.state` now reads `logs_full`, so live appearances carry shot columns.

**Live wiring checks:**
- The live tier first priced a 15-minute Tomlin absence — outside the tested universe (≥28-min
  absences only). Fixed to the same star rule; forward shadow must grade the population the test did.
- Card slots are sticky like the WNBA card (an entered play stays; a newcomer needs an open,
  P/R/A-disjoint slot). The first test of that was **vacuous** — a two-cycle replay that passed with
  the rule switched off. Replaced by `test_nba_priced_slots.py`, which forces each case and includes
  a mutant that must fail; it does.
- Combo props (pts_reb/pts_ast/reb_ast) grade by summing components; checked against cdn box scores.

**Where that leaves the port.** The WNBA's two halves have now both been measured on NBA real lines:
the thesis (margin rule) and the pricing. Neither beats the close. What has not been measured is the
WNBA's actual claim — speed. That is what the shadow + quote log now accrue, from 2026-10-22.

---

## 12. Addendum: the speed layer — replicating how the WNBA actually made money

**Why.** The WNBA record (forward since 7/31: 32-17, +13.11u, +26.7%) beat the closing line on
67% of its bets; at closing prices the same bets earn +11.5% instead of +20.2%. Every NBA test so
far priced at the close. So the replication target is the WNBA's *timing*, not another model —
and it can only be measured forward. Pre-registered in `NBA_SPEED_PREREG.md` before any flag.

**What was built** (Mac, `~/nba-engine`):
- `nba_injury_report.py` — the league's official report (every 15 min, ~4 s after the mark),
  parsed with the WNBA's own parser plus NBA team names. Names are resolved within the team's
  roster, because the PDF text splits multi-word surnames ("Lively II, Dereck" → "Dereck II" from
  the bare parser — Lively was Out that day). Checked: 32 status words / 32 rows / 18 NOT YET
  SUBMITTED blocks; six reports with every matchup's teams found and 0 unresolved. Stores every
  report with its publish time (`nba_news.sqlite`) — the news clock.
- `nba_flags.py` now takes Outs from the official report only (as the WNBA does — ESPN
  over-reported Out on 4 of 22 audited rows), applies absence game ≤ 2 **within the current
  season** (Mitchell's October opener read as absence game 3 because he sat April 10/12), excludes
  every tonight-Out from beneficiaries, and records `news_at` and the person id on every flag.
- `nba_watch.py` (cron every minute) — polls through each publication, diffs, and on a fresh Out
  for tonight refreshes both books and runs the flag pass at once. Synthetic end-to-end test:
  **10 s from publication to five shadow flags**, each with news time and person id. Within 35 min
  of a tip it refreshes lines every 2 min so the close is fresh.
- `nba_lines.py` logs **pulled** rungs (odds NULL, full fetches only) so the close can be rebuilt.
- `nba_clv.py` — the scoreboard: beat-the-close rate (CI resampling games), line move, as-flagged
  vs at-close ROI, latency. `test_nba_clv.py` checks the rebuild with known answers and a mutant
  that treats pulled rungs as live (it fails, as it should).

**Tomorrow's-game rulings — added the same day** (prereg amendment 1, committed before any flag).
The league publishes the next day's rulings the afternoon before; the trigger now fires on those
too. Flags carry `horizon` (0 = game day, 1 = the day before) and the two are separate cells,
never pooled; the scoreboard counts one opportunity per (tier, player, stat, game) — its earliest
flag. For a tomorrow game, a player also ruled Out tonight counts tonight as a missed game
(`absence_index`, unit-tested with a mutant). Synthetic end to end: a Brunson ruling for the next
day's NYK@BOS → 4 flags, all horizon 1, **9 s** from publication.

**Not in it yet, by design:** any news source faster than the report (it would only make the
engine faster), pings and paper bets (only on PROMOTE).

---

## 13. Addendum: a news layer ahead of the official report — built, and honestly measured

Pre-registered as amendment 2 before any flag: news is add-only; every flag records `trigger_src`;
a news-originated opportunity counts only if an official report before tip confirms the absence
(else it is an audit row, never in a verdict).

**What was found about the free sources (2026-10-22):**
| source | verdict on day one |
|---|---|
| RotoWire NBA wire | the afternoon's injury items **linked to the official report's PDF as their own source** — downstream of it; beat-sourced items may still lead, so `provenance` is recorded per item |
| Sleeper `/players/nba` | updated **5-20 min after** the report published the same rulings — slower; not used |
| ESPN news | articles, not rulings; not used |
| Bluesky search | mostly fantasy reposts and non-NBA "ruled out" posts; kept, matched only on an exact unique name on a team playing that day |
| **X (@UnderdogNBA, team/beat accounts)** | where news breaks first — but free X reading is dead in 2026; the VM's working reader uses the user's burner session cookie. **Benched** (`NBA_X_LOG`) until the user decides how to run it |

**Built:** `nba_news_watch.py` (sources → `news_items` with first-seen time, provenance and a
seeded flag; `news_outs()` add-only with official contradiction; `--journal` = lead over the
report per source). `nba_watch.py` polls it every ≥55 s and fires the same action as a report
trigger on an Out the report does not list yet. `nba_flags.py` merges news Outs add-only and
records `trigger_src` + the absent player's id. `nba_clv.py` applies the confirmation rule.

**Bugs found while building it:**
- RotoWire injury items carry a second CSS class (`news-update is-injured`); the first parser split
  on the plain class and **skipped every injury item** while parsing stat lines fine. Fixed, with a
  guard that refuses a page whose injury items were not all parsed — and the guard's first version
  did NOT fire on the old bug (merged blocks hid it); rebuilt to count injury items independently of
  the split, verified by restoring the old splitter.
- The first live poll ran before backlog seeding existed: 44 items stored as "just seen", any of which
  could have fired as fresh news. None did (every resolved Out was already official), and the rows
  were retro-marked. A source's first poll now seeds its backlog and never triggers.

Synthetic end to end: a news item ruling Brunson out for the next day's NYK@BOS, unknown to the
report → 5 flags, all `news:…`, Brunson as the absent player, news time = the moment it was seen.

**X — switched on the same day (user decision).** The VM's `underdog-watch.service` (which holds
the burner cookie) now reads **@UnderdogNBA**, via a systemd drop-in
(`/etc/systemd/system/underdog-watch.service.d/nba.conf` → `/home/ubuntu/underdog-nba.env`, no
secrets). `underdog_watch.py` on the VM gained three env switches with unchanged defaults: its own
log (`underdog_nba_log.jsonl`), its own seen-file, and **no WNBA fullscan kick** — every hit used to
start a ~52 s WNBA scan. Backup: `underdog_watch.py.bak-20261022-nba`. **Revert:** delete the
drop-in, `sudo systemctl daemon-reload && sudo systemctl restart underdog-watch`. Injury-tweet pings
were already off (user, 2026-07-24); its health alerts (expired cookie, changed endpoint) stay on.
The Mac pulls that log over ssh every ≤55 s with a heartbeat (a silent or inactive watcher raises).

**First measurement of X:** @UnderdogNBA's "listed out" posts *relay* the official report ~10-16 s
after it publishes — no lead. Its coach/beat posts lead it by **hours**: "Keefe: AJ Dybantsa (ankle)
ruled out for Friday" at **16:16 UTC**; the league listed him at **20:45 UTC (+4 h 28 min)**.
That is the speed this layer exists to buy, and the journal now measures it per item.
