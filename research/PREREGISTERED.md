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

## PR-002 — the 8–12h capture window  ❌ REJECTED 2026-08-26 (see REJECTED.md)
## — thesis falsified: decay is NOT monotone forward; 93% of profit from 5 longshots —

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

## PR-005 — base-rung-only (collapse the alt ladder)  (registered 2026-08-26, v1.8 untouched)

**CLAIM:** within a player-game-stat the model should take ONE bet — the rung nearest even money —
and the additional ladder rungs it currently stacks on top are a net drag.

**RULE (frozen, deterministic, outcome-independent):**
> Group tracked overs by `(pred_date, player, stat)`. Keep exactly the ONE rung minimising
> `abs(odds - 2.00)`. Drop every other rung in the group. Ties break to the LOWER line.
> Nothing else changes — same flags, same gates, same TOP-2.

**WHY THIS DEFINITION AND NOT THE OTHER ONE.** The obvious alternative is "keep rungs where the
book posted both sides" (`odds_other > 1`). Rejected as unfreezable: `odds_other` is present on
only **59% of forward rows** (83% pre-freeze — it was backfilled for rows logged before
2026-07-13, so history overstates future coverage), and it would drop whole player-stats rather
than collapse a ladder. It is also not a clean proxy for line position: one-sided rungs price as
short as 1.80–1.93. The two definitions agree on only **22/26** forward groups, which is exactly
why one had to be chosen BEFORE grading rather than after.

**EVIDENCE (forward, since the 7/31 freeze, under the frozen Definition B):**

| | record | hit% | units | ROI |
|---|---|---|---|---|
| **base rungs only** | **20-11** | 64.5% | **+7.43u** | **+24.0%** |
| alt/ladder rungs only | 3-9 | 25.0% | −5.51u | −45.9% |
| all rungs (status quo) | 23-20 | 53.5% | +1.92u | +4.5% |

Cross-check under Definition A: base 16-10 / +16.1%, alts 7-10 / −13.3%. Same sign, weaker
magnitude — so the honest range is **+16% to +24%**, not a point estimate.

**WHY IT COULD STILL BE FALSE:**
1. **Found by slicing the same forward sample it would be judged on.** This is the single reason it
   is pre-registered rather than shipped.
2. **The "alts lose" half is nearly all noise.** n=12 graded alt rungs forward. −45.9% on 12 bets
   is not evidence of anything. The load-bearing half is "base rungs win", n=31.
3. **Alts are SUPPOSED to hit less.** They are longshots (avg odds 2.55–2.77, breakeven 36–39%).
   Judge on ROI, never hit% — a lower hit rate at a longer price can still be correct.
4. **It cuts volume ~30–40%**, and volume is already the binding constraint on total units
   (1.67 bets/day, +0.037u/day). A higher ROI on fewer bets can still mean FEWER UNITS.
   That is why the bar below is written on units, not ROI alone.
5. Related but separate: the min-gap-suppressed rungs went 11-6 (+29.9%). Do NOT fold that in —
   it is a different rule and would be a second unregistered slice.

**PROMOTION BAR — all must hold on rows graded AFTER 2026-08-26:**
- n >= 40 newly graded base rungs
- base-rung ROI >= +8% on the NEW rows alone
- base rungs beat alt rungs by >= 15pp ROI on the NEW rows alone
- **total units of the FILTERED book >= total units of the UNFILTERED book on the same slates**
  (the volume-cut test — this is the one that can fail while ROI looks fine)
- t >= 2.9 on the base-vs-alt ROI difference (Bonferroni for the ~6 slices already inspected)

**FAILURE CONDITION:** base-rung ROI <= 0, or the filtered book returns fewer units than the
unfiltered book, at n >= 40 → REJECTED, recorded in REJECTED.md.

**NOT to be re-tested against pre-2026-08-26 data.** That data found the hypothesis; it cannot
also confirm it.

### ⚠️ PR-005 AMENDMENT — 2026-08-26, before any forward row was graded

**Requested: pre-register the min-gap rule separately. REFUSED — it is the same effect as PR-005,
and registering it twice would repeat the PR-003/PR-001 collinearity error.**

