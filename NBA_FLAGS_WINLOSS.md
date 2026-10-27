# Why the flags win and lose (2026-10-27)

Pre-registered in `NBA_FLAGS_WL_PREREG.md`. Code: `nba_flags_wl.py` (diagnosis) and `nba_flags_model_test.py`
(the registered model test).

## The short version
- **Why we lose: we overestimate the plays we pick, mostly their minutes.**
  - The wowy projection is accurate on average: across all 48k backtest candidates, minutes come in at
    1.01× projected and the per-minute rate at 1.00×.
  - The plays it flags come in about 2.5 units below projection in both seasons, and live too.
  - That's the winner's curse. We flag a play because its projection is high, and part of a high projection
    is noise.
  - More than half the losses are the player getting 4+ minutes fewer than projected.
- **Why we win: the rate holds, and the line was low.**
  - In wins the minutes are about as projected (slightly short) and the per-minute production beats it.
  - When FanDuel's closing line moved toward the flag, the flags went 12-3. When it moved against, they
    went 4-8.
- **What isn't driving it** (noise in one season or the other): excess band, price band, the absent
  star's minutes, absence game 1 vs 2 vs 3–4, back-to-backs.
- **Two patterns hold in both seasons, and the card already uses them:**
  - 2+ stars out loses: −11.1% and −6.8% (amendment 29 keeps those off).
  - The 3–8 minutes band beats < 3.

## Live: every graded shadow flag, 2026-10-22..26
One opportunity per play (its earliest flag), graded at the flagged line and price.

| | n | W-L | units | ROI | actual − proj | actual − line |
|---|---|---|---|---|---|---|
| all | 81 | 48-33 | +7.50 | +9.3% | −2.43 | +1.44 |
| wowy (current) | 50 | 28-22 | +1.12 | +2.2% | −3.21 | +0.76 |
| wowy_v0 (pre-amendment-7) | 15 | 13-2 | +8.74 | +58.2% | +0.35 | +5.63 |
| priced | 15 | 7-8 | −1.36 | −9.0% | −0.68 | +1.30 |
| on the card | 9 | 5-4 | +0.22 | +2.5% | | |

- **Minutes** (25 plays with box-score minutes so far):
  - minutes came in at 0.92× projected and the rate at 0.77×;
  - 64% of losses were 4+ minutes short.
- **By news latency:** ≤ 15 min 12-12 (−9.4%); 15–120 min 3-2; 2 h+ 33-19 (+17.8%). Tonight's late flags
  did most of that. The sample is too small to say fresh news loses, but it does not support the
  fresh-news rule yet either.
- **By stale line:** STALE (unchanged since before the news) 9-12 (−23%); POSTED AFTER NEWS 22-15 (+10%).
  Also too small to judge.
- **CLV:** FanDuel's closing line moved toward the flag 20% of the time and against it 16%, a mean of
  +0.1 points. That is no sign of beating the close.

## Backtest: 2023-24 and 2024-25, tip lines (FanDuel + DraftKings)

| | season | n | ROI | actual − proj | minutes realized ÷ projected | rate realized ÷ projected | losses 4+ min short |
|---|---|---|---|---|---|---|---|
| all candidates | 23-24 | 21,617 | −10.7% | +0.04 | 1.01 | 1.00 | 33% |
| | 24-25 | 26,062 | −5.1% | +0.36 | 1.01 | 1.02 | 34% |
| flagged (excess ≥ 1) | 23-24 | 1,610 | −3.9% | −2.58 | 0.92 | 0.87 | 54% |
| | 24-25 | 1,947 | −2.8% | −2.44 | 0.91 | 0.88 | 50% |
| card universe* | 23-24 | 101 | +27.5% | −2.20 | 0.91 | 0.96 | 54% |
| | 24-25 | 113 | +12.6% | −2.71 | 0.87 | 0.92 | 60% |

\*The card universe: minutes band 3–8, 1 star out, absent star < 32 min, price ≥ 1.80, excess 1–2, rebounds
included. Its filters were chosen on these same seasons (amendment 28), so its ROI is in sample and overstates
what to expect.

**Wins and losses split into minutes and rate** (card universe, stat units, 23-24 / 24-25):
- **wins:** minutes −1.0 / −1.1, rate +1.8 / +1.4. The player gets about his minutes and produces above rate.
- **losses:** minutes −2.7 / −2.6, rate −5.2 / −4.2. On average he plays 4.5 / 6.3 minutes fewer than
  projected.

**By stat (flagged, excess ≥ 1):** PRA −15.7% / −3.1%, rebounds −2.0% / −4.7%, points −5.2% / +7.8%.
Rebounds on the card universe flip: +36.2% / −7.3%.

## The registered model test (prereg amendment 1): no change adopted
Two changes, each aimed at the overprojection, fit on 2023-24 for accuracy only:
- **R:** rate shrinkage raised from K = 60 to 240 pseudo-minutes (the grid's minimum-error K).
- **M:** projected minutes = 6.54 + 0.391 × last-10 + 0.396 × last-3 + 0.164 × d_min.

The test's check reproduces amendment 30's current card exactly (no rebounds: 35 bets +20.7%, 38 bets +40.4%).

| card (current rules, rebounds included) | 2023-24 | 2024-25 |
|---|---|---|
| current projection | 78 bets, +33.5%, +26.1u | 89 bets, +10.4%, +9.3u |
| R | 67 bets, +19.3%, +13.0u | 69 bets, +7.8%, +5.4u |
| M | 69 bets, +15.1%, +10.5u | 63 bets, −1.1%, −0.7u |
| R + M | 50 bets, +19.0%, +9.5u | 49 bets, +15.0%, +7.4u |

**Decision (as registered): keep the current projection.** No change beat it in both seasons; none beat it
in either.

**Why more accuracy doesn't help.** Both changes are more accurate, including on 2024-25, the season they
were not fit on:
- minutes RMSE 7.60 → 7.13;
- rate error −2.3%;
- stat MSE on plays with lines 44.8 → 43.2.

FanDuel's and DraftKings' main line is better than all of them: an MSE of 38.2. When the projection disagrees
with the line by a margin, the line is usually right. A more accurate projection disagrees less often, so it
flags fewer plays. The plays it drops include winners on this card, whose filters were picked on these same
seasons.

The honest reading: the card's backtest edge rests on in-sample filters. The live forward record is the only
real test left. There is no clean held-out season with lines (2025-26 would need the Odds API, about 37k
credits).
