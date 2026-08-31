# REJECTED HYPOTHESES — check before testing anything new
| id | hypothesis | result | why rejected | revisit if |
|---|---|---|---|---|
| R1 | regime-weighting (availability+arrivals+elevated) improves bets | v1.5 +15.54u vs full +10.09u on 182 rows | dropped marginal WINNERS; wowy-only alone dropped 7 bets that went 7-0 | never on ROI alone; only w/ a >+15.54u backtest |
| R2 | ~~stint-WOWY as a live bettor~~ **SUPERSEDED 2026-08-13 by PR-002** | the original verdict measured only opener(48h, 15% coverage) and T-4h(breakeven) and concluded 'edge and liquidity never overlap'. That was WRONG: 8-24h was never measured, and there coverage is 99.5-100% with ROI +14.8%..+25.2% and a NEGATIVE calibration gap | the conclusion was drawn from an unmeasured gap, not from evidence against the window | superseded — see PR-002; note the 2026-only cells are much weaker (+2.4% at 12h) |
| R3 | lower EV threshold to recover volume | 0.07/0.05 both WORSE (+8.76u vs +10.09u) | adds losers faster than winners | no |
| R4 | narrow book to alt ladders | ladders 4-4 fwd vs main 9-6 | all-time ladder edge was in-sample | no |
| R5 | USAGE_RATE_ADJ | tested, rejected pre-freeze | — | — |
| R6 | harder shrink toward book fixes the anti-predictive residual | k=0/5/11 identical; k>=20 strictly worse | shrinking removes the BET, not just the bad probability -- p_adj is both signal and gate | only with a situation-gate that does not route through p_adj |

## PR-003 WITHDRAWN — 2026-08-15, same day it was registered (EXP-022)

Registered on a −8.5pp gap that was negative in 3/3 chronological thirds and 3/3 markets, with
the stated caveat that it was NON-MONOTONE and had no mechanism. The mechanism test killed it.

**WHY IT WAS NEVER A REAL HYPOTHESIS: out-count and vacated minutes are near-collinear.**

| outs | vacated minutes | hit% |
|---|---|---|
| 1 | 25.9 | 52.9% |
| 2 | 53.2 | 43.8% |
| 3+ | 77.3 | 51.1% |

"How many are out" and "how much production is vacated" are the same variable measured two
ways. You cannot control one for the other, and you cannot register them as two independent
findings — which is precisely what PR-001 (low-`vac` penalty) and PR-003 would have been.

**THE DECISIVE NUMBER.** Stratified on vacated minutes, the one stratum with BALANCED
comparison groups shows no penalty:

- HIGH vac: 2-out 49.5% (n=107) vs rest 51.1% (n=131) → **−1.6pp, z = −0.25**
- MID vac: 2-out 41.2% (n=233) vs rest 64.5% (**n=31**) → −23.3pp, but the comparison cell is
  31 rows hitting 64.5%, which is not a population, it is noise with a decimal point
- LOW vac: n=0 on the 2-out side — the strata cannot even overlap

The headline −8.5pp came from comparing 2-out situations against a *mixture* of low-vac 1-out
and high-vac 3+ groups. Same-sign consistency across 3 thirds and 3 markets did not save it,
because the confound is present in every cut.

**THE TRANSFERABLE LESSON — consistency across cuts is NOT evidence against a confound.** Six
same-sign slices felt like strong corroboration. They were six views of one collinearity. A
confound that lives in the variable itself reproduces in every subgroup you draw. What actually
discriminated was stratifying on the *suspected cause* and checking whether the comparison
groups were balanced inside each stratum. Do that before registering, not after.

**INCIDENTAL, AND A CAUTION FOR PR-001 — NOT a change to its frozen bar.** On this wide 836-row
population, holding out-count fixed, the vac effect is much smaller than the +28..+39pp PR-001
found on 61 tracked bets: **+8.0pp (z=+1.49) within 2-out, +1.4pp (z=+0.27) within 1-out.**
Direction agrees; magnitude does not. That is what a small-n selection effect looks like.
PR-001's promotion bar is UNCHANGED and remains forward-only on tracked bets — this is
retrospective context on a different population, recorded so the eventual forward read is
interpreted against a realistic prior rather than the inflated in-sample one.