The min-gap-suppressed rungs went 11-6 (+29.9%), which looked like an independent finding pointing
the OPPOSITE way to PR-005 (PR-005 removes extra rungs; relaxing min-gap adds them back). Both
cannot be true as stated. Testing distance from the nearest-even line resolves it:

| distance from base line | all-time | forward |
|---|---|---|
| **0.0** | 53-29, **+28.1%** | 20-11, **+26.3%** |
| +1.0 | 13-8, +14.8% | 7-7, −7.6% |
| +2.0 | 3-6, −21.5% | 1-4, −43.0% |

Min-gap-suppressed rungs have **median distance 0.0** (mean 0.2, max 1.0); taken non-base rungs
have median 1.0 (mean 1.7, max 4.0). So the suppressed rungs won *because they sit at the base*.
`wnba_slip.py:735` claims "Base rung always kept", but the rule keeps the highest-EV rung, which is
not always the one nearest even money — **min-gap sometimes drops the true base rung.** One effect,
not two: value decays monotonically with distance from the base line.

**THE DEFECT THIS EXPOSES IN PR-005 AS FROZEN.** The rule selects from `kept`, which is already
post-min-gap. A rule that picks "the rung nearest even money" cannot do so if min-gap has already
removed that rung. The rule was mis-specified, so the universe is corrected:

> **AMENDED RULE:** apply the selection to the candidate set BEFORE min-gap suppression
> (`kept + min-gap-dropped`). Group by `(pred_date, player, stat)`, keep the ONE rung minimising
> `abs(odds - 2.00)`, ties to the lower line. Everything else in PR-005 is unchanged.

**This is a specification fix, not tuning.** The justification is structural — the rule must be
able to see the rung it is defined to pick. For full disclosure the amended universe also scores
better (forward +26.3% vs +24.0%, +8.15u vs +7.43u), but the two produce **identical 20-11
records**; they differ on 16 of 43 picks and grade the same, so the entire gap is PRICE, not
selection. The amendment is worth ~0.7u forward and would not change a single win or loss.

**THE PROMOTION BAR IS UNCHANGED** (n>=40 new base rungs, ROI>=+8%, base beats alt by >=15pp,
filtered units >= unfiltered units, t>=2.9). Amended before any forward row was graded against it;
nothing has been re-tested to fit.

**Separately recorded, NOT registered:** the +1.0 distance bucket is all-time +14.8% but forward
−7.6%. It is the marginal case and it flipped sign across the freeze. Do not build a "take rungs
within +1" rule on it.

## PR-006 — relax the per-team cap from TOP-2 to TOP-3  (registered 2026-08-26, v1.8 untouched)

**CLAIM:** the 3rd-best play on a team-game is profitable enough that taking it ADDS UNITS, even
though it lowers ROI. Volume is the binding constraint (1.67 bets/day, +0.037u/day), so a
positive-ROI addition is worth more than a higher percentage on fewer bets.

**RULE (frozen, and the arm is named IN ADVANCE):**
> Raise the per-team-game disjoint cap from 2 to **exactly 3**. Rank candidate players within a
> team-game by `ev` descending, one entry per PLAYER (not per rung). Admit rank 3. **Do NOT admit
> rank 4 or beyond.** Everything else unchanged.

Evaluated on the **base-rung** universe (one rung per player-stat, nearest even money), which makes
this **orthogonal to PR-005**: PR-005 acts WITHIN a player-stat, PR-006 acts ACROSS players. If both
promote they compose; neither is evidence for the other.

**EVIDENCE (base rungs, displaced plays ranked within their team-game):**

| | record | hit% | units | ROI |
|---|---|---|---|---|
| rank 3 (what TOP-3 adds) | 13-9 | 59.1% | **+4.34u** | +19.7% |
| rank 4 (NOT registered) | 0-4 | 0.0% | −4.00u | −100.0% |
| current TOP-2 book | 53-29 | 64.6% | +23.06u | +28.1% |
| **combined TOP-3 book** | 66-38 | 63.5% | **+27.40u** | +26.3% |

