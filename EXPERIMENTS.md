# PGA experiment registry

Compact. One block per experiment. Read this before proposing anything — the rejected list is
here so a hypothesis is not rediscovered under a new name.

---

## EXP-001 — 1st Round Leader vs close (St Jude)
```
date          2026-08-14
market        1st Round Leader, field-wide (69 runners)
hypothesis    model R1-leader probs beat the devigged close
model         v1.5 + today's fixes
data          69 tee-gated closes @12:05 (tee 12:10); R1 graded, 5-way tie -> dead heat 1/5
temporal      ratings asof 08-13 (R1 excluded from fit); price predates tee
result        REJECTED. model LL 0.07956 vs book 0.07849 (+0.1pt worse)
economic      26 flags at the live gate -> -5.60u, -21.5% ROI
note          book overround 1.46 (31.5% hold). EV formula p*odds-1 was CORRECT (vig belongs in
              the price); the model's probabilities are simply over-spread on this market.
n             68 runners, 1 event -> observation, not evidence
status        REJECTED
```

## EXP-002 — birdie over/unders vs close, structure
```
date          2026-08-14
market        Total Birdies or Better, Round N
data          380 tee-gated closes, 4 events / 7 rounds; graded from birdie_rounds (p3b+p4b+p5b)
pricing       pga_market: 102 two-way, 32 LADDER (alternate lines pooled under one market name)
result        aggregate calibration is DEGENERATE — one over + one under per market, exactly one
              wins, so the mean is 0.5 by construction and cannot fail. Discarded.
finding       under 4.5 realised 0.635 vs devigged 0.541; blind unders +8.0% ROI, overs -22.1%
status        led to EXP-003
```

## EXP-003 — audit of the 4.5-under signal
```
date          2026-08-14
checks        event-clustered z +2.23 (6 clusters) | by-line: 3.5 -0.003, 4.5 +0.101 |
              5 of 6 clusters positive | permutation p=0.0134 | ROI +12.1% at the offered price
status        SURVIVED every audit -> escalated to EXP-004/005/006
```

## EXP-004 — is the edge OURS or the BOOK'S?
```
mechanism     posted-at-4.5 population: mean 4.147 birdies, P(<=4)=0.5961 over 13,319 rounds,
              vs a devigged price of 0.5407 -> structural gap ~5.5pp (~+4% EV), NOT the +9.4pp
              observed. The extra ~4pp was luck.
red flag      ALL profit in one price bucket: @1.50 -6.3%, @1.75 +31.1%, @2.00 -9.5%
model value   'model-ish' filter dropped 3 of 104 selections -> adds nothing
status        DEFLATED
```

## EXP-005 — book price vs player's own base rate
```
method        leave-this-round-out base rate per player (mean 208 prior rounds), vs devigged price
under 3.5     gap -0.0202, clustered z -2.47, 34% base>book   <- CONTROL: sign reverses
under 4.5     gap +0.0593, clustered z +3.63, 79% base>book
structure     book price 0.597 -> 0.544 -> 0.476 by bucket while base stays FLAT at ~0.60
reading       either the book prices week-specific signal the base rate ignores, or it
              over-differentiates. EXP-006 arbitrates.
status        PROMISING, unresolved
```

## EXP-006 — the simulator as arbiter  ⭐ THE DECISIVE ONE
```
date          2026-08-14
question      does the book know something the career base rate does not?
arbitration   corr(model, base) = +0.375 | corr(model, book) = -0.041
              -> the model sides with the flat base rate; it differentiates HALF as much as the
                 book (model sd 0.026 vs book sd 0.054)
DECISIVE      corr(model-minus-book, outcome) = -0.032 at 4.5 (n=104), -0.254 at 3.5 (n=41)
              -> the model's disagreement with the book has ZERO-to-NEGATIVE predictive value
buckets       @1.50 book .597 model .591 realised .594  (all right)
              @1.75 book .544 model .606 realised .756  (model wrong, but in the paying direction)
              @2.00 book .476 model .601 realised .458  (BOOK RIGHT, model 14pp wrong)
verdict       NO MODEL EDGE DEMONSTRATED in birdies. The apparent record is consistent with the
              @1.75 bucket running hot on n=45. The base-rate "structural shade" is refuted at
              @2.00, exactly where it was largest.
status        REJECTED (model edge). Market-structure edge NOT established either.
```

## EXP-007 — does disagreement sharpen in LATER rounds? (the in-play question)
```
date          2026-08-14
question      the model's in-play skill jumps (win Brier .033 -> .404 by after-R3). Does that
              translate into beating in-play PRICES? Split the same birdie population by round:
              R1 = model knows nothing about the event; R3/R4 = it has 2-3 completed rounds.
⚠️ BUG FOUND   first run took BOTH sides of every two-way market — the same observation twice,
              perfectly anti-correlated. n=110 was really 55 markets and every SE was inflated by
              ~sqrt(2). It reported R1 corr +0.267 at 2.8 SE; deduped to the OVER side only, the
              truth is +0.203 at 1.5 SE. Log-loss was unaffected (symmetric); the correlation was
              not. ALWAYS dedupe two-way markets to one row before correlating.
result        NOTHING SIGNIFICANT AT ANY ROUND, and the sign flips:
                R1    corr +0.203 (1.5 SE)   model LL -2.8pt vs book
                R2    corr -0.140 (-0.8 SE)  model LL +2.3pt
                R3    corr -0.015 (-0.1 SE)  model LL +0.5pt
                R4    corr +0.075 (0.5 SE)   model LL -2.5pt
                R3/R4 corr +0.044 (0.4 SE)
economic      top-quartile disagreement: R1 +4.2% (n=14), R3/R4 -5.1% (n=19). Both ~zero.
VERDICT       The in-play skill jump does NOT translate into beating in-play prices for birdies.
              The book absorbs completed-round information as fast as the model does, so the
              0.404 post-R3 Brier skill is uncertainty collapsing, not an information advantage.
status        REJECTED (in-play birdie edge). The forecasting result stands; the edge does not.
```

