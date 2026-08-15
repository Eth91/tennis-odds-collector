# WNBA RESEARCH TWIN — STATE
production: v1.8 frozen 2026-08-13, 8 files. UNTOUCHED.
research_root: research/   (nothing here is imported by production)

## data assets
- basketball_wnba_odds_hist.sqlite : 6 snap_kinds, 2023-05-21..2026-08-13
- wnba_props_hist.sqlite (2026), wnba_props_2025.sqlite : legacy, 45-min snaps
- wnba_stints.sqlite : onfloor/pairs/pteam, 942 games 2023-05-05..
- wnba_ledger.sqlite : 205 predictions, 2026-07-09..
- underdog_log.jsonl : 307 news items w/ timestamps

## open blockers
(none)

## priority queue
1 odds-timeline coverage   2 market timing   3 stint decomposition
4 role-transition graph    5 market response 6 new markets  7 ranking failure

## live research instruments
- research/pr002_shadow.py  cron */20  -> research/pr002_shadow.sqlite  (PR-002 forward test)
- wnba_health.py            cron */30  -> ~/health.log (empty = green)

## next when data allows
- PR-002 needs n>=40 shadow rows before any read. Do NOT peek at partial n.
- PR-001 (vac) needs n>=40 tracked rows graded after 2026-08-13.

---

# PHASE 3 — MARKET REPRICING / INFORMATION ABSORPTION (opened 2026-08-15)

**Question (§31):** when a role-changing event occurs, does a tradable price already exist, and
can subsequent repricing be predicted from information available before the move?

## DATA RISKS — read before designing any experiment here
- 🚨 **`wnba_lines.sqlite` is a ~3-DAY ROLLING BUFFER.** A month-long `BETWEEN` returns rows and
  raises nothing while covering 2 days. `COUNT(*)` reads 1.5M because a buffer is DENSE, not long.
  **Always print the actual distinct-day list** (§6/§37). This already produced one false +12.8pp.
- 🚨 **`wnba_proj_log` is a MUTABLE CURRENT-STATE TABLE, not a series.** It upserts
  `ON CONFLICT(date,pid) DO UPDATE`, so each (date,player) keeps ONE row and `logged_at` is the
  LAST write. The model's *earlier* view of a player is overwritten and unrecoverable. It cannot
  answer "what did the model think at T" for any T before the final write (§36 forbids relying on
  exactly this shape). Usable only as a single end-of-day snapshot.
- ⚠️ **`clv.flagged_at` is PRICE-DEPENDENT.** The flag requires EV >= threshold, which reads the
  posted price. It is a valid *event timestamp*, but using it as a *predictor* of movement toward
  that same price is the §19 leakage failure. Predictive tests must use price-independent inputs
  (`d_min`, `proj_min`, WOWY role change) — verified available: **`wnba_wowy.py` contains zero
  references to `p_market` / `posted_props` / `de_vig` / `shrink`**, so `proj_*` are price-free.
- ⚠️ **Prop pools are mostly ALT-LADDER rungs.** Tell: over% sliding monotonically with line level.
  Collapse to the rung nearest even money before any market-wide statement (§24).
- ✅ **Baseline sanity gate, mandatory before any market-relative claim (§7):** a main-line pool
  must hit ~47-48% overs after vig. A pool reading 40.5% is a defect, not a base rate.

## INFRASTRUCTURE
- `research/tick_archive.sqlite` — **timestamped** observations, one row per
  (day, player, stat, line, side, book, collected_at). Built by `research/build_tick_archive.py`
  from the daily backups. PK makes re-ingest idempotent: overlapping backups re-observe the same
  rows, and without dedup the series would look ~3x denser and every time-to-reprice would be
  wrong. Nothing interpolated or forward-filled (§8/§36).
- `research/line_archive.sqlite` — LAST pre-game quote only. Fine for base rates, **useless for
  repricing** (the collapse destroys the series). Do not use it here.
- Both are gitignored; the generators are tracked. Regenerable, so never committed.

## PROSPECTIVE (frozen — do not peek, do not tune)
- **PR-001** `vac` gate — n>=40 tracked rows graded after 2026-08-13.
- **PR-002** 8-12h capture window — n>=40 shadow rows. Instrument repaired 2026-08-15 (inverted
  `n_without` gate had it logging ZERO for two days); thresholds unchanged, clock starts 08-15.
  Loop may verify it is *collecting*; it may not read its results.

## SETTLED — do not re-open
- **The situation carries no outcome signal (+0.1pp, z=0.04).** Any edge is on the PRICE side.
  This is what motivates Phase 3.
- **CLV is not a sufficient proxy for edge.** News recency predicts CLV strongly (z=5.47) and
  predicts bet outcome not at all (z=0.57, sign flips). Being demonstrably early on real
  information did NOT convert to profit in that population. A repricing edge must therefore be
  argued economically (§29), never on CLV alone.
