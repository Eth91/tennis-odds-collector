# CLV audit: one yardstick across the paper-betting systems

Read-only, on the Mac. Nothing bet, pinged or changed on the VM or any live system.

- **Method, fixed first:** `CLV_AUDIT_PREREG.md`, committed and pushed as 7d2f5b2379 (2026-11-04 03:32 UTC), before any
  strategy-level CLV was computed.
- **Code and guards:** `clv_audit.py` and `test_clv_audit.py` (17 mutants, all killed), committed before the run
  (5a0af73fac).
- **Audit files:**
  - `audit/clv_audit/bets.20261104.csv`: every bet with its CLV, null, excess and the reason when it wasn't scored.
  - `audit/clv_audit/result.20261104.json`: summaries, tiers, store hashes.
  - `audit/clv_audit/sens.20261104.json`: the sensitivity reads.
  - `CLV_AUDIT_TABLES.md`: every strategy, every missing-close reason, and the breakdowns.
- **Data:** stores read up to 2026-11-04 03:00 UTC. The NBA data is the 11/3 VM backup, so its forward window is
  10/27–11/02.

**CLV here:** the no-vig closing probability of the bet's side at the bet's line, times the bet's price, minus 1. It's
measured against the **same book's** close, taken no more than 30 min before the start.

**CLV is not profit.** ROI is in the tables file as information only.

## Verdict

| System | Strategy | Scored (coverage) | Dates | Mean CLV [95%] | Null | Over the null [95%] | Holm p | Tier |
|---|---|---|---|---|---|---|---|---|
| Tennis Pinnacle-ref | pinnacle_ref | 816 (71%) | 41 | +1.5% [+0.8%, +2.3%] | −6.9% | +8.5% [+7.7%, +9.2%] | 0.005 | **Strong** |
| NBA side-by-side | DK_LAGS_FD | 943 (95%) | 7 | +1.3% [+0.6%, +1.8%] | −6.2% | +7.5% [+6.7%, +8.0%] | 0.005 | **Promising** |
| NFL V2 | alt_tails (price CLV) | 578 (96%) | 10 | +0.2% [+0.1%, +0.5%] | +0.1% | +0.1% [−0.1%, +0.2%] | 0.940 | **No evidence** |
| NBA side-by-side | NULL_TIP30 | 1806 (94%) | 7 | −5.7% [−5.8%, −5.6%] | −5.7% | +0.0% [−0.2%, +0.2%] | 1.000 | **Loses to the close** |
| NBA side-by-side | RATIO_RC | 276 (94%) | 7 | −6.3% [−6.8%, −5.4%] | −7.2% | +1.0% [+0.4%, +1.7%] | 0.005 | **Loses to the close** |
| NBA side-by-side | DEPTH_NEXT_TIP30 | 228 (98%) | 7 | −5.9% [−6.6%, −5.3%] | −5.8% | −0.0% [−0.9%, +0.5%] | 1.000 | **Loses to the close** |
| NBA side-by-side | NEWS_FD | 214 (95%) | 6 | −4.6% [−6.2%, −1.2%] | −5.7% | +1.1% [−0.3%, +3.8%] | 0.756 | **Loses to the close** |
| NBA side-by-side | UNDER20 | 212 (98%) | 6 | −6.0% [−7.0%, −5.2%] | −5.6% | −0.4% [−1.3%, +0.4%] | 1.000 | **Loses to the close** |
| Tennis model | forward (Elo vs FanDuel) | 211 (75%) | 38 | −2.6% [−3.7%, −1.7%] | −4.4% | +1.8% [+0.7%, +2.7%] | 0.005 | **Loses to the close** |
| NBA side-by-side | RATIO_PA | 198 (87%) | 7 | −5.2% [−6.8%, −2.5%] | −7.3% | +2.1% [+0.8%, +4.5%] | 0.005 | **Loses to the close** |
| NBA flag engine | flags_wowy | 141 (93%) | 10 | −3.1% [−6.0%, −0.4%] | −6.4% | +3.3% [+0.6%, +5.8%] | 0.132 | **Loses to the close** |
| NBA side-by-side | T4_TIP30 | 128 (97%) | 7 | −4.1% [−6.4%, −2.8%] | −6.4% | +2.2% [+0.2%, +3.5%] | 0.179 | **Loses to the close** |
| NBA side-by-side | UNDERML | 117 (100%) | 6 | −5.4% [−6.3%, −4.6%] | −5.7% | +0.3% [−0.5%, +1.2%] | 1.000 | **Loses to the close** |
| NBA side-by-side | UNDER20P | 109 (100%) | 6 | −6.2% [−7.8%, −4.8%] | −5.7% | −0.5% [−2.1%, +0.9%] | 1.000 | **Loses to the close** |
| NBA side-by-side | NEWS_DK | 91 (100%) | 5 | −6.2% [−7.8%, −4.8%] | −6.6% | +0.4% [−1.3%, +1.8%] | 1.000 | **Loses to the close** |
| NBA side-by-side | NEW_STARTER | 91 (100%) | 6 | −7.3% [−9.2%, −5.8%] | −5.7% | −1.6% [−3.3%, −0.4%] | 1.000 | **Loses to the close** |
| NBA side-by-side | BOOST_NH | 73 (91%) | 5 | −4.1% [−5.2%, −3.3%] | −6.4% | +2.3% [+0.8%, +3.1%] | 0.005 | **Loses to the close** |
| NCAAF P2 | p2_under_paper | 66 (38%) | 13 | −5.5% [−5.6%, −5.4%] | −5.7% | +0.3% [+0.0%, +0.4%] | 0.179 | **Loses to the close**\* |