## EXP-008 / EXP-009 — the rank offsets were fitted on a model that no longer exists  ⭐ REVERTED
```
date          2026-08-14
trigger       the offset x stretch ORDER was shipped unmeasured; EXP-008 tested it
EXP-008       three arms off the SAME draws (offsets->stretch / stretch->offsets / no offsets),
              identical cached ratings, identical seed:
                2026 summed LL   A 1.73045   B 1.72954   C 1.71337
              ORDER is irrelevant (B-A = -0.0009). REMOVING the offsets is worth +0.017.
EXP-009       refit on the CURRENT model, 2023-25 -> 2026:
                base 1.66917 | refit 1.66907 (-0.0001, nothing) | SHIPPED 1.68538 (+0.0162)
              refit shape is OPPOSITE: top5 -0.19 -0.20 +0.03 +0.03 -0.03 vs shipped
              +0.71 +0.27 +0.26 -0.04 -0.26. Sign-flipped at rank 1.
ROOT CAUSE    offsets were fitted on shape_sims.npz, generated with the DEFAULT cut_n=65 for every
              event. The per-event cut rule shipped LATER THE SAME DAY. The top-N tail of a
              156-man field cut at 65 is not the tail of a 69-man no-cut playoff field.
⚠️ WHY THE     +55.9 nats on the 2026 holdout, 8/8 markets, null on `win`, hurting when forced onto
   HOLDOUT    `win` — ALL of it computed inside the same stale checkpoint. The train/holdout split
   MISSED IT  was honest; the MODEL underneath both halves was wrong. A holdout cannot catch that,
              because it is not a data problem.
action        REVERTED. _recal_rank unwired; machinery + table kept, documented, not called.
status        REJECTED. Rank bias was an artifact of a stale cut rule.
```

## Infrastructure — the freeze could not see the revert
```
Disabling _recal_rank changed 2026 summed LL from 1.68538 to 1.66917 and pga_freeze reported
FREEZE INTACT: RANK_OFFSETS was still DEFINED and every constant still matched. A snapshot of
VALUES cannot see whether anything CALLS them.
fix           snapshot() now records call-site wiring (recal_rank_called / recal_shape_called /
              inplay_shape_called), parsed from simulate() with comment lines stripped.
class         same as G2 passing a constant-0.5 model, and aggregate slope hiding a
              rank-conditional defect: a check that cannot fail the way the system actually breaks.
```

---

# REJECTED — do not rediscover

| hypothesis | why | evidence |
|---|---|---|
| TAU is fittable | pure common-mode; cancels from every field-relative quantity | sd(cut_line) = sqrt(sd0²+2tau²) to 0.0115 across tau 0-4 |
| cut line "1.5x too narrow" | harness bug — rated-subset sim vs whole-field realised | coverage .484 -> .733 once matched |
| rho ~ 0.60 from cut-line fit | 6x the measured value; absorbing other misspecification | direct measurement 0.091, CI [.070,.111], placebo 0.0004 |
| HALF_LIFE_D 90 | cheap metric said better, markets said worse | 270 wins 8/8 train, 6/8 holdout; top20 LL +0.0059 |
| separate recent-form term | nothing to absorb it into once 270 stays | partial 0.0646 flat -> 0.0351 at 270d, not convertible |
| course fit | 74% survives a course-key placebo — form wearing a venue label | real .0645 vs placebo .0479 |
| recalibration on p (isotonic/Platt) | ~0 headroom vs a resample null | 5 of 8 markets NEGATIVE excess |
| withdrawal model | 96% contamination in the naive count | true post-cut WDs 0.098/event |
| per-regime constants (majors/field size) | majors are the BEST split already | win skill +.068 vs +.026 |
| model edge in birdies | disagreement with the book does not predict | corr -0.032 (n=104), -0.254 (n=41) |
| rank-conditional offsets | fitted on a stale checkpoint (uniform cut_n=65); refit is worth -0.0001 | shipped cost +0.0162 summed LL on 2026 |
| in-play birdie edge | no round shows significant disagreement-predicts-outcome | R3/R4 corr +0.044 (0.4 SE) |

# METHOD RULES EARNED THE HARD WAY
- A cheap proxy metric has pointed OPPOSITE to tournament probabilities 4 times in one day.
  Never adopt a rating constant without a walk-forward on the markets, 2026 held out.
- Aggregate slope/intercept is BLIND to rank-conditional defects (top10 slope 1.002 while rank-1
  was +11pp and rank-41+ -1.1pp). Never gate on it alone.
- A gate needs a FLOOR as well as a ceiling — G2 passed a constant-0.5 model for months.
- One price bucket carrying all the profit is the signature of variance, not edge.
- Two-way markets must be deduped to ONE row before correlating. Both sides is the same
  observation twice and inflates every SE by ~sqrt(2) (EXP-007 read 2.8 SE for a real 1.5).
- A CHECKPOINT IS A SNAPSHOT OF A MODEL, NOT OF DATA. Any fit derived from one is
  invalidated by a change to the model that produced it, and a holdout cannot detect it.
- A freeze must record WIRING, not just values. A disabled correction is a model change.
- Every market must declare its normaliser (pga_market). A guessed one produces a plausible fair
  price and a fake edge, silently.