## EXP-026 — THE SITUATION CARRIES NO SIGNAL (2026-08-15)

**The axis was: can a situation-level gate work without `p_adj` or any probability-derived
ranking? The answer is NO, and not because the gate was built badly — because the situation
itself is not informative.**

Flagged selections vs non-flagged market main lines, 2026-08-05..08-14, on a reconstructed
11-day line archive:

| | flagged | non-flagged main | gap |
|---|---|---|---|
| ALL | 44.4% (n=277) | 44.3% (n=734) | **+0.1pp, z=+0.04** |
| points | 44.2% (n=113) | 44.2% (n=285) | +0.0pp |
| rebounds | 47.4% (n=95) | 46.5% (n=243) | +0.9pp |
| assists | 40.6% (n=69) | 41.7% (n=206) | −1.2pp |

Zero in every market. **Identifying the beneficiary of an absence is worth 0.1pp.**

This CORROBORATES and quantifies the existing finding that big WOWY/usage/minutes deltas are
not what makes a beneficiary over hit. It extends it from the tracked pool to a 1011-row
like-for-like comparison with a real baseline.

**THE STRATEGIC CONSEQUENCE.** Whatever edge the tracked system has cannot be coming from
situation identification. It has to come from the PRICE side — the EV gate and the TOP-2
ranking — because the situation pool it draws from is indistinguishable from random. Research
effort spent on better situation variables is spent on a channel measured at +0.1pp. Every
future situation-variable hypothesis inherits this ceiling and should be scoped against it.

### ⚠️ EXP-023 and EXP-024 ARE VOID — and how they lied

Both reported the flag beating the market by **+12.8pp (z=5.53)** and **+12.0pp (z=2.54)**.
Both were wrong, for two independent reasons, and both looked healthy:

1. **`wnba_lines.sqlite` is a 3-DAY ROLLING BUFFER.** 1.5M rows spanning 2026-08-13..08-15 ONLY.
   Querying `WHERE date BETWEEN '2026-07-12' AND '2026-08-14'` returns rows and raises no error
   — it silently answers about 2 days while appearing to answer about 34. Row COUNT looks
   enormous (1.5M) precisely because a buffer is dense, not long. **Always check
   `COUNT(DISTINCT day)`, never `COUNT(*)`, before trusting a window.**
2. **The market pool was the ALT LADDER.** One player's 2.5 main line also appears at 4.5/5.5/6.5.
   The tell was a monotone slide in over% with line level inside every stat (assists 62.9 → 51.3
   → 39.5 → 25.0 → 13.2%). Comparing our selections to that pool compares main lines against
   longshots and manufactures a large fake edge.

**The gate that caught it:** a main line must hit ~47-48% overs after vig. EXP-024's pool
measured 40.5%, which is not a base rate, it is a defect. That single check is now mandatory
before any market-relative claim — it is cheap, it is outcome-independent, and it would have
killed both experiments before they were written up.

**INFRASTRUCTURE BUILT:** `research/build_line_archive.py` → `research/line_archive.sqlite`,
19,287 rows / 11 real days (2026-08-05..08-15), reconstructed by unioning the daily backups
(each itself a 3-day window). One row per (date, player, stat, line, side) = last pre-game
quote. This is the only WNBA line history that exists; the live DB cannot answer any question
spanning more than 3 days. Research-only, imported by nothing in production.

## PR-002 REJECTED — 2026-08-26 (931 graded rows, bar was n>=40)

**It passed the LETTER of its bar and is still rejected. The bar was underspecified — that is my
error, recorded below so the next pre-registration does not repeat it.**

