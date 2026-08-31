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
