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