\* Only the bets whose line hadn't moved could be scored. See NCAAF below.

- **Every other forward strategy is Insufficient:** under 50 scored bets or under 5 dates. That covers all of golf, the
  NBA tip card, carded and pinged flags, and NCAAF totals and receiving-yards overs.
- **Holm** was run across the 18 strategies with 50+ bets on 5+ dates. A p of 0.005 is the bootstrap floor (1 in 4,000)
  times 18.
- **The null:**
  - NBA and NCAAF: the average CLV of every other prop on the same book, market and side that day, at its main line.
  - Tennis: the no-move baseline, i.e. the CLV if the price had never moved (about minus the hold).
  - NFL: every other alt rung in the same market at the same fetch.

### 1. Tennis Pinnacle-referenced (Strong)
**What it does.** It bets DraftKings (790 of the 816 scored bets) or FanDuel (26) when that book pays more than
Pinnacle's no-vig price. Logged 9/3–10/18; the logger and its collectors were retired on 10/23.

**What we found:**
- **Against DraftKings' own close:** +1.5% [+0.8, +2.3].
- **Against Pinnacle's close:** +6.9% [+5.9, +8.0] on the 651 bets Pinnacle could be matched for.
- **Why that makes sense:** the books it bets move toward Pinnacle by the start. That is the mechanism the strategy was
  built on.

**Checks:**
- **The 71% coverage is a storage artifact.** The DraftKings tennis log stores a row only when a price changes. A quiet
  board for 30+ minutes therefore looks like no observation.
  - Read as change-only, taking the last stored price before the start, coverage is 99%.
  - On that reading: 1,142 bets, +2.1% [+1.5, +2.7]; 9.0 points over the no-move baseline.
- **The logged price was really on the board.** It matches DraftKings' stored price at the moment of logging in 1,102 of
  1,116 bets. Scored at the board price instead, it's +1.8% [+1.3, +2.5].
  - A first pass seemed to show half the prices stale. That was a timestamp quirk: in 54% of bets the capture is stamped
    3–6 seconds after the log time.
- **It all comes from bets placed 3+ hours out:** 703 bets at +2.4%. The 113 bets placed inside 3 hours are negative
  (−2.6% and −6.1%). That's a breakdown, not a tier.
- **ROI (information only):** +7.4% [−0.5, +15.6] on 1,059 graded bets.

### 2. DK_LAGS_FD (Promising)
**What it does.** It bets DraftKings props that lag FanDuel's.

