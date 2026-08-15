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

# METHOD RULES EARNED THE HARD WAY
- A cheap proxy metric has pointed OPPOSITE to tournament probabilities 4 times in one day.
  Never adopt a rating constant without a walk-forward on the markets, 2026 held out.
- Aggregate slope/intercept is BLIND to rank-conditional defects (top10 slope 1.002 while rank-1
  was +11pp and rank-41+ -1.1pp). Never gate on it alone.
- A gate needs a FLOOR as well as a ceiling — G2 passed a constant-0.5 model for months.
- One price bucket carrying all the profit is the signature of variance, not edge.
- Every market must declare its normaliser (pga_market). A guessed one produces a plausible fair
  price and a fake edge, silently.
