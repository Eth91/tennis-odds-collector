# PRE-REGISTRATION: one CLV yardstick across the paper-betting systems

**Written:** 2026-11-04, before any strategy-level CLV is computed or read for this audit. Committed and pushed as
7d2f5b2379 at 03:32 UTC (21:32 CST on 11/3). `clv_audit.py`, Mac only, read-only.

**User:** "Before examining strategy-level results, document and commit a clear analysis methodology to prevent
hindsight-driven selection." Nothing here bets, pings or changes a live system. CLV alone is never called profit.

## What was already known before writing this (disclosed so it can be discounted)
- **The NBA side-by-side scoreboard** has been read in earlier sessions:
  - NULL_TIP30 is about −5.6%;
  - the injury rules are −4.5% to −6.5%;
  - DK_LAGS_FD is +3.6% CLV on 997 signals.
  - Those used the scoreboard's own CLV (FanDuel's close, missing when the line moved).
- **Step 2a dropped two injury-window candidates** at −5.4% and −4.0% full CLV.
- **The `nba_clv.py` docstring** quotes a WNBA figure: bets beat the close 67% of the time.
- **No other system's CLV** has been looked at in this session.
- **DK_LAGS_FD is therefore a pre-known candidate.** It gets no special treatment, and the report flags this.

## Inventory and snapshots (counts and schemas only were read)
See the `Systems` section below.
- 21 non-NBA ledgers were found by a read-only inventory that opened no result files.
- Every store is a read-only copy.
- The VM's nightly backups are SHA-256-checked against their manifest.
- Live files are copied once, by scp, when nothing writes them, and checked with `PRAGMA quick_check`.
- Paths and hashes are recorded in the result.

## The unit
- One bet is one strategy signal at the price it logged.
- If a system logged the same (strategy, game, player or runner, market, side, book) more than once, only the earliest
  counts. Duplicates are counted.
- **Development vs forward:**
  - development or backfilled signals (before a rule's registration, or marked development by its system) are
    reported separately and are never evidence;
  - only forward signals, logged live after the rule was frozen, are ranked.

## Canonical CLV (one definition for every bet the data allows)
- **CLV** = q × o − 1, where:
  - o is the bet's decimal price;
  - q is the no-vig closing probability of the bet's side at the bet's line.
- **No-vig:** multiplicative on the two-sided rung: p_over = (1/o_over) ÷ (1/o_over + 1/o_under). That's the
  codebase's own rule.
- **The close, in order of preference:**
  - **Primary: the same book's close.**
    - It's the book's last successful observation before the start (tip, kickoff or first serve).
    - It must be no more than 30 min before the start; otherwise it's missing.
    - The main line is the two-sided rung whose no-vig over is closest to 50%.
  - **Secondary, NBA: FanDuel's close,** the sharper of the two collected books and the side-by-side's yardstick.
  - **Secondary, other systems: Pinnacle's close** where the system collected it.
- **A different line at the close:**
  - **NBA props in points, rebounds, assists, threes, PRA, P+R, P+A and R+A:** q comes from the frozen Step 2a
    conversion (negative binomial; parameters in `audit/inj_step2a/result.20261103.json`, commit 7da9e0597e). It passed
    its held-out gate in all 8 markets.
  - **Every other market and sport:** there's no validated conversion. CLV is computed only when the close has a
    two-sided rung at the bet line. Otherwise it's missing and counted, and the line move in units is reported apart.
- **Excluded and counted:**
  - bets graded void (DNP or retirement);
  - props pulled at the close;
  - bets with no close in the window.
- **Coverage is reported for every strategy:** CLV-scored bets over graded bets.

## Baselines (what "beating the close" has to beat)
- **NBA matched null:**
  - **The set:** at the book's observation at or before each bet, every other prop on the same book, market and side,
    for games that day that hadn't started.
  - **Its CLV:** each prop is taken at its main line and price and scored with the same canonical CLV.
  - **The bet's null value** is the set's mean.
  - **Excess** = bet CLV − null value, paired per bet.
- **Other systems:**
  - the same matched null where the stored odds history has the full board at bet time;
  - otherwise a **no-move baseline**: the bet's own book's no-vig price at bet time, at the bet line, times o, minus 1.
    That's what CLV would be if the market never moved. Excess = CLV − no-move CLV.
  - Where neither exists, there's no baseline, and the strategy can't reach the top tiers.

## Statistics
- **Means** of CLV, null and excess.
- **Intervals:** 95% date-clustered bootstrap, 4,000 resamples, seed 7 (`nba_proj_eval.boot_ci`).
- **One-sided p** for "mean excess ≤ 0": the bootstrap share of resample means ≤ 0, floored at 1/4,000.
- **Multiplicity:** Holm–Bonferroni across every forward strategy with 50+ CLV-scored bets on 5+ dates, at
  family-wise 0.05.
- **Shrinkage** (reported, not a gate): an empirical-Bayes normal-normal shrink of each strategy's mean excess toward
  the across-strategy mean. τ² comes from the method of moments, floored at 0. It shows how much of each mean is
  noise.

## Evidence tiers (fixed now; forward signals only)

| Tier | Needs all of |
|---|---|
| **Strong** (first in line for shadow testing) | 200+ CLV-scored bets on 10+ dates; mean CLV > 0 with the interval's low end > 0; mean excess > 0 with the low end > 0; Holm-adjusted p < 0.05 |
| **Promising** (keep shadowing) | 50+ bets on 5+ dates; mean CLV > 0 and mean excess > 0; the excess interval's low end > 0 before adjustment. It fails a Strong requirement. |
| **No evidence** | 50+ bets on 5+ dates, not Promising, and the CLV interval's high end ≥ 0 |
| **Loses to the close** | 50+ bets on 5+ dates and the CLV interval's high end < 0 |
| **Insufficient** | fewer than 50 bets or 5 dates. Reported, not judged. |

- **A strategy with no baseline** is capped at Promising, and is judged Promising only on CLV itself: mean CLV > 0
  with the interval's low end > 0.
- **Level C** (price CLV) is capped at Promising.
- A strategy whose coverage is under 70% is capped at Promising, and the coverage is stated. Missing closes are often
  moved lines.

## The audit of the existing calculations
For every system that stores its own CLV or beat-the-close:
- its definition (close time, reference book, de-vig, line handling);
- the agreement with the canonical CLV, bet by bet: rank correlation, mean difference, and the sign-agreement rate;
- the coverage difference.

Inconsistencies are listed as found.

## Breakdowns
- by strategy × book, market, side or bet type, and time before the start (NBA: under 30 min, 30 min to 3 h, 3 h+);
- sample size is shown on every row;
- no breakdown cell is ranked or tiered. Only whole strategies are.

## Systems and how each is scored (fixed now)
**Level A: canonical CLV and a matched null.**
- **NBA side-by-side** (`nba_sxs.sqlite` signals, VM copy 2026-11-03 12:57 UTC):
  - every rule;
  - its own phase (forward / development);
  - the book it logged;
  - the close from the 11/3 `nba_lines` backup.
- **NBA live flag engine** (`nba_shadow` 11/3 backup):
  - **the strategies:** flags by tier, flags carded, flags pinged, and the tip card (card = 1);
  - **the price:** the logged best-of-two over price, with its book inferred by matching FanDuel's and DraftKings'
    over at that line at the flag time (FanDuel on a tie);
  - **no match:** the bet is scored on FanDuel and counted.
- **NCAAF P2 under** (`ncaaf_p2_ledger.paper_bets`, two arms):
  - the price at the flag;
  - the close and the null from FanDuel's `fd_quotes` snapshots (Mac `collectors/ncaaf_fd_prices.sqlite`);
  - the close is the last fetch before kickoff, within 30 min.
- **NCAAF totals** (`paper_totals`): the same store, game totals. Same line only, since there's no conversion for
  totals.
- **NCAAF receiving-yards over** (VM `ncaaf-rec-over/live_ledger.picks`): the close and the null from the VM's
  `ncaaf_fd_prices` (a copy).

**Level B: canonical CLV and the no-move baseline (moneylines).**
- **Tennis moneyline forward test** (`ml_ledger.bets`, FanDuel).
- **Tennis Pinnacle-referenced** (`pin_bets`; DraftKings and FanDuel).
- **For both:**
  - the close is the same book's last quote before the start, within 30 min, from `tennis_fd.sqlite` (`fd_tennis`,
    `dk_tennis`);
  - Pinnacle's close (`pin_tennis`) is the secondary read;
  - players are joined by name within the event. Unmatched bets are counted.

