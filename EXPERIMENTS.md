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

## EXP-010 — Round Score markets (over/under a stroke count)

First test of an entirely untested market family. Ladders, so pga_market splits them per line
before devigging; a pooled devig would have priced every selection at a half or a third of value.
Integer lines PUSH and were skipped, not graded as losses.

    over side  n=192  book .523  realised .617  gap +.094  clustered SE .059  z = +1.59

Blind over-betting reads +17.7% ROI, which is the shape of an edge. It is not one: z = +1.59 on
7 event-rounds, and EXP-011 shows what is actually driving it.

## EXP-011 — the birdie and round-score "edges" are ONE observation  ⭐ KILLED BOTH

Fewer birdies IS a higher score, so "birdie unders profitable" and "round-score overs profitable"
are not two confirmations. Per event-round gaps, correlated across the rounds carrying both:

    corr(birdie-under gap, round-score-over gap)  -0.111   (7 event-rounds)
    corr(field mean score, birdie gap)            +0.026
    corr(field mean score, round-score gap)       +0.749

The round-score "edge" is a CONDITIONS effect — the rounds simply played harder than the book
priced them, and the model has no wind forecast. corr +0.749 with the field's own scoring is the
whole result. Betting overs is betting that the weather beats the number, at 7 rounds of evidence.
The birdie gap is NOT conditions-driven (+0.026) and is independent of it (-0.111), so it survives
EXP-011 as a separate question — but EXP-004/006 already showed the edge there is the BOOK's.

VERDICT: round-score overs REJECTED. The honest n was 7 event-rounds, not 192 selections.

## EXP-012 — 2nd Round Leader (36-hole) vs close  ⭐ MARKET UNBETTABLE BY CONSTRUCTION

Second field-wide observation after EXP-001, on a different round and a real dead-heat rule.

SETTLEMENT HAD TO BE RESOLVED FIRST. "2nd Round Leader" can mean low round-2 score or low 36-hole
total, and the model probability is completely different. Settled model-free from the book's own
prices: corr(devigged prob, R1 score) = -0.716, and the five biggest price gains from 1RL to 2RL
are exactly the five players who shot 65 in R1. It is the 36-HOLE market. (Both readings happened
to have the same winner, so the outcome was robust — the model probability would not have been.)

TWO SNAPSHOTS, ONE CLOSE. golf_moves holds this event under a padded AND a clean name, 69 closes
each, stamped 09:30:06 and 12:05:02. Iterating rows into a dict mixes two snapshots 2.5h apart.
Took the later (deadline = R2 first tee 12:10, so 12:05 is 5 min pre-tee) and used the earlier as
a contamination control: 69/69 prices IDENTICAL, max relative move 0.0000 — the padded rows are
duplicate writes, and no golf was played between them.

Model priced by drawing only R2 on top of the known R1 (an unconditional sim would discard the
head start the entire market is about). tau omitted deliberately: a common per-round shock cannot
change a rank.

    unconditional   model LL .06179  book .06387   -0.21 pts   winner rank 10 vs book 12
    form-updated    model LL .06607  book .06387   +0.22 pts   winner rank 14 vs book 12
    EV >= 3% flags: 0 (both)

    corr(model, book) = +0.989      mean |model - book| = 0.0026
    best runner in the field: EV -0.060      median EV -0.529      hold 26.7%

TWO SEPARATE READINGS, AND ONLY ONE IS EVIDENCE. The log-loss gap is ONE winner's probability
(.0402 vs .0349) — a single Bernoulli draw, worth nothing on its own. The zero flags are NOT a
coin flip: they are deterministic given the model and the prices. The model agrees with the book
at +0.989 and the vig is 26.7%, so the most favourable runner in a 68-man field is still a 6%
loser. To clear +3% anywhere the model would have to beat the raw implied price by 10% relative.

The rho=0.09 form update made it WORSE. Consistent with the rejected recent-form term.

VERDICT: 2nd Round Leader OFF. Not "no edge found" — no edge is REACHABLE at this hold.
Round-leader hold falls hard by round: 1RL 32.1%, 2RL 26.7%, 3RL 16.0%. Only 3RL is close to
a price where model skill could ever show up, and it is BLOCKED until R3 completes.

## EXP-013 — HOLD CENSUS  ⭐ THE SCREEN THAT SHOULD HAVE COME FIRST