Forward slice: rank 3 is 3-2, +0.94u (n=5). **Five bets — carries no weight; listed for
completeness only.**

**WHY IT COULD STILL BE FALSE:**
1. Found by slicing existing data, n=22 all-time. +19.7% is not distinguishable from 0 at that size.
2. **The within-team-game ranking shows NO measurable skill** — where a chosen and a displaced play
   both graded, the chosen one returned more in only **7/21 (33%)**, z=−1.53. If the ranking cannot
   order plays, "rank 3" is a near-arbitrary label and rank-3 results may not generalise.
3. rank 4 at 0-4 is **n=4 and proves nothing** — it is the reason the rule stops at 3 by
   construction, not by evidence.
4. Adding bets adds variance and correlated exposure (a third bet on the same team-game shares
   pace, officiating and game script with the first two).
5. DNP-pricing confound applies in principle; both pools are model-flagged beneficiaries so scratch
   risk should be similar, but this is NOT a paired comparison.

**PROMOTION BAR — all must hold on rows graded AFTER 2026-08-26:**
- n >= 25 newly graded rank-3 base rungs
- rank-3 ROI >= +5% on the NEW rows alone
- **clustered-by-slate t >= 2.5** on rank-3 ROI (PR-002 lesson: a bare ROI figure is satisfiable
  by noise; the bar must name a significance threshold)
- **TOP-3 book total units > TOP-2 book total units on the SAME slates** — the economic test, and
  the one that can fail while ROI looks fine
- **survives removing the 3 largest winners** (PR-002 lesson: 93%-of-profit-from-5-bets is not an
  edge)

**FAILURE CONDITION:** rank-3 ROI < 0, or TOP-3 units <= TOP-2 units, at n >= 25 → REJECTED.

**SEASON NOTE:** at ~3 slates/week and a regular season ending in ~2 weeks, n>=25 will almost
certainly NOT be reached in 2026. This bar is expected to carry into the NBA port. Do not lower it
for convenience — a bar met early by shrinking it is not a bar.

**NOT to be re-tested against pre-2026-08-26 data.**

### ⚠️ PR-005 SECOND AMENDMENT — 2026-08-26: revert to the POST-min-gap universe, and PROMOTED EARLY

**Two changes, both operator decisions, both recorded before any epoch row was graded.**

**1. The universe reverts to POST-min-gap (i.e. the ORIGINAL frozen definition).** The first
amendment moved selection to the pre-min-gap candidate set on the structural argument that a rule
picking "the rung nearest even money" must be able to see every rung. The operator has decided to
keep min-gap as-is, so production selects from the min-gap survivors — and **the registered rule
must test what actually ships**, or the pre-registration validates something nobody is betting.
Cost of the revert: ~0.7u forward (+24.0% vs +26.3%), and it changes no win or loss — the two
universes produced identical 20-11 records. Live consequence on 2026-08-26: min-gap suppressed
Burke 10.5 @ 2.04, so the selection takes 9.5 @ 1.87 instead.

**2. SHIPPED EARLY at n=31, before the bar was met.** v1.9 (2026-08-26) applies the filter to the
board, the alert and the record. **PR-005 REMAINS OPEN AND UNVALIDATED** — shipping it does not
promote it. The promotion bar is unchanged and still runs on rows graded after 2026-08-26:
n>=40, ROI>=+8%, base beats alt by >=15pp, filtered units >= unfiltered units, t>=2.9.

**WHY SHIPPING EARLY IS DEFENSIBLE HERE, and where the risk sits:**
- The evidence is unusually stable: base-rung hit% moved 64.7% -> 64.5% across the 7/31 freeze
  while the headline number halved. Almost nothing else in this system held its rate.
- The excluded rungs KEEP GRADING, so the counterfactual stays measurable — this is a trial with
  a live control arm, not a deletion.
- ⚠️ But n=31 is small, the ladder arm is n=22, and **PR-002 has just demonstrated that a
  pre-registered result at this sample size can reverse outright.** If the epoch rows disagree
  with the pre-epoch evidence, revert rather than rationalise.

**REVIEW DUE 2026-09-02** (1 week). Compare, on epoch rows only: base rungs actually bet vs the
ladder rungs excluded-but-graded. If the ladder outperforms, revert v1.9.

