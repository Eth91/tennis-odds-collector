# PRE-REGISTRATION: ML1, a flagging model learned from everything we knew at the time

Written 2026-10-27, before the dataset was built or any model fit. Research only: nothing is bet, and
`nba_flags.LIVE_TIERS` stays empty.

**User:** "we can analyze all the info we knew at the time for the past 5 days as those are all logged, then
build a flagging model off of all those plays."

## Data: every prop, at fixed moments, as it was known then
- **Days:** the final game dates 2026-10-22 through 2026-10-26, replayed with `nba_replay` (the same View,
  observations and look-ahead guards as the side-by-side).
- **Checkpoints, per game:**
  - FanDuel's first observation at or after tip − 6 h, − 3 h, − 2 h, − 1 h and − 30 min;
  - FanDuel's first observation within 10 min after any report that newly lists a regular (≥ 20 min) of either
    team as Out or Doubtful.
- **Rows:** at each checkpoint, for each prop (game, player, market) and each book (FanDuel, DraftKings) with a
  main rung (two-sided, over nearest even money), one row per side at that book's main line and price.
- **Target:** EV at FanDuel's close = q × price − 1, exactly the side-by-side's CLV. Here q is FanDuel's closing
  no-vig probability of the side at the line (an over-only alternate is de-vigged at the main rung's overround).
  A row without a closing q is dropped.
- **Win/loss:** joined from the box scores and reported, never the target. Five days of outcomes are mostly
  noise.

## Features (each computed from what was known at the row's time)
- **Structure:** book (DraftKings = 1), side (over = 1), market (8 indicators), log minutes to tip.
- **Price against the books:**
  - EV now at FanDuel's fair price (FanDuel's current no-vig at the line × the price − 1);
  - DraftKings' fair minus FanDuel's fair at the line;
  - the other book's main line minus this book's, signed by side.
- **Movement so far:**
  - this book's main line change since its first observation, and over the last 60 min;
  - FanDuel's fair at the line minus its fair at the first observation;
  - all signed by side.
- **News:**
  - minutes since the latest regular newly Out/Doubtful on the player's team (capped at 24 h), and the same
    for the opponent;
  - regulars Out/Doubtful on each team's latest report;
  - the player's own latest status (Questionable, Probable).
- **The player:**
  - last-10 minutes;
  - minutes trend (last 3 − last 10);
  - the line minus his last-10 average of the market, signed by side.

## Model and validation
- **Model:** ridge regression of the target on the standardized features. The penalty is chosen from
  {1, 10, 100, 1000, 10000} by inner leave-one-day-out mean squared error.
- **Flag rule:** predicted EV at the close ≥ 0.02. The first checkpoint at which a (game, player, market,
  side) fires is the flag, at that book's price.
- **Outer validation, leave one day out (5 folds):** fit on 4 days, flag the 5th. Report, pooled over the
  held-out days:
  - flags' mean realized EV at the close, with a day-clustered interval;
  - ROI.
- **Baselines on the same held-out days:**
  - DK lag: EV now at FanDuel's fair ≥ 0.03, one feature, no fitting;
  - every row.

## Pass bar (decided now)
All four must hold for the held-out flags:
1. pooled mean realized EV at the close > 0;
2. above the DK lag baseline's pooled mean;
3. positive on ≥ 4 of the 5 held-out days;
4. ≥ 100 flags pooled.

**If it passes:** fit on all 5 days with the chosen penalty. Freeze the coefficients into rule ML1 (its
fingerprint covers its feature code and coefficients) and register it in `nba_sxs_rules.REGISTRY`, where the
side-by-side's bars judge it forward.

**If it fails:** no registration; the report says why.

**Honest limits:**
- Five days and about 45 games.
- The features were chosen with the latency and win/loss findings in mind, so the held-out days are the only
  check on the fit.
- A pass means "worth a forward test", not "it works".

---

## Result (2026-10-27, about 06:25 UTC): FAIL, so ML1 is not registered
- **Dataset:** 38 games over 5 dates; 64,152 rows, 52,416 with a closing price (`nba_ml1.py --build`).
- **Where it ran:** the build moved off the VM after its first attempt, because the VM was swapping with 82% CPU
  steal while live jobs ran. It ran on read-only snapshots of the four stores, taken with the SQLite backup API
  at 06:15 UTC.

| held-out flags (5 folds) | n | mean EV at the close [95%] | ROI (W-L) |
|---|---|---|---|
| ML1 | 72 | +2.0% [−0.5, +4.8] | −18.1% (30-42) |
| DK lag baseline (EV now at FanDuel's fair ≥ 3%) | 118 | +2.0% [+0.8, +3.6] | −8.7% (56-62) |
| every row (first checkpoint) | 6,168 | −6.2% | −6.2% |

**Checks:**
- pooled CLV > 0: yes;
- beats DK lag: **no** (+2.01% vs +2.03%);
- positive on ≥ 4 of 5 days: **no** (3);
- ≥ 100 flags: **no** (72).

**What it learned** (all 5 days; change in EV per standard deviation):
- EV now at FanDuel's fair: **+0.026**;
- the missing indicator for that EV: −0.008;
- DraftKings' fair minus FanDuel's: +0.007;
- over (vs under): −0.003;
- line move since open (toward the side): +0.002;
- FanDuel fair drift: +0.001;
- every news and player feature: |w| ≤ 0.0003.

The model rediscovered one signal, DraftKings' price against FanDuel's fair price. That signal is already in
the side-by-side as DK_LAGS_FD and T4_TIP30. None of the news, injury-count or player-form features predicted
the close in these five days.
