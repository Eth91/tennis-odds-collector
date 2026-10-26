# TENNIS RESEARCH — ATP / WTA

Phase 2 of the betting programme, opened 2026-08-31 after the PGA phase closed with no edge.
Prior work lives in `Desktop/Projects/tennis-betting/` and in project memory; this file records
only what is established HERE, on the live Pinnacle feed.

## WHY TENNIS, STATED HONESTLY
Not because the vig is dramatically lower. Measured on 8,375 pre-start Pinnacle closes:

    set total 2.5 hold   median 4.75%   (ATP 4.29%, WTA 4.14%, ITF 4.78%)
    moneyline hold       median 4.73%

against golf's TIGHTEST family at 5.2% (EXP-013). A modest improvement, not a different world,
and my first framing of it overstated the gap.

The real difference is structural: tennis gives a SHARP REFERENCE (Pinnacle) on the exact market
where a mispricing mechanism has already been identified. Golf never had one.

## ALREADY SETTLED — do not redo
- MONEYLINE IS DEAD. Surface Elo trails de-vigged Pinnacle by 0.039 log-loss (AUC 0.708 vs 0.753),
  a DISCRIMINATION gap; isotonic recalibration plus rank features recover only ~0.007. Betting into
  Pinnacle runs about -10% ROI. Phase 3 added fatigue, form, streak and H2H for +0.005 AUC and
  concluded winner prediction sits at the PUBLIC-DATA CEILING. Do not optimise the winner model.
- The one live mechanism is the SET SHAPE, not the match line.

## TN-001 — iid-from-moneyline undercounts STRAIGHT SETS  ⭐ CONFIRMED ON SHARP PRICES

Phase 4a claimed soft books price set betting as if sets were iid draws implied by the match line,
undercounting straights (0.545 priced against 0.647 realized). Phase 6 could not grade it: no free
set-odds archive existed and Betfair was region-blocked. Phase 7 then built the instrument without
realising it — Pinnacle publishes a SET TOTAL at 2.5, which in best-of-3 IS straights (under)
versus decider (over).

Model-free throughout. De-vig the moneyline for M = P(favourite wins match); invert best-of-3 for
the per-set p solving M = p^2(3-2p); the iid straight-set probability is p^2 + (1-p)^2; compare
against Pinnacle's own de-vigged P(under 2.5). No match outcomes needed — both numbers come from
the same quote, which is why this could be answered immediately.

    tour        n       iid    Pinnacle       gap
    ALL      8375    0.5401      0.6518    +0.1116
    ATP      2428    0.5341      0.6259    +0.0918
    WTA      1090    0.5474      0.6488    +0.1014
    ITF      4857    0.5415      0.6654    +0.1238

Phase 4a measured 0.545 against 0.647 from REALIZED OUTCOMES in a historical dataset. This measures
0.540 against 0.652 from LIVE SHARP PRICES. Two independent routes, the same answer.

ROBUSTNESS
    Pinnacle above the iid value in 8,348 of 8,375 matches — 99.7%
    gap median +0.1140, p05 +0.0692, p95 +0.1504
    by month:  Jul +0.1126   Aug +0.1107   Sep +0.1021
    by favourite strength: +0.113 / +0.112 / +0.113 / +0.106 / +0.091 from .50-.60 up to .90+
    every tournament positive: ATP majors ~+0.075, WTA ~+0.10, ITF ~+0.13

MECHANISM: sets within a match are POSITIVELY CORRELATED — same opponent, surface, conditions and
day — so sweeps occur more often than independent draws imply. iid ignores that. The effect is
larger at ITF than ATP because lower tiers blow out more often.

## ⚠️ THE GATE — and it is the entire edge
TN-001 establishes the mispricing that WOULD exist IF a soft book prices sets iid-from-moneyline.
It does NOT establish that any book does. We hold ZERO soft-book tennis prices: fanduel_props has
an empty sport column, tt.sqlite is table tennis, odds.sqlite is Pinnacle only, and earlier work
already found FD/DK cannot be auto-scraped.

State: mechanism CONFIRMED, exploitability UNVERIFIED. One observation settles it — a handful of
real FD/DK set-betting prices, compared against 0.54 (iid, exploitable) and 0.65 (Pinnacle-like,
no edge). Until that exists no bet is justified, and nothing here is evidence of one.

This is the "does the instrument cover the claim" trap in its purest form: everything measurable
has been measured, and the one unmeasured link carries the whole result.

## TN-002 — does FanDuel actually price sets iid?  ❌ NO — THE EDGE IS DEAD