**⚠️ RECORD EPOCH.** Rows from 2026-08-26 are selected under a different rule. Never pool them
with earlier rows. History verified unchanged: all-time 60-40 / +20.39u, forward 23-20 / +1.92u.

## PR-007 — exclude `basis=volume`  (registered 2026-08-29, v1.10 untouched)

**CLAIM:** `basis=volume` selections are a losing cohort and excluding them raises total units.
`elevated` and `role_flip` are both ROLE-CHANGE theses — a player's role genuinely changes because
someone is out. `volume` is a usage-shape argument, the arm least connected to the role-change
story that is this system's only established edge.

**RULE (frozen, arm named in advance):** drop a tracked bet when `basis == "volume"`. Nothing else
changes. Applied on top of the v1.10 base-rung record.

**EVIDENCE (forward, base-rung record):**

| basis | record | hit% | units | ROI |
|---|---|---|---|---|
| elevated | 15-5 | 75.0% | +9.12u | +45.6% |
| role_flip | 4-1 | 80.0% | +2.54u | +50.8% |
| **volume** | **3-6** | **33.3%** | **−3.55u** | **−39.5%** |

Excluding volume moves the forward book from **+8.11u to +11.66u (+3.55u)**.
The in-sample/forward collapse is the tell: volume was **5-1 (+79.8%) pre-freeze** and **3-6
forward** — a ~50pp drop against the system's overall 64.9% → 64.7%. Nearly all the overfit lived
in this arm.

**⚠️ "NON-POINTS GOES 7-1" IS NOT A SEPARATE FINDING — DO NOT REGISTER IT.**
All 9 forward volume bets are `points` bets, so volume is FULLY NESTED inside points and the two
look like independent signals while being one. The 2×2 settles it:

| | volume | not volume |
|---|---|---|
| points | 3-6 (−39.5%) | 12-5 (+33.9%) |
| non-points | *(empty cell)* | 7-1 (+73.8%) |

Controlling for volume, non-points vs points is **+16.9pp, z=+0.92 — no residual market effect**.
The market split is an artifact of the overlap. Registering both would repeat the PR-003/PR-001
collinearity error.

**WHY IT COULD STILL BE FALSE:**
1. **n=9 forward, and it is not significant.** Within points, not-volume vs volume is +37.3pp at
   **z=+1.83**; elevated-vs-volume across all markets is z=+2.14. Both sit under the ~2.8 needed
   for the ~10 fields screened. This is registered BECAUSE it falls short.
2. **Two volume bets are pending right now** (Burke 08-28, Harrison 08-29). If both win it is 5-6
   and the case softens materially. The result is one slate from looking different.
3. **The 2×2 has an EMPTY CELL** (non-points & volume). The design is unbalanced, so volume and
   market can never be fully separated on this data — only a future non-points volume bet can.
4. Two of the three wins are very recent (08-26, 08-28), so the arm may be improving, not decaying.

**PROMOTION BAR — all must hold on rows graded AFTER 2026-08-29:**
- n >= 25 newly graded `basis=volume` bets
- volume-basis ROI <= 0 on the NEW rows alone
- non-volume beats volume by >= 20pp ROI on the NEW rows alone
- **clustered-by-slate t >= 2.5** (PR-002 lesson: a bare ROI figure is satisfiable by noise)
- **total units of the FILTERED book > the UNFILTERED book on the same slates** — the economic
  test; an exclusion cuts volume, and volume is the binding constraint
- **survives removing the 3 largest volume winners** (PR-002 lesson)

**FAILURE CONDITION:** volume ROI > 0, or filtered units <= unfiltered units, at n >= 25 → REJECTED.

**SEASON NOTE:** ~9 volume bets accrued in two months, so n>=25 will NOT be reached in 2026. This
carries into the NBA port. Do not lower the bar for convenience.

**NOT to be re-tested against pre-2026-08-29 data.**

## PR-008 — NBA port: POINTS-ONLY at margin ≥ 3.5 (registered 2026-08-30, pre-season)