**What we found:**
- **Against DraftKings' own close:** +1.3% [+0.6, +1.8]. Against FanDuel's close: +3.4% [+2.5, +4.0].
- **Why it isn't Strong:** every other Strong test passes, but it has only 7 forward dates against the 10 required.
- **Pre-known:** it was disclosed in the pre-registration as already flagged.
- **Concentration:** overs +2.1%, unders +0.3%; points-type combos +3–5%; threes 0.0%. Breakdowns only.
- **Its development phase** (557 bets, 6 dates) was −0.1%, so the forward phase is the better one.
- **ROI (information only):** +4.7% [+1.0, +12.2].

### 3. Everything that loses to the close
- **The NBA rules and the live flag engine** all close behind the market by about the vig.
- **Some pick better-than-average props:**
  - flags_wowy: +3.3 points over the null;
  - RATIO_PA: +2.1;
  - BOOST_NH: +2.3;
  - RATIO_RC: +1.0.
- **None is close to enough to overcome a ~6% vig.**
- **NULL_TIP30 is the null rule itself.** Its +0.0 over the null is a check that the yardstick works.

### 4. NCAAF: CLV can't really be measured on this data
- **FanDuel's NCAAF props move lines, not prices.** Every scored bet sat at the same ~1.89/1.89 price at the close, so
  a same-line CLV is minus the vig by construction (−5.4% to −6.2%).
- **No validated line-to-probability conversion exists for NCAAF yards.** So a bet whose line moved can't be priced.
  Coverage is 38–71%.
- **The line moves themselves don't favour the bets:**

| Strategy | Line moved toward the bet | Moved away |
|---|---|---|
| P2 unders | 14% | 18% |
| P2 underdog unders | 16% | 17% |
| Receiving-yards overs | 9% | 16% |
| Totals | 12% | 7% (59 bets) |

- **143 P2 and totals bets had no fetch within 30 min of kickoff.** The collector's last pre-kick fetch was often
  30–120 min out.

## Recommendations for further shadow testing (none of this changes anything live)
1. **Tennis Pinnacle-referenced: first in line.**
   - **What it would take:** restarting `pin_live` with the Pinnacle and DraftKings tennis collectors. They were retired
     on 10/23, so this needs your authorization and a crontab plan.
   - **The forward test:** pre-register it with this yardstick, the price on the board at log time, and the 200-bet,
     10-date bar.
   - **Two things to watch:** how fast the DraftKings feed is (a GitHub runner every 5 min), and that the edge sits in
     bets placed 3+ hours out.
2. **DK_LAGS_FD: keep shadowing as is.** It already logs every slate in the side-by-side. Re-tier it once it has 10
   forward dates, which is about 3 more slates. No change is needed.
3. **NBA flag engine (flags_wowy): keep logging; no promotion.** It beats random props but not the close.
4. **NFL alt-tails: no evidence.**
   - Price CLV is about 0 and no better than the other rungs.
   - With every rung kept, it's +0.3% [+0.1, +0.6], with 0.1 [−0.05, +0.3] points over the null.
   - Keep it only if it's free to run.
5. **NCAAF:** before any CLV verdict is possible, it needs a held-out line conversion for yards props (like Step 2a), or
   the collector fetching inside 30 min of kickoff.
6. **The rules that lose to the close with nothing over the null** can be retired from the side-by-side whenever
   convenient: UNDER20, UNDER20P, UNDERML, DEPTH_NEXT_TIP30, NEW_STARTER, NEWS_DK. That's a scoreboard decision, not
   urgent.

## How the existing calculations differ (audit items 1 and 2)

| System | Close time | Reference | De-vig | Moved line | Stored measure |
|---|---|---|---|---|---|
| NBA side-by-side (`nba_replay.grade`) | FanDuel's last observation before tip, any age | FanDuel, even for DraftKings bets | multiplicative | over-only alt rung at the main's overround, else missing (13%) | price CLV |
| `nba_clv.py` | board at tip from the change log | best of FanDuel+DraftKings; main = over nearest 1.9091 | none | binary: line up, or price shorter | beat yes/no |
| NBA flag engine | n/a | best-of-two price logged with no book | n/a | n/a | none |
| `bet_ledger` | game start | Pinnacle (not the book bet) | Shin | Pinnacle at the bet line | price CLV |
| `wnba_clv` | close capture | FanDuel main line | none | line points only | line points |
| `k_live` | last snapshot, 10:00 to 08:00 next day (no first-pitch cap) | best price across books | none | price ratio only on an unchanged line | direction and price ratio |
| Golf (`golf_moves`) | frozen at a per-market tee deadline | FanDuel | none | n/a | open/close prices |
| NFL, NCAAF, tennis | none stored | | | | none |