FanDuel IS scrapable. `sbapi.ny.sportsbook.fanduel.com/api/content-managed-page?page=SPORT&
eventTypeId=2` lists the board (tennis is eventTypeId 2, inherited from Betfair's taxonomy), and
`event-page?eventId=X&tab=popular` returns the full market set. Same public `_ak` key the golf
collector already uses. 93 head-to-head matches, 47 with deep boards.

The default event page carries PLAYER_A/B_TO_WIN_AT_LEAST_1_SET, which IS the straight-sets market
in disguise: P(A wins 0 sets) = 1 - P(A wins at least 1 set) is a sweep in either format, so
P(straights) = 2 - pA - pB with no format assumption at all.

    format   n     iid    FanDuel      gap
    BO3     46  0.5665     0.6747   +0.1082
    BO5     41  0.3268     0.4771   +0.1503
    Pinnacle, same market (TN-001)          +0.1116

FanDuel's best-of-3 gap of +0.1082 against Pinnacle's +0.1116 is the same number. FANDUEL PRICES
SETS ABOUT AS SHARPLY AS PINNACLE AND DOES NOT USE iid. The Phase 4a premise is false at FanDuel,
and that was the only live tennis mechanism on the books. TN-001 remains correct and is now merely
a description of how both books price, not an exploitable gap.

⚠️ MY OWN BUG, CAUGHT: the first pass applied the best-of-3 inversion to everything and produced
a clean ATP-negative / WTA-positive split that looked like a finding. It was Men's Grand Slam
matches being best-of-FIVE. The FanDuel side is format-agnostic; the iid side is not.

## TN-009 — FanDuel tennis hold census (tab=popular)

    MATCH_BETTING                    2 runners   4.3%   <- CHEAPER THAN PINNACLE (4.73%)
    TO_WIN_1ST_SET, SET_2/3/4/5_WINNER  2        4.7%
    MATCH_TOTAL_GAMES / >=1 SET / SET_X_MOST_ACES  2   6.5-6.6%
    MAIN_SET_TOTAL_GAMES, MAIN_SET_GAME_HANDICAP   2   ~10%
    SET_BETTING                      4 runners  10.6%   genuine, mutually exclusive
    SET_X_SCORE_AFTER_Y_GAMES        5          11.8%
    CORRECT_SCORE_1ST/2ND/3RD_SET   14          22.5%
    ace ladders                      4-7        NOT MEASURABLE - see below

FanDuel's tennis MONEYLINE is cheaper than Pinnacle's. The FD-exclusive markets are the expensive
ones; the markets both books price are the cheap ones. That is the opposite of the "no sharp
competitor means opportunity" hypothesis - no competitor also means no pressure on price.

⚠️ RETRACTED WITHIN THIS EXPERIMENT: an earlier pass reported ace holds of 42-63%. The ace markets
are ONE-SIDED NESTED THRESHOLD LADDERS - "5+, 7+, 9+, 11+, 13+, 15+, 20+" with no under quoted -
so their implied probabilities are cumulative and overlapping and summing them is meaningless.
This is exactly the ladder trap pga_market was built to prevent, and it nearly went into a report.
With only one side quoted the vig CANNOT be extracted from the price at all; it needs a model or a
competing quote.

## GOTCHAS FOR THE SCRAPER
- tennis is eventTypeId=2; `customPageId=tennis` 404s.
- an UNKNOWN tab name does NOT error - it silently returns the 6-market default. Two passes here
  concluded "no deep boards exist" because they asked for `tab=all`, which is not a real tab. The
  working tab is `popular`; the layout block names the real ids [319, 109 Popular, 238, 317,
  110 Set Markets, 112 Player Markets].
- market depth is a function of TIMING: matches already underway are stripped to 1-9 markets,
  upcoming marquee matches carry 33-43 including 9-13 ace markets.

## WHERE THIS LEAVES TENNIS
The moneyline was already at the public-data ceiling. The set-shape edge is now dead at FanDuel.
The FD-exclusive surface is dearer than the shared markets, and its most interesting family (aces)
is one-sided so it cannot even be priced without an independent model of ace counts.
What survives as a QUESTION, not a finding: ace ladders are one-sided and FanDuel must price them
from something; the prior work already has a serve model and TML has ATP serve stats to 1968. That
is the only remaining thread, and it needs an ace-count model plus settled results to grade.

## TN-011 — FanDuel tennis collector, ALL markets  ✅ LIVE

`tennis_fd_collect.py`, cron every 15 minutes on the VM, writing `tennis_fd.sqlite`.

    board     content-managed-page?page=SPORT&eventTypeId=2      (Betfair taxonomy via Flutter)
    markets   event-page?eventId=X&tab=popular                   (the ONLY tab with the deep board)
    first pass  95 matches, 48 deep boards, 10,529 quotes, 0 errors

GENERIC BY DESIGN. One row per (market, runner) with market_type carried as DATA - nothing about
the 43 families is hardcoded, so a product FanDuel adds next month is captured the first time it
appears rather than dropped by a schema that never heard of it.

CHANGE-ONLY STORAGE. A full snapshot is ~10.5k rows; at every 15 minutes that is ~3 GB a month of
mostly identical prices, on a box that already runs a disk guard and a dozen collectors. Rows are
written only when a price MOVES (first sighting always writes), so the line-movement history - the
thing CLV actually needs - is preserved at a fraction of the size. Verified: pass 1 wrote 10,529,
pass 2 saw the same 10,529 quotes and wrote 0.

TOUR + BEST_OF ARE STORED, NOT DERIVED. FanDuel does not label Slam boards ATP/WTA - they arrive
as "Men's US Open 2026" / "Women's US Open 2026", and the first mapper tagged every row OTHER.
best_of is stored because applying best-of-3 maths to Men's Slam matches already manufactured a
convincing ATP/WTA split earlier in this phase that was pure format artifact.

ITF is collected too, despite the ask naming ATP and WTA. Filtering at read time is free,
un-collected data is gone forever, and ITF carried the LARGEST set-shape gap of any tier
(+0.1238 against ATP's +0.0918).

## TN-012 — ACE MODEL v1  ⭐ BEATS ITS BASELINES OUT OF SAMPLE

Data: TML-Database 2015-2026, 58,927 PLAYER-MATCH rows, 1,111 players. Player-match rather than
match-wise, because an ace is a SERVER quantity and storing w_ace/l_ace forces every downstream
join to re-derive the opponent side and get it wrong half the time. (Sackmann is confirmed dead;
TML is live. TML's 2026 file stops at 2026-01-17, so the holdout year is 2025.)

    expected_aces = rate(server, returner, surface) x expected_service_points

Splitting rate from workload is the whole design: a model predicting COUNTS without conditioning
on service points is largely predicting match length wearing a serving costume. Rate is a log5
combine on the surface baseline, both inputs empirical-Bayes shrunk toward it. Everything is
accumulated in DATE ORDER with exponential decay and every prediction is made BEFORE the match is
learned from. Shrinkage k=200 and half-life 540d were fitted on TRAIN ONLY, scored on 2024.

CHRONOLOGICAL BACKTEST, train <= 2024, test 2025, 5,499 rows, actual mean 6.58 aces:

    global mean (6.37)                 MAE 3.9023
    player's own historical mean       MAE 3.3539     <- the honest baseline to beat
    MODEL, rate x PREDICTED workload   MAE 2.9686
    MODEL, rate x ACTUAL workload      MAE 2.5724
    like-for-like on the 5,314 rows where both exist: 3.3539 -> 2.9639, MODEL BETTER by 11.6%

    by surface: Grass actual 8.96 / pred 8.89 | Hard 7.15 / 6.95 | Clay 4.34 / 4.08

WHERE THE ERROR LIVES. Handing the model TRUE service points cuts MAE from 2.9686 to 2.5724, so
about 13% of total error is match-LENGTH uncertainty rather than serving. That is the largest
single improvement available, and it is exactly what the moneyline knows - which links the model
to the feed TN-011 now banks.

⚠️ SYSTEMATIC UNDER-PREDICTION of roughly 2-5% on every surface. On a market that quotes ONLY
overs, a low bias points the wrong way, and it must be corrected before any bet is priced.

⚠️ ATP ONLY. TML has no WTA serve stats; the WTA ace model is blocked on DATA, not method. The
collector banks WTA ace ladders regardless, so the gap is on the model side.

⚠️ WHAT THIS IS NOT. Beating a player-mean baseline is NOT beating FanDuel. There are ZERO
historical FanDuel ace odds - collection began 2026-08-31 - so the EDGE test is forward-only and
cannot be backtested at all. Model quality is not market edge; that distinction is the single
most expensive lesson of the PGA phase and it applies here unchanged.

## TN-013 — ACE MODEL v2: moneyline workload + bias correction  ⭐ BOTH FIXES LAND

v1 named its own two weaknesses. Both are now addressed and measured.

ODDS SOURCE. TML has serve stats but no prices, so tennis-data.co.uk ATP files 2015-2025 were
fetched and joined: 27,347 priced matches, 69.5% join rate onto ace_pm. The unmatched third is
mostly Challenger/qualifying, which tennis-data does not cover - and which FanDuel does not price
ace ladders on either, so the joined subset IS the relevant population rather than a biased slice.
The join key is (surname, first initial) inside a +-4 day window, because tennis-data stamps the
scheduled day and TML the tournament start; ambiguous and unmatched rows are counted, never
silently dropped. Rank difference was available inside TML and would have avoided the join, but it
is a PROXY - fitting on a proxy and deploying on a price is how a model stops meaning what it was
measured to mean.

WORKLOAD, redesigned as LENGTH x STYLE:
    expected_service_points = expected_service_GAMES(moneyline, best_of) x points_per_service_game
Service games belong to the MATCH, points per service game to the PLAYER. v1 averaged both
players' historical service-point totals and thereby blended the two, letting a short match with a
grinder look like a long match with a big server. The moneyline enters ONLY through expected games,
fitted on train by (best_of, |M-0.5|) bucket, so it cannot smuggle in anything about aces:

    bo3  11.7 (close) -> 9.7  (lopsided)      a 17% workload swing
    bo5  18.8 (close) -> 15.4 (lopsided)

    service-point MAE   21.35 -> 19.61   |   ace MAE on joined rows  2.9406 -> 2.8660

BIAS, corrected on TRAIN ONLY (actual = -0.0065 + 1.0243 * pred, n=51,889), the same two numbers
applied unchanged to test. Fitting it on test would guarantee zero bias and prove nothing.

FULL CHRONOLOGICAL BACKTEST, train <= 2024, test 2025:

    model                                    MAE       bias
    v1  no moneyline, no correction       2.9688    -0.4140
    v2  moneyline workload                2.9211    -0.2510
    v2  + bias correction   <- SHIPPABLE  2.9329    -0.1035
    ceiling: rate x ACTUAL svpt           2.5713    -0.2060

    residual bias by surface: Grass -0.118, Hard -0.086, Clay -0.138

THE CORRECTION COSTS MAE AND THAT IS THE RIGHT TRADE. MAE rises 2.9211 -> 2.9329 while bias falls
59%. The market quotes ONLY overs, so a systematically low model is wrong in the SAME DIRECTION on
every bet it ever makes, whereas a slightly wider spread of errors is not. Bias is the loss
function for this market; MAE is not.

Combined against v1: bias -0.4140 -> -0.1035, a 75% reduction, with MAE also slightly better.

⚠️ RESIDUAL BIAS of -0.10 aces (1.6% of the 6.58 mean) survives a train-fitted linear correction,
and it is negative on all three surfaces. The likely cause is a secular upward TREND in ace rates
that a backward-looking decayed average cannot fully track - a 540-day half-life lags a rising
series by construction. A year term, or a shorter half-life, is the next thing to try.

⚠️ STILL FORWARD-ONLY FOR EDGE. Everything above is forecasting accuracy against baselines. There
are still ZERO historical FanDuel ace odds, so whether any of this beats the PRICE cannot be
backtested - only accrued. TN-011 has been banking ace ladders since 2026-08-31.

## TN-014 — a silent column-order corruption, found and fixed within the hour

The collector's first hours wrote a POISONED market_type column and nothing errored.

CAUSE, and it was mine. fd_tennis was first created without best_of. Adding it with
ALTER TABLE ADD COLUMN appends to the END of the table, but the patched INSERT supplies values in
the DDL's order, where best_of sits sixth. Every value after position five shifted by one:

    start_time  <- best_of
    market_id   <- start_time
    market_type <- market_id        which is why market_type held "736.183007715"

SQLite accepted 14 values into 14 columns. They were simply the wrong 14. 1,934 of 1,959 distinct
"market types" were market ids, and every downstream filter on market_type would have silently
matched a third of the data.

CAUGHT BY A SANITY CHECK, not by an error: "distinct market types = 1959" is impossible when the
board has 28 families, and it exceeded the count of distinct market IDs. The rule that found it is
the same one from the golf phase - when a number is impossible, audit the data before believing
any analysis built on it.

FIX: the table was rebuilt from the DDL so column order and INSERT order agree by construction
rather than by an ALTER and a hope; ~30 minutes of data was discarded. fd_current had to be
cleared too - a `sqlite3` CLI call to do it failed silently (the CLI is not installed), so the
first rebuild pass wrote only 209 changed rows instead of a full baseline, leaving prices tracked
in fd_current with no row in the table. Clearing it from Python and re-running restored a complete
10,598-row baseline.

GUARD ADDED: the collector now asserts market_type is an upper-case enum and fails the pass LOUDLY
if more than 5% of rows are not, so a future reordering announces itself instead of quietly
poisoning a column for weeks.

VERIFIED AFTER: distinct market_type 1959 -> 25, non-enum rows -> 0, tour/best_of ATP-bo5 x51 and
WTA-bo3 x49, start_time back to ISO timestamps, 553 ace rows banked.

## TN-015 — is there a reason to believe the ace ladders are beatable?  ⚠️ INCONCLUSIVE, verdict retracted

The ladder implies a survival curve; turning each rung into 1/odds gives P(>=k) INCLUDING vig, so
FanDuel must sit ABOVE any unbiased estimate. Compared against a negative binomial (dispersion
r=4.4 fitted on players with >=25 matches, so ace counts are genuinely overdispersed and a Poisson
tail would understate the big-serving upside):

    rung   3+      5+      7+      9+     11+     13+     15+     20+
    gap  +.025   +.039   +.039   +.056   +.043   +.019   -.008   -.040
    overall mean gap +0.0256 over 72 rungs

⚠️ THE SCRIPT PRINTED "thin, worth pursuing" AND THAT VERDICT IS RETRACTED. The comparison curve
was a crude negative binomial on each player's RAW historical ace mean times 1.45 for best-of-5.
The per-player disagreements it produced are enormous - Safiullin FD 0.204 against model 0.406 at
11+, Alcaraz FD 0.263 against model 0.173 - roughly +-0.20, an order of magnitude larger than the
+0.026 aggregate. The aggregate is therefore the average of my own large errors in both
directions, not a measurement of FanDuel's margin. A uniform vig would also show a FLAT gap across
rungs; this one rises to +0.056 at 9+ and turns negative by 20+, which is the shape of a wrong
mean, not of a price.

WHAT WOULD SETTLE IT: score the REAL model (TN-013/016) against live ladders and settle against
actual ace counts. That needs the model wired to the live board plus an ace-RESULTS collector.
Neither exists. Until they do there is no basis for a bet.

## THE HONEST CASE ON ACES

FOR
  - Pinnacle does not price aces, so FanDuel has no sharp line to copy and must self-price.
  - Ace rate is among the most stable player-level stats, so a model can be genuinely accurate.

AGAINST, and this side is stronger
  - The market is ONE-SIDED, overs only. That is the signature of a recreational product, and
    such products are normally shaded toward the side punters like. There is no way to take the
    other side of a shade.
  - Every FanDuel-EXCLUSIVE market measured in TN-009 runs 6.5-22% hold, against 4.3% on the
    markets both books price. No sharp competitor means no pressure on price, not opportunity.
  - Model MAE is 2.93 aces while ladder rungs are spaced 2 apart: the typical error spans more
    than one rung of the decision.
  - Across this whole programme - golf and now tennis - the book has known every time.

STATUS: a hypothesis with a plausible mechanism and a stronger counter-mechanism. Not a finding.

## TN-016 — the year term is REJECTED; the fix is a SHORTER HALF-LIFE  ⭐

v2 ran -0.10 low, negative on all three surfaces. A same-sign bias everywhere is a TIME problem,
so a year term was the obvious fix. It was wrong twice over.

THE SERIES IS U-SHAPED, not trending. Ace rate per service point fell to roughly 2020-2022 and has
risen since (Clay .0576 -> .0465 -> .0528; Grass .1059 -> .0915 -> .0997). A ten-year straight
line is dominated by the early decline and the COVID dip and extrapolates DOWNWARD into 2025,
exactly when the truth was rising. Bias doubled: -0.2035 -> -0.4385.

FOUR VARIANTS, SELECTED ON MEAN |bias| ACROSS THREE TRAIN YEARS (2022/23/24):

    variant                              2022     2023     2024   mean|b|
    A  no year term (540d)             -0.208   -0.408   -0.405    0.3404
    B  linear over ALL train years     -0.489   -0.764   -0.745    0.6661
    C  linear over LAST 3 train years  -1.093   -0.545   -0.231    0.6227
    D  no year term, half-life 270d    -0.211   -0.364   -0.320    0.2984  <- robust pick

Both year-term forms are the two WORST. D wins, and on the untouched 2025 holdout:

    A  -0.1445   B  -0.3938   C  +1.2513   D  -0.0364  <- essentially unbiased
    D by surface: Grass +0.117, Hard +0.018, Clay -0.221 - now straddling zero, not all negative
    D MAE 2.9633 against A's 2.9263

FULL ARC v1 -> v4: bias -0.4140 -> -0.0364, a 91% reduction, bought for +0.037 MAE. On an
overs-only market that is the right trade, for the same reason as TN-013.

⚠️ THE NEAR-MISS IS THE LESSON. A SINGLE-year selection (2024 alone, on |bias|) picked variant C -
which then produced the WORST holdout of all four at +1.2513, three times any other. Same four
candidates, same data; the only difference was selecting on three years instead of one. One
selection year is one draw, and picking the max of a noisy criterion is how an overfit variant
gets promoted.

## TN-017/018/019 — FANDUEL vs PINNACLE on the shared markets  ❌ NO MONEYLINE EDGE

Every earlier test asked whether OUR MODEL beats the book. This asks the question that actually
matters for a soft book and needs no model at all: does FANDUEL's price differ from PINNACLE's?
Pinnacle's de-vigged number is the best available estimate of truth, so a FanDuel price paying
more than that is +EV by construction.

Joined by normalised player pair and date, pairing each FanDuel quote with the Pinnacle quote
CLOSEST IN TIME and discarding anything over 20 minutes apart - a non-simultaneous pair measures
line movement, not disagreement. Median surviving gap 6.5 minutes, 166 quotes over 87 matches.

    MONEYLINE, proportional de-vig:  mean EV -0.0347, and 17 of 166 quotes (10.2%) paid MORE than
    sharp-fair, mean +6.0%, max +13.6% - every one a longshot (mean fair prob 0.173).

THAT TAIL WAS A DE-VIG ARTIFACT. Proportional de-vigging splits the margin evenly across both
sides; real books load it onto the longshot. So a longshot's proportional "fair" probability is too
HIGH, and since EV = fair x odds - 1, an inflated fair manufactures positive EV out of nothing. A
longshot-ONLY tail is exactly that signature. Re-run with Shin:

                        mean EV     +EV quotes      mean +EV       max
    proportional        -0.0347     17/166 (10.2%)   +0.0600     +0.1358
    SHIN                -0.0519      5/166 ( 3.0%)   +0.0045     +0.0088

    deep longshots <.15   proportional +0.0139  ->  Shin -0.1176      a 13-point swing
    heavy favourites      proportional -0.0494  ->  Shin -0.0371

The five survivors average +0.45%, inside noise and below any transaction cost. NO MONEYLINE EDGE.
This is EXP-015's failure mode from the golf phase, carried forward and caught before it became a
bet - the tail sat entirely in the band the de-vig distorts.

⚠️ ALSO RETRACTED: a persistence test claimed "the tail PERSISTS" on a sample of ONE. Change-only
storage means an unchanged price writes no new row, so only 6 quotes appeared at 2+ snapshots. The
claim was meaningless and is withdrawn.

## TN-020 — the FanDuel line was never in `handicap`, and the schema bug REPEATED

FanDuel leaves `handicap` at 0.0 on every tennis market and puts the number in the RUNNER NAME:
"Over 36.5", "Ben Shelton +2.5". Nothing was lost - the information was always in runner_name - but
the TN-017 totals join found ZERO overlap purely because it compared against handicap=0. A parsed
`line`/`side` column now makes totals and handicaps joinable: totals 13.5-60.5, game handicaps
-14.5 to +13.5, set totals 8.5-10.5.

⚠️ TN-014 REPEATED, and was caught only by the check TN-014 taught. ALTER TABLE appends, so adding
line/side put them at the END while the patched INSERT followed the DDL and supplied them before
`odds`. The next cron tick would have written odds into `line`. Recording the lesson did not
prevent the second occurrence, because ALTER is the convenient path and the DDL is where you look.
The durable fix is not a rebuild but an ASSERTION: the collector now compares the LIVE column order
against the exact list it inserts and REFUSES TO WRITE on mismatch.

⚠️ SECOND PARSE BUG: "Ben Shelton 6-0" matched the handicap pattern on its trailing "-0", so every
CORRECT_SCORE market reported a line of -6.0 to 0.0. A handicap is written " +2.5" with a SPACE
before the sign; a scoreline has a digit there. Requiring the space separates them, and
correct-score markets are now excluded from parsing outright. Verified after: 0 correct-score rows
carry a line, down from ~2,100.

## ANSWER: IS THERE AN EDGE IN ANY OF THESE MARKETS?

    MONEYLINE     NO. Mean EV -0.035 = FanDuel's own hold; the longshot tail collapses under Shin
                  (17 -> 5 quotes, +6.0% -> +0.45%). And separately, our model trails de-vigged
                  Pinnacle by 0.039 log-loss at the public-data ceiling.
    SET BETTING   NO. TN-002: FanDuel prices sets at +0.1082 against Pinnacle's +0.1116 - the same
                  number - at a 10.6% hold on a 4-runner book.
    TOTAL GAMES   UNTESTED. Blocked until now by the handicap=0 issue; the line is parsed and the
                  Pinnacle join is possible. FanDuel hold 6.5%.
    SET SPREAD    UNTESTED. Lines now parsed (MAIN_SET_GAME_HANDICAP -3.5..3.5).
    SET WINNERS   UNTESTED, and the most interesting of the three: at 4.7% hold it is the CHEAPEST
                  FanDuel tennis market, cheaper than its own moneyline. Pinnacle does not quote it
                  directly, but a sharp reference is derivable from its moneyline plus set total.

## TN-021/023 — the three untested markets  ❌ NO EDGE IN ANY

All references SHIN-devigged from the start, since TN-019 showed proportional de-vigging
manufactures a longshot edge.

    TOTAL GAMES     n=100  mean EV -0.0840   ZERO +EV quotes. Worse than FanDuel's own 6.5% hold,
                    so FanDuel's totals are dearer than Pinnacle even net of margin.
    GAME HANDICAP   n= 46  mean EV -0.1036   1 of 46 +EV, at +0.5%.
    SET WINNERS     n=172  ZERO quotes below the sharp-implied interval.

⚠️ A +45% "EDGE" WAS FOUND, DIAGNOSED AND RETRACTED. The first set-winner pass reported mean EV
+0.4497 with a max of +1.4751. No book is 45% wrong; that is a bug, and the rule from the golf
phase applies - when an effect is impossibly large, audit before believing.

The derivation used Pinnacle's spr_home as P(wins 2-0). It is provably not: Krueger's moneyline
implies M=0.169 while spr_home reads 0.400, and no player wins 2-0 more often than they win the
match. Spread values cluster at 0.4-0.6 on every match - a handicap line set near coin-flip. The
tell was in the worked examples: the FAVOURITE's derived fair was plausible (EV -0.023) while the
UNDERDOG's was nonsense (0.685 against M=0.294), which is the signature of a mis-assigned term.

FIXED BY PARTIAL IDENTIFICATION, which is what the data actually supports. From the moneyline and
set total alone, P(A wins set 1) = a + (1-S)/2 with a = P(A 2-0) NOT pinned down, only bounded:
    max(0, M+S-1) <= a <= min(M, S)
so the honest object is an INTERVAL. Same lesson as "top N and ties is not point-identified" in
golf: a point estimate invents information the market never gave.
    168 of 172 FanDuel quotes fall INSIDE the interval, 4 above, ZERO below.
Since FanDuel's implied probability contains its vig it should sit above a fair number anyway, so
inside or above proves nothing. Nothing generous exists.

## TN-024 — IS THERE HEADROOM IN THE MONEYLINE MODEL?  ❌ NONE

"Can our model beat Pinnacle" has been answered no for three phases, and it is the wrong question.
A model can be strictly worse standalone and still improve a sharp price if its errors are
uncorrelated. The right test is a blend in log-odds space with the weight fitted on train:

    logit(p_blend) = (1-w) * logit(p_pinnacle) + w * logit(p_elo)

Elo built chronologically from 29,385 match results (overall + surface, updated only AFTER each
prediction), joined to 20,481 Shin-devigged Pinnacle prices. Train 2015-2023, test 2024-2025.

    weight   0.00     0.02     0.05     0.10     0.15     0.20     0.30     0.50
    train LL .58296  .58306   .58326   .58375   .58441   .58525   .58753   .59457

    -> OPTIMAL WEIGHT 0.00, and log-loss rises MONOTONICALLY with any weight on the model.
    held out: Pinnacle alone .59503 | blend at w=0 .59503 | Elo alone .62937
    winner-picking accuracy: Pinnacle 0.673, Elo 0.629

NOT "a little information" - ZERO. Every positive weight makes the forecast worse, which is a
stronger result than a small optimal weight would have been: it means Pinnacle already contains
everything a public-data Elo knows, with nothing left over.

⚠️ SCOPE: this tests ELO, not every conceivable model. A genuinely different information source -
point-by-point data, injury or fitness information, anything non-public - is untouched by this
result. What is closed is the public-data ratings approach, and it is closed completely.

## TENNIS: WHERE IT STANDS

    MONEYLINE      NO EDGE. FanDuel mean EV -0.035 = its own hold; the longshot tail was a de-vig
                   artifact (17 -> 5 quotes under Shin). And NO HEADROOM: optimal blend weight 0.00.
    SET BETTING    NO EDGE. FanDuel prices sets at +0.1082 vs Pinnacle's +0.1116, at 10.6% hold.
    TOTAL GAMES    NO EDGE. Mean EV -0.084, zero +EV quotes.
    GAME HANDICAP  NO EDGE. Mean EV -0.104.
    SET WINNERS    NO EDGE. Zero of 172 quotes below the sharp-implied interval.
    ACES           UNRESOLVED, and the only thread left. No sharp reference exists, so it cannot be
                   settled by comparison - only by settling the model against realised ace counts.
                   The model is built and near-unbiased; the results collector is not.

## TN-025/028 — DO FORM, SURFACE, FATIGUE, H2H OR RANK ADD ANYTHING OVER PINNACLE?  ❌ NO

The honest benchmark is the PRICE, not our own model. Earlier work found these worth +0.005 AUC
over Elo, but beating Elo is easy and irrelevant: if Pinnacle already prices a factor, knowing it
is worth nothing however real the factor is.

Design: orient each match by NAME-SORT (p1 = alphabetically first, y = 1 if p1 won), fit
logit P = a + b*logit(p_pinnacle) + c*feature on 2015-2023, score on 2024-25. Sanity check that
the orientation is unbiased: p1 win rate 0.506.

    factor          n       coef      t     OOS delta LL
    form_10      3478    -0.6271  -6.59       -0.00039
    form_delta   3478    -0.2883  -3.31       +0.00044
    surf_edge    3719    +0.0001  +0.47       +0.00031
    h2h           805    -0.0784  -0.58       +0.00018
    rank_gap     3716    -0.0515  -2.41       +0.00002
    ht_gap       3716    +0.0020  +0.12       +0.00027
    rest_days / load_14  see the leak below

NOTHING HELPS. Recent form is the only factor with a signed, surviving coefficient, and it is worth
0.0004 nats of log-loss - against a 4.3-4.7% hold, unexploitable by three orders of magnitude.
SURFACE SPECIALISATION IS THE MOST STRIKING NULL: surf_edge, the "clay-courter on clay" claim, has
t = +0.47 and makes out-of-sample prediction WORSE. Head-to-head is nothing. Rank adds nothing over
the price, which is unsurprising since the price is built from it.

⚠️ THREE FAILED DESIGNS BEFORE A VALID ONE, all mine, all worth recording:

  1 WINNER-ORIENTED ONLY. Every row had y=1, so the logistic intercept ran to infinity and EVERY
    feature "helped" by the entire log-loss (~0.60). Standard errors came back as 1311 and 1917,
    which was the tell.
  2 MIRRORED ROWS. Emitting (z, y=1) and (-z, y=0) ties the feature's SIGN to the LABEL by
    construction, so any feature with a winner/loser asymmetry separates the classes perfectly.
    rest_days returned t = -73 and a 0.14 log-loss "improvement" over a sharp closing price - a
    gain that would be worth a fortune and cannot exist in a 4.7%-hold market.
  3 WITHIN-TOURNAMENT ORDERING. TML stamps ONE tourney_date on every round, so "ORDER BY date"
    leaves matches inside an event in arbitrary order and a final can be replayed before its own
    first round. Any running-history feature then sees LATER ROUNDS of the same event - which a
    player only reaches by WINNING. Direct look-ahead, and it explains both signs exactly:
    load_14 positive (recent matches include rounds they had to win) and rest_days negative
    (rest 0 means a same-event match was already processed, i.e. they advanced).

    PROOF: re-sorting by (date, round) collapses it.
        date only     rest t=-2.92  load t=+1.66      (and a DIFFERENT sort gave t=-52)
        date + round  rest t=-1.96  load t=+1.08, NEITHER helps out of sample
    The magnitude depended entirely on an arbitrary sort order, which is the definition of an
    artifact.

## WHY TENNIS IS HARD, AND WHERE AN EDGE COULD STILL LIVE

Tennis is the easiest sport to MODEL and that is exactly why it is hard to BEAT. One-on-one, no
team noise, point-level structure, enormous match volume - so every modeller converges on similar
numbers and the price already contains them. The vig confirms it: Pinnacle 4.7%, FanDuel 4.3%,
tighter than anything measured in golf. A tight market is a confident market.

MEASURED AND CLOSED:
    every market both books quote  - FanDuel is Pinnacle plus margin (TN-017/021)
    the public-data ratings model  - optimal blend weight on Elo is 0.00 (TN-024)
    every classic factor           - form, surface, fatigue, H2H, rank, height (TN-027)

WHAT IS NOT CLOSED, in descending order of plausibility:
    SPEED           FanDuel lags Pinnacle by minutes. That is a stale-line race, won with
                    infrastructure and execution, not with a better model. Untested here.
    NO-REFERENCE    markets nobody prices sharply - aces being the live example. Unresolved, and
                    handicapped by being one-sided.
    NON-PUBLIC      injury, fitness, travel, court-speed measurement. Nothing in this programme
                    touches it, and it is the only class of information the price provably lacks.
    IN-PLAY         untested here entirely.

## TN-029 — BEST-EFFORT MONEYLINE MODEL + LIVE FORWARD TEST

Built at the user's direction after they disagreed with the no-edge conclusion. Their objection was
fair: the earlier result showed a CRUDE Elo failing against Pinnacle's CLOSE, which is the weakest
model against the hardest bar.

MODEL. Three components, tuned on 2015-2023, held out on 2024-25 (n=3,719):

    Elo, tuned (K=32, surface blend 0.3)          log-loss 0.62875
    POINT model (serve/return -> exact recursion)          0.82571
    STACK (Elo + point)                                    0.62807
    Pinnacle (Shin-devigged)                               0.59503

The point model is a genuinely different object from Elo - it estimates serve strength and return
strength separately (p_A = s_A + (S - o_B)) and runs the exact point -> game -> set -> match
recursion, validated on symmetry: game_win(0.50)=0.5000, set_win(0.64,0.64)=0.5000, and best-of-5
correctly amplifying the stronger player (0.8405 -> 0.8934).

IT SCORED WORSE THAN A COIN FLIP (0.826 against 0.693) AND THE REASON IS STRUCTURAL. The recursion
amplifies about tenfold - a 0.04 gap in point probability becomes a 0.69 match line - while a single
match measures p only to +-0.09. Estimation error explodes into overconfidence. It earned a NEGATIVE
weight (-0.109) in the fitted stack. This is not a tuning failure; it is the signal-to-noise of
aggregate serve statistics meeting a highly non-linear map.

DOES ANY OF IT ADD TO PINNACLE? weight on Pinnacle 1.0703, weight on our stack -0.1292, held-out
delta -0.00058. The NEGATIVE weight is the finding: the blend improves by leaning AGAINST us, and
most of the gain is Pinnacle's own log-odds being extremised (weight > 1), which needs no model.

CALIBRATION, and the distinction that settles it:
    logit(p_true) = 0.0050 + 0.9452 * logit(p_model)   fitted on 34,703 historical matches
    2025+ held out: raw 0.62047 | calibrated 0.61992 | market 0.60064
Calibration closes 2.8% of the gap. So the model is WELL CALIBRATED AGAINST OUTCOMES AND LESS
INFORMATIVE THAN THE MARKET - different properties, and only the second one matters here. A
well-calibrated but less-informative model sits nearer the base rate, so against a sharper price it
will ALWAYS appear to find value on longshots. Every live scan confirmed it: all 40 flagged bets
were underdogs at +27% to +48%, and damping the model made those edges LARGER, not smaller.

## LIVE FORWARD TEST — running

`ml_live.py scan` every 30 minutes; `ml_live_ingest.py` + `settle` daily at 06:20 UTC.
Ledger `ml_ledger.sqlite`. PAPER ONLY - nothing places a bet.

PRIOR RECORDED ON EVERY ROW, before any result arrives: "calibrated LL .61992 vs market .60064 -
EXPECTED TO LOSE". A forward test is only worth running if its prior is written down first; if the
ledger comes back profitable over a real sample that is evidence AGAINST every retrospective result
here and worth more than any backtest, and if it comes back negative it confirms them. Either way
it is decided by outcomes rather than by my judgement.

⚠️ FOUR BUGS CAUGHT IN THE HARNESS BEFORE IT WAS TRUSTED, every one of which would have produced a
fake edge:
  1 SILENT DEFAULT. TML is ATP-ONLY and the WTA fetch had timed out, so every WTA player was
    unknown, defaulted to Elo 1500, returned EXACTLY 0.500, and against a 101.0 longshot read as a
    4,950% edge. 88 such bets were logged and purged. Now: refuse below 20 matches of history,
    reject an exact-0.500 output as the default's fingerprint, cap edges at 50%.
  2 ATP-ONLY ELO. Even after the gate, Elo was seeded from the ATP-only serve table. Rebuilt from
    results_live: 57,386 matches, BOTH tours, 2015-2026.
  3 NAME FORMAT. FanDuel writes "Yuliia Starodubtseva", tennis-data writes "Starodubtseva Y." - so
    nothing joined and the gate correctly refused all 103 matches. One canonical (surname, initial)
    key now spans both.
  4 ORIENTATION. The market was stored winner-oriented while the label was name-sort oriented,
    making Pinnacle score 0.80245 - worse than our Elo, which is impossible and was the tell.

DATA CONSTRAINT: TML's serve statistics stop 2026-01-17 while results run to 2026-08-30, so the
point model is 225 days stale. It is computed and RECORDED on every row but does NOT price; the
live model is the calibrated Elo, which can be kept fully current from results.

## TN-030 — FOUR BUGS IN THE LIVE HARNESS, all of which INFLATED the record

Three surfaced only because the user asked how the already-finished picks had done. Every one made
a losing model look better, which is the direction that matters.

1 IN-PLAY PRICES BANKED AS PRE-MATCH. The scan took MAX(collected_at) - the LATEST quote - which
  for a match already underway is an in-play price that knows part of the result. Arnaldi was
  logged at 2.60 having opened at 1.57; the drift existed precisely BECAUSE he was losing. Betting
  a drifted price on a losing selection is where fake edges are manufactured.
  This is the deadline-contamination class the golf phase named, repeated verbatim.
  FIX: require collected_at <= start_time. No fallback - a match with no pre-match quote is
  skipped, because the only quote available is the contaminated one.

2 FANDUEL REWRITES start_time WHEN A MATCH GOES LIVE, and that is why the filter is subtle:
      pre-match quotes carry the SCHEDULED time   (17:00)
      in-play quotes carry the ACTUAL start       (16:43)
  So the same match legitimately holds two start_times, and a ledger row can store either
  depending on when it was written. The filter is still correct - it now returns Arnaldi 1.58 and
  Duckworth 2.42 instead of the 2.60 in-play drift - but the ambiguity is worth knowing.

3 BOTH SIDES OF THE SAME MATCH LOGGED. The ledger key was (event, pick, start_time). When FanDuel
  moved a match from 16:43 to 17:00 it re-entered as a new row, and by then the model's edge had
  flipped to the OPPONENT. The ledger held Arnaldi 2.60 AND Duckworth 2.42 on one match - an
  implied 79.8% book, which no sportsbook offers. Two snapshots stitched together, reading as free
  money. FIX: key is (event, pick), and a match that already carries a bet is skipped. First
  opinion stands; the model changing its mind is not a second opportunity.

4 SILENT 0.500 DEFAULT (found earlier). TML is ATP-only and the WTA fetch had timed out, so every
  WTA player was unknown, defaulted to Elo 1500 and returned EXACTLY 0.500 - which against a 101.0
  longshot reads as a 4,950% edge. 88 such bets were logged and purged.

STANDING AUDIT, because this file has now been patched eight times and the next bug will not
announce itself either. `audit_live.py` runs twice an hour and asserts nine invariants, each a
MAGNITUDE rather than a truthiness:
    every logged price existed pre-match | one bet per match | never both sides
    no 0.500 defaults | edge == p*odds-1 | edges within [3%, 50%]
    pick/opp distinct and both named in the match | odds plausible | probabilities inside (0,1)
Current state: 52 bets, ALL NINE PASS.

## FIRST RESULTS — 31 August, indicative

Graded from in-play price collapse because official results post next morning and ESPN's
scoreboard is 403 from this box. Only DECIDED rows counted: a side at <= 1.10, or its opponent
at >= 8.0. Stake 1u = $100 at the PRE-MATCH price.

    Virtanen   5.30  LOST   -100        Fearnley  3.20  LOST  -100
    Vacherot   1.79  WON     +79        Baez      6.20  LOST  -100
    Tsitsipas  5.40  WON    +440        Alcaraz   1.19  WON    +19

    record 3-3 | P&L +239 | ROI +39.8% on 6 bets

⚠️ THE ENTIRE PROFIT IS ONE BET. Tsitsipas at 5.40 returned +440 while the other five net -202.
That is the defining property of a longshot book: one hit at 5.40 covers three losses and prints a
fake 40% ROI. The portfolio is 71% underdogs at mean odds 3.85, so swings this size are routine in
both directions. Nothing is readable before roughly 200 settled bets, and the prior recorded on
every row before any result arrived says this is expected to LOSE.