**CLAIM:** on REAL lines the NBA beneficiary premise survives only in `pts`. PRA — the stat the
port was designed around — does not survive at any margin. The live config should flag points
only, and gate off pra/reb/ast/fg3m.

**RULE (frozen, single arm named in advance):**
> Flag OVERS on `player_points` only, when `proj − real_main_line ≥ 3.5`.
> `pra`, `reb`, `ast`, `fg3m` are GATED OFF. Real main line = the rung nearest even money, best
> over price across US books. Nothing else changes.

**WHY 3.5 AND NOT THE BEST-SCORING MARGIN.** 5.5 scored highest on the fit half (+3.19%) and 5.0
best on the hold half (+8.29%). **I deliberately did NOT take either.** 3.5 is chosen on two
outcome-independent grounds: it is the LOWER BOUNDARY of the contiguous positive band, and it
carries the most volume (n_hold 382 vs 114 at 5.5) — and volume is the binding constraint on total
units. Picking the max would be the best-of-N selection that killed PR-002.

**EVIDENCE — re-derived on real lines (`nba_margin_refit.py`), chronological split at 2024-10-29:**

| stat | shipped margin | fit ROI | hold ROI | verdict |
|---|---|---|---|---|
| **pts @ 3.5** | 3.0 | **+0.66%** | **+2.58%** | both halves positive |
| pts @ 4.0 / 5.0 / 5.5 / 6.0 | — | +0.89 / +1.08 / +3.19 / +2.77 | +0.58 / +8.29 / +3.06 / +2.93 | contiguous band |
| pts @ 3.0 (shipped) | 3.0 | −2.03% | −3.09% | the SHIPPED value loses |
| **pra @ 5.0 (shipped)** | 5.0 | **−6.24%** | **+1.81%** | signs disagree; negative at every margin ≤4.0 |
| reb @ 2.0 (shipped) | 2.0 | −0.94% | −4.07% | loses |
| ast / fg3m | 2.0 / 0.8 | negative throughout | | already gated off — correctly |

**THE BASE RATE THIS MUST BEAT:** betting every NBA points over on real lines returns **−8.47%**
(113,465 graded quotes, `nba_realline_base.py`). At margin 0 the beneficiary pool returns
−5.82%/−4.18%, so the selection beats blind betting by ~3-4pp on its own — real, but not enough to
clear the vig until the margin rises.

**WHY IT COULD STILL BE FALSE:**
1. The whole positive band is **+0.6% to +3.2%** — small, and small edges are what this project has
   repeatedly failed to confirm forward (PR-002, PR-004, volume-basis).
2. **Two changes are bundled** (market selection AND threshold). If it fails I will not know which
   half was wrong. Registered as one config deliberately, because splitting them doubles the
   multiple-testing burden on a premise that is already marginal.
3. The hold half is **n=382**, and the earlier fit/hold agreement at 3.5 is the weakest cell in the
   band (+0.66% fit). A contiguous band is better evidence than any single cell, but it is still
   one dataset.
4. `reb @ 1.5` was +3.52%/+0.54% — NOT registered, but it is the first stat to revisit if points
   validates. Do not add it opportunistically mid-season.
5. **The 2025-26 holdout is unpulled** (the Odds API key is deactivated), so this has never been
   tested on data outside 2023-10..2025-04.

**PROMOTION BAR — all must hold on 2026-27 season rows graded live:**
- n >= 150 newly graded points flags
- ROI >= +2% on the NEW rows alone
- beats the all-overs points base rate by >= 8pp on the NEW rows
- **clustered-by-slate t >= 2.5** (PR-002 lesson: a bare ROI figure is satisfiable by noise)
- **total units POSITIVE** — not just ROI; the margin cuts volume hard
- **survives removing the 3 largest winners** (PR-002 lesson)

**FAILURE CONDITION:** ROI <= 0, or negative total units, at n >= 150 → REJECTED. If points fails,
**the NBA beneficiary premise is dead**, not merely mis-tuned — pra/reb/ast/fg3m already failed on
real lines, so points is the last surviving stat.

**NOT to be re-tested against 2023-2025 data.** That data derived the margin; it cannot confirm it.