**Measured agreement on the same bets:**
- **The side-by-side's stored CLV against this audit's FanDuel-close CLV:** rank correlation 0.996 and same sign
  99.7% (7,955 bets). Its definition is sound.
  - Against the same-book close it agrees less: 0.86 and 92%, because DraftKings bets are scored on FanDuel.
  - It covers fewer bets: 87.5% against 96.3% here, because the conversion prices moved lines.
- **`nba_clv.py` against this audit's CLV, on 201 flags:**
  - "beat" agrees in sign 78% of the time;
  - its beat rate is 47%, where the share with CLV > 0 is 30%;
  - a binary beat ignores the vig, so it overstates.

**Other problems found:**
- **Change-only tennis stores (FanDuel, DraftKings)** can't tell a quiet board from a stopped collector. `fd_captured_at`
  is the time of the last change, not when the price was seen, and FanDuel tennis collection ended on 10/18.
- **Golf:** some tee deadlines resolved to the wrong year (Bermuda 2026 outrights → 2024-11-14), so their frozen
  "close" predates the flags. Golf's birdies and round-score markets are two-sided, though this audit's
  pre-registration treated all golf as one-sided.
- **NFL V2:**
  - bet prices come from the Odds API's FanDuel feed, but the close comes from FanDuel's own site;
  - it logs several rungs per player at once, and the pre-registered unit keeps one per player and market (1,352 rungs
    collapsed; the all-rung read agrees);
  - only 99 predictions are graded, 7 of them bets.
- **NCAAF P2** voids 13 bets as `void_no_box_row`. The receiving-yards grader treats a missing box score as 0 yards
  (from the inventory; it didn't affect CLV).
- **Table tennis** rewrites its logged price until the start, so its CLV is about 0 by construction (excluded). The WNBA
  ledger has no flag time (excluded).

## Audit-only systems (stored measure as stored; never tiered)
- **`bet_ledger`** (July, 8 dates): +7.0% on 312 bets against Pinnacle's Shin close.
  - mlb/model +9.0% (197 bets, 3 dates);
  - mlb/direct +4.6% (84, 4 dates);
  - ebasketball −4.6%.
  - Too few dates to read, and the reference is a different book.
- **`wnba_clv`:** firm-tier flags (1,572, 53 dates). The close moved the line toward the projection 23% of the time and
  away 9%. That's +0.19 points on average, with no price value.
- **`k_live`:** 40 rows with a stored CLV across its streams. Too few to read.

## Deviations from the pre-registration (all stated, none changes a tier)
1. **The Mac's live collectors were read in place**, through read-only connections cut at 11/4 03:00 UTC, rather than
   copied. That's the NCAAF store (13 GB), the NFL store (4.4 GB) and both ledgers. Every VM store is a copy and is
   hashed in the result file.
2. **Coverage counts started, non-void bets** rather than graded ones, because the NFL ledger grades almost nothing.
3. **For the change-only tennis stores**, an "observation" is a collector run that stored any change. The change-only
   reading is reported beside it and agrees.
4. **NBA flag engine:** 15 flags the engine itself voided are left out. The 12 side-by-side signals logged as "best"
   get their book inferred the same way as the flags.

## Limitations
- **Short windows.** NBA forward data covers 7 slates, and DK_LAGS_FD is the one rule held back by that.
- **The tennis baseline is the no-move CLV, which is about minus the hold.** That's an easier bar than a matched null.
  The CLV itself, +1.5% against the book's own close and +6.9% against Pinnacle's, is the stronger evidence.
- **Executability.**
  - The DraftKings tennis board came from a 5-minute GitHub runner, and NBA DraftKings checks are 3–9 min apart.
  - A real bettor could find prices gone, or get limited.
  - None of that is measured here.
- **Outside the NBA, a moved line can't be priced.** NCAAF and tennis model results are weak on that account.
- **CLV is not profit.** No strategy here is called profitable.
