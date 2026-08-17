# PRE-REGISTERED HYPOTHESES — fixed BEFORE the evidence exists. Do not edit after the fact.

## PR-001 — the `vac` gate  (registered 2026-08-13, v1.8 untouched)

**CLAIM:** tracked bets whose vacated production pool `vac` is at or below the median (14.7 in
the stat's own units) underperform those above it, and dropping them raises total units.

**RULE (frozen):** drop a tracked bet when `vac IS NOT NULL AND vac <= 14.7`. Rows with vac
NULL are KEPT — no evidence either way. Nothing else changes.

**EVIDENCE SO FAR** — all of it in-sample or sample-burned, which is exactly why this is
pre-registered rather than shipped:

| test | result |
|---|---|
| temporal split | pre +28.3pp, fwd +39.2pp — same direction |
| within proj_min strata | LOW +26.5pp, HIGH +35.7pp — not collinear, corr = +0.030 |
| leave-one-player-out | +26.7 .. +37.4pp — no single player carries it |
| economic, forward | 13-13 / −0.44u → 9-4 / +4.99u |
| **multiple testing** | **z = 2.52; 15 fields screened; Bonferroni needs 2.94. FAILS.** |

**WHY IT COULD STILL BE FALSE:** found by screening 15 fields on n=61, and the forward cut was
used to select it, so it is not a clean holdout. A large effect on a small n is precisely what
a multiple-comparison artifact looks like.

**PROMOTION BAR — all must hold on rows graded AFTER 2026-08-13:**
- n >= 40 newly graded tracked bets
- high-vac hit% exceeds low-vac hit% by >= 10pp
- two-proportion z >= 2.94 on the NEW rows alone
- total units improve vs unfiltered v1.8 on the NEW rows alone

**FAILURE CONDITION:** gap < 5pp, or sign flip, at n >= 40 → REJECTED, recorded in REJECTED.md.

**NOT to be re-tested against pre-2026-08-13 data under any circumstance.** That data found the
hypothesis; it cannot also confirm it.

### PR-001 UPDATE (same day, before any forward evidence)
EXP-008: the vac split REVERSES in the suppressed pool -- tracked +31.5pp vs suppressed
-21.0pp (z=-1.94). A causal "more vacated production = more opportunity" story should hold in
both populations. This is therefore either an INTERACTION WITH THE GATE or noise, and the
volume-recovery use is dead outright (high-vac suppressed = 39.0%, -26.8% ROI).
Prior belief lowered. The promotion bar above is UNCHANGED -- it must still be met on rows
graded after 2026-08-13, and this reversal is a reason to expect it will not be.

## PR-002 — the 8–12h capture window  (registered 2026-08-13, v1.8 untouched)

**CLAIM:** stint-WOWY edge is monetizable at **T-8h to T-12h**, a window where book coverage is
99.5–100% and the model is still *under*-confident, and it decays monotonically to strongly
negative by tip.

**THE CURVE (8 leads, 2025-05-01 → 2026-08-13, real archived prices):**

| lead | hrs | bets | hit% | ROI | calib gap |
|---|---|---|---|---|---|
| t1440 | 24 | 8 | 62.5 | +25.2% | −0.095 |
| t720 | 12 | 18 | 61.1 | +18.9% | −0.067 |
| t480 | 8 | 17 | 58.8 | +14.8% | −0.042 |
| t240 | 4 | 19 | 52.6 | +4.6% | +0.003 |
| t120 | 2 | 21 | 42.9 | −13.8% | +0.105 |
| t60 | 1 | 20 | 35.0 | −31.2% | +0.183 |
| t45 | 0.75 | 20 | 35.0 | −31.6% | +0.181 |
| tip | 0.48 | 21 | 33.3 | −35.0% | +0.199 |

Monotone in BOTH columns across all 8. The calibration gap crossing zero at ~4h is the
mechanism: before that the model is under-confident (edge left on the table), after it is
over-confident (the price has absorbed the information).

**WHY THIS MIGHT STILL BE FALSE — read before believing the levels:**
1. **The per-season split guts the headline.** t720: 2025 is 3-0 (+101.7%) vs 2026 8-7
   (**+2.4%**). t480: 2025 2-1 (+38.0%) vs 2026 8-6 (+9.9%). The strong overall ROI is carried
   by tiny 2025 cells. **The honest recent-season read is roughly breakeven to +10%, not +19%.**
2. n = 8–19 per arm, and the arms SHARE bets (same games, overlapping selections), so this is
   not 8 independent observations and the monotonicity is less improbable than it looks.
3. 8 leads were searched. Multiple-testing applies to the choice of window.
4. This corrects, and therefore supersedes, the earlier conclusion recorded as R2.

**PROMOTION BAR — all must hold on data graded AFTER 2026-08-13:**
- capture prices at T-12h and T-8h prospectively for ≥ 40 qualifying situations
- realised ROI at the chosen lead ≥ +8% on those NEW rows alone
- calibration gap at that lead remains ≤ 0 (under-confident) on the NEW rows
- the monotone ordering vs T-1h holds on the NEW rows

**FAILURE CONDITION:** ROI < 0 at n ≥ 40, or the calibration gap turns positive → REJECTED.

**OPERATIONAL PREREQUISITE (blocking, and cheap):** production currently captures FanDuel
lines continuously but the model only *acts* near tip. Testing this forward needs a
T-12h/T-8h capture-and-evaluate path in the research twin. That is infrastructure, not a
production change, and it does not touch v1.8.

## PR-003 — the 2-out cascade penalty  ❌ WITHDRAWN 2026-08-15 by EXP-022 (see REJECTED.md)
## — text kept below for the record; it is NOT an open hypothesis and must not be graded —

**CLAIM:** situations where exactly TWO players are out underperform both single-absence and
3+-absence situations, and the effect is pre-bet knowable from the out list alone — no
probability variable involved.

**RULE (frozen):** flag a situation as degraded when `count(out_player) == 2`. Nothing else
changes. This is a *research* label; it gates nothing in production.

**EVIDENCE (845 graded rows from wnba_clv, far wider than the 85 tracked bets):**

| cut | 2-out | rest | gap |
|---|---|---|---|
| overall | 43.8% (n=340) | 52.3% (n=505) | **−8.5pp**, z = −2.41 |
| chrono T1 | 48.9% | 51.3% | −2.3pp |
| chrono T2 | 43.5% | 55.7% | −12.2pp |
| chrono T3 | 32.9% | 49.5% | −16.5pp |
| within points | 49.3% | 56.5% | −7.1pp |
| within rebounds | 35.4% | 47.7% | −12.3pp |
| within assists | 45.6% | 51.6% | −6.1pp |

Negative in **3/3 chronological thirds and 3/3 markets**. Six same-sign cuts is stronger than
z alone implies, but the cuts are not fully independent.

**WHY IT COULD STILL BE FALSE:**
1. **z = −2.41 does NOT clear the Bonferroni bar (~2.81) for ~10 variables screened on this
   axis.** It is registered *because* it fell short, not despite it.
2. **The pattern is NON-MONOTONE** — 1 out is fine (52.7%), 2 out is bad (43.8%), 3+ out is
   neutral (51.1%). A genuine "more absence = more mispricing" story would be monotone. A
   middle-bucket penalty is the shape a confound or a noise artifact takes.
3. No mechanism is established. Until there is one, this is a pattern, not a finding.

**PROMOTION BAR — all must hold on rows graded AFTER 2026-08-15** (the evidence above runs
through 2026-08-14, so the cutoff must sit past it):
- n >= 60 newly graded rows carrying an out-count
- 2-out trails the rest by >= 5pp on the NEW rows alone
- z <= −2.81 on the NEW rows alone
- the sign holds in each half of the new window

**FAILURE CONDITION:** gap >= 0, or sign flip, at n >= 60 → REJECTED.

---

## AXIS VERDICT — situation gate without p_adj (EXP-014..020)

The question was whether a situation variable predicts realized market-relative error or
future price movement, independently of p_adj. **Both halves are now answered:**

**PRICE MOVEMENT — YES, robustly.** `corr(proj, clv) = +0.008`, so CLV is orthogonal to the
projection. News recency then predicts it strongly: fresh (<=9h) +0.30 line movement vs stale
(>24h) −0.27, z = 3.19 and 5.47 on independent chronological halves, and it is NOT the
late-flag effect (it is *strongest* within the early-flag stratum, z = 6.69; corr(age, lead)
= +0.301).

**REALIZED OUTCOME — NO.** The same news-age variable does not predict whether the bet wins:
gap +2.9pp, z = 0.57, and the sign FLIPS across halves (−7.2pp / +16.6pp). Market/line-level
splits are chronologically unstable. Only the 2-out cascade survived structurally, and it
misses the correction bar.

**THE STANDING LESSON, SHARPENED:** being early on real information is *true and measurable* —
the market does move toward us — and it still does not convert into profit in this population.
CLV is not a sufficient proxy for edge here. Any future work that validates on CLV alone is
measuring the wrong thing.

**REJECTED ON THIS AXIS (do not re-test):** lead-to-tip vs CLV (corr −0.063, earlier is
*worse*); line-movement-as-selector (57.8% vs 45.4%, z=1.98 — but only knowable after the fact
and gating on the book having reacted violates the speed rule); market and line-level splits
(chronologically unstable).

### ⚠️ PR-002 CORRECTION — 2026-08-15: the forward arm was capturing NOTHING

Registered 2026-08-13. Between then and 2026-08-15 the shadow arm logged **zero rows** while its
`*/20` cron fired normally and its log looked healthy. Cause, found by EXP-027's funnel:

```
mates                        85
projected starter            35
n_without<2 (new ground)      0   <-- every candidate died here
```

The arm carried `if nwo >= 2: continue`, commented "production already covers this". That
captures the n_without<2 tier — the candidates production deliberately never acts on — i.e. the
**complement** of the universe PR-002 is about. PR-002 claims stint-WOWY edge is monetizable at
T-8h..T-13h; that is a claim about WHEN a candidate is priced, not about WHICH candidates
qualify. Testing it requires production's own universe (`n_without >= 2`) observed early.

Gate corrected to `if nwo < 2: continue`. Dry-run on the 2026-08-15 slate: **55 candidates would
be captured**, versus 0 before.

**WHAT THIS COST:** nothing yet, because no rows were graded — but the failure mode is the
dangerous one. The arm was indistinguishable from an arm that is merely *waiting*, and "waiting
for n>=40" is what I would have assumed indefinitely. A capture path that yields nothing and a
capture path that has nothing to yield look identical from outside. `--diag` now exists to tell
them apart without writing a row (verified: 0 rows before, 0 after).

**BAR UNCHANGED. START DATE CORRECTED.** The n>=40 / ROI>=+8% / calibration-gap<=0 / monotone
thresholds are exactly as registered and are NOT being tuned. Only the clock moves: prospective
capture effectively begins **2026-08-15**, since 08-13 and 08-14 captured nothing. Any row
timestamped before 2026-08-15 does not exist and cannot be graded.

**BACKUP:** `research/pr002_shadow.sqlite` holds prospective data that cannot be recreated and
was covered by no backup. Added as a research-only cron at 08:25 UTC, 15 min ahead of the
off-box pull. `wnba_backup.py` was deliberately NOT edited — production stays frozen.

## PR-004 — flagged rungs drift toward the over after the line opens (registered 2026-08-15)

**CLAIM:** rungs the model flags drift toward the over, from the opening price to the last
pre-game price, more than non-flagged rungs on the same days.

**EFFECT (EXP-033, 11-day tick archive, FanDuel, n=209 flagged vs 8,948 non-flagged):**

| | opener → last pre-game |
|---|---|
| flagged rungs | **+0.89pp** |
| non-flagged baseline | **−0.53pp** |
| difference | **+1.417pp, t = +4.34** |
| flagged BEFORE the line opened (n=102) | +1.20pp → **+1.733pp vs baseline, t = +4.22** |

**WHAT IT SURVIVED (EXP-034):**
1. **Mean reversion — the §19 leakage kill-shot — points the WRONG WAY.** Drift by opening-price
   quintile is strongly monotone (cheap overs +1.90pp → expensive overs **−5.11pp**), so a
   price-triggered flag could trivially fake this. But flagged openers average **0.509** implied
   vs 0.406 non-flagged: flagged rungs sit in the EXPENSIVE zone, where drift is normally ~0 to
   negative. The confound predicts the opposite of what was measured.
2. **Outlier trim makes it STRONGER.** Dropping the 5 largest and 5 smallest drifts from each side
   gives +1.364pp at **t = +5.12** (vs +4.34 untrimmed). Not a few big moves.
3. Positive in both usable opening-price quintiles.

**WHAT IT DID NOT SURVIVE — why this is registered, not promoted:**
1. **Heterogeneous and not pre-specified.** Within opening-price quintile only Q3 is significant
   (+1.46pp, t=2.59); Q4 is +0.28pp (t=0.79). Within stat×level only points-mid holds (+2.25pp,
   t=2.35) and **points-high is NEGATIVE** (−0.53pp, t=−1.34). ~8 cells were inspected; Bonferroni
   needs |t| ~2.9, so no subcell clears on its own.
2. **The flag remains price-dependent.** The direction check above is strong evidence, not proof.
   A clean version must select rungs using price-free inputs only (`d_min`, `proj_min` — verified
   price-free: `wnba_wowy.py` has zero `p_market`/`posted_props`/`de_vig`/`shrink` references).
3. **11 days. One book. n=209.**

**🚨 THE CAVEAT THAT MATTERS MOST — DRIFT IS NOT PROFIT.** EXP-018 already established on this
system that market movement does **not** predict bet outcome: news recency predicted CLV at z=5.47
and predicted whether the bet won at z=0.57, with the sign flipping across halves. So a robust
drift finding may be economically worthless. **PR-004 must never be promoted on drift alone**; §29
requires an economic test at the observed entry price.

**PROMOTION BAR — all must hold on rungs opening AFTER 2026-08-15:**
- n >= 120 newly observed flagged rungs
- flagged-minus-baseline drift >= +0.8pp on the NEW rungs alone
- t >= 2.9 on the NEW rungs alone (Bonferroni for the cells already inspected)
- holds within opening-price quintile, not only in aggregate
- **and a positive economic result at the entry price actually available** — drift alone fails it

**FAILURE CONDITION:** difference <= 0, or sign flip, at n >= 120 → REJECTED.

## PR-004 VERDICT — 2026-08-15: the DRIFT is real, the STRATEGY is not. NOT EXECUTABLE.

Tested per §29 at the actually-available entry price, on real settled outcomes.

### TASK 1 — entry at OPEN vs entry at CLOSE, same selections

| cohort | n | hit | at OPEN | at CLOSE | early-entry edge |
|---|---|---|---|---|---|
| all flagged | 204 | 44.6% | −25.67u, **−12.6%** | −30.06u, −14.7% | +2.1pp |
| pre-market flagged | 101 | 49.5% | −3.08u, **−3.0%** | −5.51u, −5.5% | +2.4pp |
| line existed first | 103 | 39.8% | −22.60u, −21.9% | −24.55u, −23.8% | +1.9pp |

**The early-entry advantage is REAL and survivorship-immune** — it is a paired comparison on the
identical 204 rows: open price minus close price = **+0.0281 decimal, t = +2.21**, worth +4.39u.
PR-004's drift finding therefore stands as a *phenomenon*.

**It is not a strategy.** Every cohort loses at both entry points. Entering earlier on a losing
selection loses less; it does not win. +2.1pp cannot close a −12.6% gap. **REJECTED as executable.**

⚠️ **This is NOT the production tracked record.** The 204 rungs are every rung the model flagged
in `clv` — a far wider universe than the TOP-2 selections production actually bets (forward 13-10,
+11.1% ROI, n=22). This result says the BROAD flagged-rung universe loses; it does not contradict
the narrow tracked selection, and must never be quoted as if it did.

### TASK 2 — do pre-market flags carry information the opener lacks? NO POSITIVE SIGNAL

Conditional on opening implied probability (the opener IS the market's probability estimate):

| opener bin | flagged | non-flagged | gap | z |
|---|---|---|---|---|
| ≤0.495 | 39.2% (n=79) | 39.5% (n=924) | −0.3pp | −0.05 |
| ≤0.664 | 47.1% (n=119) | 50.2% (n=806) | −3.2pp | −0.65 |
| pre-market ≤0.495 | 47.6% (n=42) | 39.5% | +8.1pp | +1.05 |
| pre-market ≤0.664 | 48.1% (n=54) | 50.2% | −2.1pp | −0.30 |

Null, with the pre-market cohort flipping sign between bins.

### 🚨 WHY THE NEGATIVE CANNOT BE CERTIFIED EITHER — the DNP-pricing confound

`actual − opener` reads −6.30pp for flagged and **+3.05pp for non-flagged (t=+4.56)**. Taken at
face value that means betting random non-flagged rungs beats their own opening price, which is
absurd. The mechanism: **the opener prices in the chance the player does not play, and grading
only retains players who DID play.** That silently removes priced DNP risk — and removes it
unequally, because flagged rungs are **97.6% graded (204/209)** while non-flagged are **51.7%
(4627/8948)**. Flagged players are beneficiaries who were always going to play, so they gain far
less from the filter, and therefore look worse by construction.

Restricting to `actual>0` does not fix it (that IS the filter). **Within-player matching does not
fix it either** — the within-player difference is −10.87pp (t=−3.25), but a flagged day is by
definition a day that player is certain to play, so the same asymmetry survives the match.

⇒ **Correct verdict: NO POSITIVE INFORMATION DETECTED beyond the opener; the apparent
ANTI-information is confounded and must not be reported as a finding.** Cleanly resolving this
needs DNP-inclusive grading (scratched players graded as unders, which is what the bettor actually
experiences), and the box-score archive does not currently retain the quoted-but-scratched set.
Recorded as a DATA RISK, not a result.

### WHAT SURVIVES FROM PHASE 3
1. Flagged rungs drift toward the over after opening (+1.42pp, t=+4.34; trimmed t=+5.12).
2. That drift is worth **+2.1 to +2.4pp of ROI** as a better entry, paired and survivorship-immune.
3. It is **not enough to make the flagged universe profitable.**
4. The flag carries **no detectable information beyond the opening price.**
