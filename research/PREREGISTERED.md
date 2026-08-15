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