Letter-of-the-bar check: best bucket t10, ROI +10.83%, n=299, calibration gap −6.29pp → all three
testable conditions PASS. Then the §40 audit:

| audit | result |
|---|---|
| **the registered thesis** | **FALSIFIED.** PR-002 claimed MONOTONE decay — earlier is better, t12 > t10 > t8. Forward: **t12 +1.01%, t10 +8.54%, t8 +6.32%.** t12 is the WORST bucket, the reverse of the claim. |
| **concentration** | **top 5 bets = 93% of all profit** (+23.70u of +25.52u). Remove them and it is **+1.82u, ROI +0.62%**. |
| **significance** | clustered on slate: t = **+0.88**, 95% CI **[−13.3%, +34.9%]** — contains zero. Per-slate ROI: +100, +38, +29, +23, +9, +8, −3, −14, −37, −42. |
| **selection** | I picked the best of 3 buckets post hoc. With 3 draws the max is biased up ~0.85·SE ≈ **10.4pp** — essentially the entire headline. |
| what it actually bet | mean price **2.98**, hit **41.1%**, breakeven 33.6% — longshot alt rungs, not the main-line thesis. |

**⚠️ TWO DEFECTS IN MY OWN BAR — fix these in every future pre-registration:**
1. **No significance requirement.** "ROI >= +8%" can be met by noise at n=10 slates. Every future
   bar must state a clustered t threshold, not a bare ROI number.
2. **The lead bucket was never pre-specified.** "ROI at the chosen lead" let me choose the winner
   after seeing all three. A bar must name the arm BEFORE the data exists, or test all arms jointly.
Add: a bar should require the result to survive removing the top-N winners, since 93%-from-5-bets
is not an edge.

**The retrospective curve that motivated PR-002 does not replicate.** It showed monotone decay
across 8 leads (t1440 +25.2% → tip −35.0%). Prospectively the ordering is gone. That retrospective
curve was already flagged as carried by tiny 2025 cells; this confirms it.

**Do not rebuild the "bet earlier in the window" thesis** without a mechanism and a bar that
names its arm in advance. The shadow arm and its cron may keep running — capture is cheap and the
data is reusable — but the hypothesis is closed.

Related: this is the same shape as [[PR-004]] (real drift, no executable edge) and the WNBA house
lesson that edge lives in PRICE, not in refining the thesis.

## MINUTES DE-BIAS — PROPOSED AND REJECTED BEFORE REGISTRATION (2026-08-30)

Proposed after the valuation audit found projections running **+0.64 points optimistic**
(t=+3.26, stable across both chronological halves), with minutes over-projected at every band
(+1.26 / +1.60 / +2.33). For an OVERS-ONLY system an upward bias is directionally harmful, so
correcting it looked like the one fixable lever the error decomposition left open.

**It is not. Two measurements killed it:**

**1. The bias is in a cohort we do not bet.** Split by confidence tier, the entire effect is
`bench` (+1.62, t=+6.31) and `projected`. `confirmed` is unbiased at −0.14.

| cohort | points bias | t | n |
|---|---|---|---|
| confirmed + likely (what we bet) | **−0.09** | −0.32 | 429 |
| rows that became actual ledger bets | **−0.31** | −0.50 | 103 |
| bench + projected (NOT bet) | **+1.61** | +6.45 | 324 |

The 2026-07-29 role gate already removed bench/projected from the bet path — the ledger's last
`bench` row is 2026-07-29 and last `projected` is 2026-07-28, versus `confirmed`/`likely` on
2026-08-30. **The gate fixed this a month ago.** The global +0.64 is an artifact of pooling a
cohort that never reaches a bet.

**2. ⚠️ CORRECTING MINUTES WOULD MAKE IT WORSE.** On the tiers we bet, minutes ARE still
over-projected (+0.69, t=+2.52) — yet the resulting STAT projections are unbiased (points −0.09).
The minutes error is being **offset by an under-projected rate**; the two cancel. Subtracting the
minutes bias would break the offset and introduce a NEW negative bias into every stat projection,
making an overs-only system systematically under-project and stop firing on good bets.

