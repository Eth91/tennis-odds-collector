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
