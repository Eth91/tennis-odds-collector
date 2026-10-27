# PRE-REGISTRATION: why each prop won or lost, and simple filters from it

Written 2026-10-27, before any outcome was split by any condition. Research only: nothing is bet.

**User:** "take all the props and news and context we have from the 3000 props we collected for the past few
days, figure out why each prop won or lost, then create our selection criteria or filters from there. The only
rule is it can't get super hyperspecific criteria."

## Data
- **Props:** every prop at FanDuel's main line at tip − 30 min, 2026-10-22..26. That is FanDuel's first
  observation at or after tip − 30, as known then: the `cp30` FanDuel rows of `nba_ml1.py --build`, rebuilt by
  `nba_why.py`.
- **One row per (game, player, market)**, with:
  - the over and under prices;
  - the result (over, under, push; a DNP is dropped);
  - CLV per side (EV at FanDuel's close, as in the side-by-side).

## Part 1: why it won or lost (description)
Per prop:
- actual − line;
- the minutes effect: (actual minutes − last-10 minutes) × last-10 rate;
- the rate effect: actual minutes × (actual rate − last-10 rate);
- whether the game was a blowout (final margin ≥ 15);
- whether he started (box score).

Reported for over winners vs under winners:
- the share explained by minutes vs rate;
- the share of unders where he played ≥ 5 min under his last-10;
- blowout rates.

## Part 2: filters (pre-game information only)
**Conditions** (fixed buckets, nothing tuned):
- **market:** points / rebounds / assists / threes / combo (P+R, P+A, R+A, PRA);
- **line vs last-10 average**, relative: ≤ −10% / within / ≥ +10%;
- **minutes trend**, last 3 − last 10: ≤ −3 / within / ≥ +3;
- **role**, last-10 minutes: < 20 / 20–30 / ≥ 30;
- **teammate regular Out/Doubtful tonight:** yes / no;
- **opponent regular Out/Doubtful tonight:** yes / no;
- **team news in the last 6 h** (a regular newly out): yes / no;
- **own status listed** (Questionable/Probable): yes / no;
- **FanDuel line since open:** up / unchanged / down;
- **DraftKings fair minus FanDuel fair (over):** ≥ +0.02 / within / ≤ −0.02;
- **home / away**;
- **back-to-back:** yes / no;
- **price of the side:** < 1.80 / 1.80–2.00 / > 2.00.

**A filter** = a side (over or under) + 1 or 2 conditions from different rows above.

**The not-hyper-specific rule:**
- at most 2 conditions;
- only these buckets;
- the filter covers ≥ 5% of the props it is chosen on;
- it fires on every date it is chosen on.

**Selection:**
- On a set of dates, a filter is selected if its ROI at FanDuel's price is > 0 on every date and > 0 pooled.
- The bet set is the union of selected filters, one bet per (prop, side). A prop with both sides selected is
  skipped.

**Validation, all decided now:**
1. **Leave one day out.** Select on 4 dates, bet the 5th; pool the 5 held-out days. Report ROI and CLV
   (date-clustered).
2. **Shuffle control.** Rerun the selection on all 5 dates 200 times, with results shuffled within (date, market)
   (prices and conditions kept). Report how many filters get selected by chance (median, 95th percentile).

**Pass** (all three):
- held-out pooled ROI > 0;
- held-out pooled CLV > 0;
- the number of filters selected on all 5 dates > the shuffle's 95th percentile.

**If it passes:** the filters selected on all 5 dates become one side-by-side rule (WHY5, registered with its
fingerprint), judged forward.

**If it fails:** the report shows what was found, set against what chance produces. No registration.