**Level C: one-sided markets, a same-rung price CLV, capped at Promising.** These can't be de-vigged two ways.
- **The measure:** price CLV = o_bet ÷ o_close − 1, on the same book and the same rung.
- **NFL V2 alt-tails** (`nfl_v2_ledger`, bet = 1):
  - the close comes from FanDuel's `fd_quotes` in `nfl_prekick_prices.sqlite`;
  - **the null:** every other alt rung in the same market at the fetch at or before the bet, over side, with the same
    price CLV.
- **Golf PGA paper** (`pga_paper.flags`):
  - the close is the frozen pre-tee FanDuel price in `golf_moves.moves`;
  - there's no null.

**Level D: audit only.** The stored measure is described and reported as stored, and is never tiered.
- `bet_ledger` (Pinnacle Shin close);
- `wnba_clv` (line points toward the projection);
- `k_live` (direction and price ratio, best across books).

**Excluded, with the reason recorded:**

| System | Reason |
|---|---|
| WNBA firm ledger | no flag time, only a slate date |
| WNBA stint and PR-002 shadows | research shadows with no stored price or close |
| Tennis set-shape | never staked |
| MLB K-over and walks paper | no closing data for their books beyond 4 days |
| fbe market ledger, NFL inactives, NCAAF rb-rush, options | no bets, or one |
| Table tennis | the logger rewrites the price until the start, so CLV is near 0 by construction; the live host wasn't accessed |

**Dates for clustering:** the game's ET date (NBA, NCAAF, NFL), the match's UTC day (tennis), the flag's UTC day
(golf).

**Forward:**
- NBA side-by-side: its own phase.
- Every other ledger row was logged live, so it all counts as forward.
- The live flag engine's tiers changed over time (`wowy_v0` → `wowy`). Each tier is its own strategy.

## What the report won't do
- It won't call anything profitable.
- **ROI** is shown with its interval as information.
- **Recommendations** are only about which strategies merit further shadow testing, and each follows from its tier.
- **No live change.**

## Result (committed as 553eb0c871 at 2026-11-04 04:01 UTC, after the run; see `CLV_AUDIT.md`)
- **Strong:** tennis Pinnacle-referenced, +1.5% [+0.8, +2.3] CLV on 816 bets over 41 dates, against the book's own close.
- **Promising:** DK_LAGS_FD, +1.3% [+0.6, +1.8] on 943 bets. It had only 7 forward dates; the pre-known candidate.
- **No evidence:** NFL alt-tails.
- **Loses to the close:** 15 strategies.
- **Insufficient:** everything else.
- **Deviations** are listed in the report. None changes a tier.