🔑 **THE LESSON: a bias measured on the full projection log is not a bias on the BET population.**
Always re-measure on the post-selection universe before correcting anything — and when two errors
cancel, fixing one of them is strictly worse than fixing neither. Related:
[[feedback_fit_on_post_selection_universe]].

**WHAT THE AUDIT DID ESTABLISH (keep this):** our projection error and the book's line error are
statistically identical — |proj err| 5.26 vs |line err| 5.21, paired t=+0.22, our projection closer
on 48% of rows. **Valuation is already market-grade and cannot be improved by projecting harder.**
The residual is noise (bias/noise ratio 0.06–0.12), not correctable error. Edge must come from
PRICE (line shopping +3.31pp, base rungs) or from finding where the BOOK's line is biased — not
from out-projecting a market we already match.

## "WHERE IS THE BOOK'S LINE WRONG?" — UNANSWERED, and why (2026-08-30)

Four attempts, three real bugs found in my own analysis, no finding. Recording so the next attempt
starts past these rather than repeating them.

**The apparent result each time:** longshot rungs (implied < 0.24) hitting far above their price —
peaking at **+195% ROI, t=+11.4**, broad across 93 players with no concentration (top player 3% of
winners), surviving on players who actually played. Every property of a real finding.

**It was data corruption, all four times.** The bugs, in the order they were found and fixed:

1. **DNP-pricing confound.** Grading only players who appeared refunds scratch risk the price
   charged for. Fixed by constructing the quoted-but-scratched set (tick_archive has every QUOTED
   player-day; box_actuals says who PLAYED) and grading scratches as over-losses — which is what
   the bettor experiences. This un-blocks a question memory had marked BLOCKED.
2. **`tick_archive.d` is the COLLECTION date, not the GAME date.** Books post days ahead, so
   quotes for a future game were graded against today's box and counted as scratches — **49.3%
   scratched**, an impossible number. Fixed by requiring the player's TEAM to appear in that day's
   box before a scratch can be inferred. Scratch rate fell to a plausible 10.8%.
3. **Stale rungs.** Taking the last quote of the day admits rungs the book never refreshed.
   Production applies `FRESH_MIN = 10`; the analysis did not. Dropped 1,009 rungs.
4. **🚨 THE REAL ONE — 28.3% OF LADDER SNAPSHOTS ARE NON-MONOTONE.** A ladder must have longer
   prices at higher lines. In 10,707 of 37,876 player-stat snapshots it does not:
   `Hamby points 2.5@4.60 4.5@14.50 7.5@1.09 9.5@1.24` — the LOWEST rungs carry the LONGEST
   prices. Those phantom rungs (a 13-point scorer priced at o4.5 @ 14.50) are exactly what
   produced the fake edge.

**PRODUCTION IS NOT AFFECTED — the guard exists and works.** `posted_props` calls `_drop_inverted`
("strip arithmetically impossible rungs before ANY consumer sees them"). Verified: **0 of 16**
ladders it currently returns are non-monotone, **0** tracked bets carry the corrupted signature
(line<=5.5 at odds>=4.0), and every tracked bet's price is sane (points 1.57-3.50). The corruption
lives in raw `fd_lines`; the model never sees it.

🔑 **RULE FOR ALL FUTURE RESEARCH: `tick_archive` / `line_archive` / raw `fd_lines` are UNFILTERED.
Any analysis reading them directly must re-apply the production guards — monotonicity, FRESH_MIN,
and game-day matching — or it will measure the corruption and report it as an edge.** The research
archives were built to preserve everything, which is right for storage and wrong for analysis.

**The question itself remains open.** Nothing here says the book is or is not mispriced; it says
this data cannot answer it until filtered. Related: [[reference_dnp_pricing_confound]],
[[reference_silent_zero_failures]], [[feedback_real_lines_only]].