Model-free: reads prices, nothing else. After EXP-012 showed a model agreeing with the book at
corr +0.989 still losing 6% on its best selection, the obvious question is which markets can be
beaten IN PRINCIPLE. 607 priced books, holds per family (ladders split per line — a pooled ladder
overround is meaningless):

    PLAYER_ROUND_SCORE        5.2%   (295 books, best 4.3%)
    ROUND_MATCHBETS_IMG       5.3%   ( 75)
    TOURNAMENT_MATCHBETS_IMG  5.3%   ( 24)
    PLAYER_BIRDIES_OR_BETTER  5.7%   (199)
    ---- everything field-wide ----
    TOP_20 / TOP_10 / TOP_5 (dead heat)   11.2% / 13.1% / 17.5%
    ROUND_LEADER              26.7%  (1st 32.1%, 2nd 26.7%, 3rd 16.0%)
    WIN_ONLY                  28.0%
    TOP_20 / TOP_10 / TOP_5 (incl. ties)  30.4% / 32.9% / 35.9%

NOT ONE FAMILY IS UNDER 5%. And the four tightest are precisely the four already tested — round
score (EXP-010/011, a conditions effect), matchbets (OFF, failed the placebo), birdies
(EXP-004/006, the edge is the BOOK's). The reachable universe has already been swept, and it came
back empty. Everything still untested is untested because it is unbeatable, not because it is
unexplored.

This also reprioritises the BLOCKED work. Top-N was the top blocked experiment; the census says
TOP_5/10/20 hold 11-36%, so when St Jude finishes it will be measuring a market no model reaches.
It is worth grading for calibration (Lane A), not as a candidate for money.

⚠️ SCOPE. Proportional devigging, so per-runner vig is constant by construction; real books load
longshots harder, and a power/Shin devig would move vig off the favourites. The favourite end of
a big field is therefore better than its book average suggests — EXP-012's best runner sat at
-6.0% against a 26.7% book average. That does not rescue any family here, but it means "hold" is
an average, not a floor.

BLIND SPOT FOUND: 17,257 rows in families with ZERO closes — never priced, which is not the same
as no edge. Two causes. (a) market-group labels in the event column ('3 Balls', '2 Balls', 'Hole
Match Betting', 'Top Region'), ALREADY FIXED — every such row stops at 2026-08-14T09:30:06, the
moment the golf_collect guard landed, and clean names run to the present. (b) pga_tee_gate had no
branch for ball markets and fed the whole market string to a player lookup ('2 Ball (Round 3) -
Thorbjorn' is not a player). Fixed in EXP-014.

## EXP-014 — 2-BALLS: a family we had never once priced

Unblocked by two patches, each measured before shipping.

pga_tee_gate: a ball market closes at the EARLIEST tee in the group (same rule as a matchbet —
once any player is away the price is in-play). Participants parsed from the market string, matched
exact -> unique surname -> surname + first initial, FAILING CLOSED on any ambiguity. Also folded
the Latin letters NFKD cannot decompose: 'ø' was being DELETED, so 'Højgaard' -> 'hjgaard', and
the tee sheet already held 'rasmus hjgaard' AND 'rasmus hojgaard' as two separate keys.
    regression check over all 2598 (event, market) pairs: NEW 70, CHANGED 0, LOST 0
    (68 ball markets + 2 Højgaard matchbets — the fold fixed a non-ball market too)

pga_market: ball markets are exhaustive over their own runners, so they normalise to 1.0. Ties are
a PUSH, so this is P(win | no tie) and ties MUST be excluded at grading rather than scored as
losses — the two conventions travel together. Self-tests extended, ALL PASS.

Closes were reconstructed straight from golf_lines (last price before the resolved deadline)
rather than waiting on the moves backfill.

    HOLD  67 books, median 5.26%, min 3.08%, max 7.35%
          -> marginal, the same band as round score 5.2% / matchbets 5.3% / birdies 5.7%.
          NOT the reachable family hoped for.

    BOOK  n=59 (3 ties pushed)  mean p .4956  realised .4915  gap -.0041
          book log-loss .66469 against .6931 for a coin flip — the book has real information

    MODEL n=59  log-loss .67376 vs book .66469   +0.91 pts   BOOK BETTER
          corr(model, book) +0.873   mean |model-book| .0247
          corr(model-book disagreement, outcome) = -0.110   ANTI-predictive
          EV>=2% n=11 -10.9% ROI | EV>=3% n=11 -10.9% | EV>=5% n=6 -4.2%

VERDICT: 2-balls OFF. Same conclusion as matchbets, reached independently on a market the model
had never seen. Disagreement is anti-predictive here (-0.110) exactly as in birdies (-0.032).
n=59 over 2 event-rounds is small and the clustered SE is meaningless at 2 clusters — this is one
observation, and it points the same way as all the others.

The infrastructure win is permanent regardless: ~24k ball price rows per week now resolve and will
keep accruing, and DP World events remain unreachable only because the tee sheet is PGA-only.

## EXP-015 — does EXP-013's strike-off survive a different devig? Testing my own claim

EXP-013 struck every field-wide market off the programme using its HOLD. That verdict inherited an
assumption: pga_market devigs PROPORTIONALLY, which makes per-runner vig constant by construction,
so every runner in a 26.7% book reads as a 26.7% loser. Real books load longshots far harder. If
so, the favourite end could be much cheaper than the book average and the strike-off would be an
artifact of my own devig.

Proportional vs power vs Shin (z = implied insider fraction), per-runner vig at each end:

    favourites (5 shortest)   proportional +38.3%   shin  +25.7%   power +31.1%
    longshots  (5 longest)    proportional +38.3%   shin +180.6%   power +66.6%

THE BIAS IS REAL AND LARGE. Proportional devigging misallocates badly: it charges favourites ~12
points more than Shin implies and longshots ~142 points less. Any "edge" found on a longshot under
proportional devigging is the devig, not the market.

Cheapest products once the vig is allocated (Shin, favourite end):
    Top 20 (dead heat)   +9.4%      Top 10 (dead heat)  +10.5%
    3rd Round Leader     +13.0%     Top 5  (dead heat)  +14.2%
    2nd Round Leader     +22.2%     Win Only            +24.9%
DEAD-HEAT top-N is 3-4x cheaper than the same market "incl. ties" (Top 20: 11.2% vs ~30% hold).

VERDICT: STANDS. The cheapest favourite-end vig under the most generous devig is +9.4%, and every
disagreement correlation measured anywhere in this programme is NEGATIVE (birdies -0.032, 2-balls
-0.110, in-play +0.044 at 0.4 SE). Nothing here reaches 9.4%.

BUT THE ORDERING IS REFINED, and it matters for the blocked work: Top 20 dead-heat, not Top 5 or
the leader markets, is the cheapest field-wide product. When St Jude finishes, that is the one to
grade.

⚠️ This is a SENSITIVITY analysis and is labelled as one. Proving which devig is correct needs
realised frequencies across the price range; the only field-market outcomes in hand are two single
winners (1RL, 2RL). It shows the verdict is robust to the assumption, not that Shin is true.

CAUGHT IN FLIGHT: the first run reported top-N vig of +40000%. Per-runner vig is implied/fair - 1
and BOTH sides must be on one scale; rebuilding implied from the odds re-applied the target and
put top-N out by N^2. Field-win markets hid it completely because their target is 1.

## Infrastructure — golf_lines was still in DELETE journal mode

The EXP-014 backfill died with 'database is locked' mid-read. Same class as the golf_moves
deadlock, second database, never fixed there: golf_lines is 467 MB and written by golf_collect
every 30 minutes, and in DELETE mode a writer blocks EVERY reader for the whole transaction. The
writer was the least patient party in the system -- golf_collect opened it with no timeout
argument at all, i.e. the 5-second default.

Fixed on both sides, busy_timeout BEFORE the WAL switch (flipping journal_mode is itself
lock-taking, which is the ordering that broke this the first time): golf_collect now opens with
timeout=60 + PRAGMA busy_timeout=60000 + WAL, and golf_moves' three LINES connections route
through a single _open_lines(). The file itself is now WAL, so readers no longer block on the
writer at all.

## EXP-016 — is the BOOK internally coherent? (model-free)  ⭐ CLEAN NEGATIVE

Every test so far has been our number against theirs, and the book has won every time. This asks
something the book cannot win by being smarter: do its own prices contradict each other? Three
orderings are forced by logic alone for the same player in the same event.

  A DOMINANCE  "Top 20 (Incl. Ties)" pays whenever "Top 20" (dead heat) pays and MORE -- a
               five-way tie for 18th pays in full on one and a fraction on the other. So
               odds_ties <= odds_dh always. EXP-015 made this worth asking: the same nominal
               market holds 11.2% as dead-heat and ~30% incl.-ties, and a 19-point spread on two
               products over one event is where a contradiction would hide.
  B NESTING    top5 within top10 within top20 -> odds non-increasing, within each flavour.
  C WIN        winning is a subset of top 5.

Tested at RAW OFFERED ODDS, never on devigged probabilities: a devigged violation can be
manufactured by the devig itself (EXP-015 moved the longshot end 142 points between methods),
whereas a raw-odds violation is a statement about two prices actually on offer.

    A dominance   0 violations / 207 pairs
    B nesting     0 violations / 554 pairs (138 dead heat, 416 incl. ties)
    C win vs top5 0 violations / 138 pairs

FanDuel is internally coherent on every axis available. The 11.2% vs 30% hold gap is not an
inconsistency -- it is the book pricing the tie probability and charging more vig on the product
that wins more often. Both are coherent; one is simply dearer.

VERDICT: no model-free inconsistency to exploit. This closes the last avenue that did not depend
on out-predicting the book.

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

| rho form update on R1 residual | costs log-loss on the only market it was tried on | LL .06179 -> .06607, winner rank 10 -> 14 |

| 2-balls as a tight market | 5.26% median hold, same band as everything else; model loses | LL .674 vs book .665, disagreement corr -0.110 |

| cross-market incoherence | book is coherent on every available axis | 0 violations in 207 dominance + 554 nesting + 138 win/top5 pairs |

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
- TWO "EDGES" THAT ARE THE SAME PHYSICAL EVENT ARE ONE OBSERVATION. Fewer birdies is a higher
  score. Before treating a second market as confirmation, correlate the per-event gaps and check
  neither is just tracking conditions (round-score gap vs field mean score: +0.749).
- RESOLVE SETTLEMENT BEFORE GRADING, FROM THE BOOK'S OWN PRICES. "2nd Round Leader" has two
  readings with different model probabilities. corr(price, prior-round score) decides it model-free.
  Grading the wrong rule yields a confident number about a question nobody asked.
- CHECK THE HOLD BEFORE BUILDING THE MODEL. At a 26.7% overround the best runner in a 68-man field
  was -6% EV with the model AGREEING with the book at +0.989. Screen markets by vig first; skill
  cannot reach a price that keeps a quarter of the pool.
- A DUPLICATE EVENT NAME IS A DUPLICATE SNAPSHOT. Two name variants each carried 69 closes at
  timestamps 2.5h apart; a dict built by iteration silently mixes them. Take the latest before the
  resolved deadline, and diff the earlier one as a free contamination control.
- SCREEN BY VIG BEFORE MODELLING. Do the hold census first. Not one PGA family prices under a 5%
  hold, and the four tightest are the four already tested and rejected. Markets left untested are
  untested because they are unbeatable, not because they are unexplored.
- ZERO CLOSES IS NOT ZERO EDGE. 17,257 rows sat unpriced because a gate could not resolve a
  deadline. Fail-closed is right, but a permanently silent refusal is indistinguishable from a
  market that does not exist. Count and report refusals by reason.
- A GLOBAL NAME-NORMALISATION CHANGE SHIPS ONLY WITH A BEFORE/AFTER DIFF over every pair, split
  into NEW / CHANGED / LOST. NEW is the point; CHANGED or LOST is a regression that would silently
  re-date closes already graded against.
- NFKD DOES NOT FOLD EVERY LATIN LETTER. ø, đ, ł, æ, ß have no decomposition and get DELETED by an
  ASCII pass, so 'Højgaard' and 'Hojgaard' never match and the index silently splits in two.
- REPORT WHY A PRICING LAYER REFUSED. 67 refused books read as an empty hold table because the
  loop skipped them silently — the same silent-zero class, self-inflicted inside an experiment.
- PROPORTIONAL DEVIGGING MAKES PER-RUNNER VIG CONSTANT BY CONSTRUCTION. It is an assumption, not
  a measurement. Shin puts the favourite end 12 points cheaper and the longshot end 142 points
  dearer on the same books. Any edge found on a longshot under a proportional devig is the devig.
- DEAD-HEAT AND INCL.-TIES ARE DIFFERENT MARKETS AT DIFFERENT PRICES, not two labels for one
  product: Top 20 dead heat holds 11.2%, Top 20 incl. ties ~30%. Never pool them.
- WHEN A VERDICT RESTS ON A METHOD CHOICE, RE-RUN IT UNDER THE ALTERNATIVES BEFORE BANKING IT.
  EXP-013's strike-off survived; it might not have, and it was my own assumption that put it at
  risk.
- TWO DATABASES MEANS TWO LOCK FIXES. golf_moves was put into WAL after it deadlocked; golf_lines
  was left in DELETE mode and deadlocked the same way months later. Fix the class across every
  file it applies to, not the file that happened to fail.
- TEST COHERENCE ON RAW ODDS, NOT DEVIGGED PROBABILITIES. A devigged "violation" can be an
  artifact of the normaliser; a raw-price ordering violation is a fact about two live offers.
