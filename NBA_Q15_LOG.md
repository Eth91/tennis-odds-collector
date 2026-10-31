# NBA_Q15 experiment log

Every experiment, in order, failures included. The protocol is `NBA_Q15_PREREG.md`. Results are TRAIN/VALIDATE
unless marked TEST.

## E1: the market (2026-10-31, about 09:20 UTC)
- **Data:** 286,731 props (TRAIN 130,726, VALIDATE 131,419, TEST A 24,586). 99.4% matched to a box score. Pushes
  dropped from the rates.
- **The market's no-vig over probability against what happened:**

| | TRAIN | VALIDATE |
|---|---|---|
| over rate / mean no-vig over | 48.1% / 49.8% | 48.7% / 49.6% |
| log loss: market / coin (base rate) | 0.6873 / 0.6925 | 0.6875 / 0.6928 |
| every over, FanDuel or DraftKings | −8.7% | −6.2% |
| every under, FanDuel or DraftKings | −1.7% | −3.9% |
| every under, best of 4 books | −1.9% | −3.0% |

- **Calibration:** the miss is on props where the under is the favourite. At no-vig 0.35–0.45, overs hit 39.5% /
  40.3% against 41.9% priced. At 0.45–0.50: 45.9% / 47.1% against 48.1–48.3%. At 0.55+ the price is right.
- **Reading:** props are close to coin flips, and the market only beats a coin by about 0.005 in log loss. Any edge
  is a few points of probability. The known structure: overs are over-priced, most where the under is already
  favoured, but the margin (about 4–5% at FanDuel and DraftKings) is bigger than the bias.

## E2 / E3: market-anchored logistic and LightGBM, walk-forward by month (2026-10-31, about 09:35 UTC)
- **Setup:**
  - Every month is predicted by a model fit on all decided props before it. TRAIN is predicted from 2023-12.
  - 31 features (`nba_q15.features`). The market's logit is a feature (logistic) or the starting score (LightGBM).
  - Bets: the side with the higher EV ≥ τ, at the better of FanDuel and DraftKings at the consensus line.
- **Log loss, model vs market:**
  - logistic: 0.68708 vs 0.68751 (TRAIN), 0.68719 vs 0.68751 (VALIDATE). A small, consistent gain.
  - LightGBM: 0.68904 vs 0.68751 (TRAIN, overfits the early months), 0.68746 vs 0.68751 (VALIDATE).

| τ | logistic TRAIN | logistic VALIDATE | LightGBM TRAIN | LightGBM VALIDATE |
|---|---|---|---|---|
| 3% | 21,891, +1.8% | 11,626, +1.3% | 33,603, −0.1% | 18,180, +0.1% |
| 5% | 13,547, +2.1% | 5,085, +2.5% | 24,804, +0.8% | 10,501, +1.5% |
| 8% | 6,065, +4.0% [+1.1, +6.8] | 1,246, +4.3% [−1.2, +9.6] | 15,097, +2.0% | 4,180, +1.8% |
| 12% | 1,797, +1.2% | 187, +14.0% | 7,037, +1.8% | 1,037, +3.1% |

- **By side:** the logistic model's unders make +3% to +6% at τ 3–8% in both seasons. Its overs lose −2% to −5% in
  both, even when it calls them +EV, so the model is miscalibrated on overs.
- **Reading:** there is real but small information beyond the price (about 0.0004 in log loss). Selected bets
  return low single digits. τ ≥ 12% is too few bets to read (VALIDATE's +14% is 187 bets).

## E4–E6: where the edge sits, and five rules fixed from TRAIN (2026-10-31, about 09:55 UTC)
- **E4 (TRAIN only):** the logistic model's under edge is biggest where the naive projection (L5/L10 minutes × rate)
  is far below the line. All unders with r_proj ≤ −0.4: +9.3% (1,692).
- **E5 (TRAIN only), unders with r_proj ≤ −0.3:** +7.4% (4,159). Best:
  - prices from even to −150;
  - points and combo markets (+11%); threes +1.5%, assists +3.9%;
  - teammates out (216 props without one: −8%).
- **E6:** five rules, all with 12+ minutes over the last 10 (bettable under the 2026-10-16 restriction), at the better
  of FanDuel and DraftKings.

| rule | TRAIN | VALIDATE | VALIDATE halves |
|---|---|---|---|
| C1: r_proj ≤ −0.3, −150 or better, no threes or assists | 2,628, +9.8% [+4.8, +15.1] | 1,801, **−4.8%** [−10.6, +0.8] | −4.9%, −4.7% |
| C2: C1 + model EV ≥ 3% | 1,212, +11.2% | 701, **−0.5%** | −1.2%, −0.1% |
| C3: model unders, EV ≥ 8% | 4,419, +6.3% [+2.7, +9.4] | 1,045, +4.3% [−1.9, +10.7] | −1.2%, +7.2% |
| C4: C1 at r_proj ≤ −0.4 | 1,312, +11.0% | 877, **−3.0%** | +6.0%, −7.0% |
| C5: C1 with teammates out | 2,533, +10.5% | 1,753, **−5.0%** | −5.6%, −4.7% |

- **Reading:** the deep-under rules found on TRAIN fail on VALIDATE, which is overfitting or a regime change. C3
  holds at about +4%, short of the bar.
- **No candidate meets the pre-registered VALIDATE bar** (≥ +10%, positive halves), so TEST A is not spent on these.

## TEST A slots, registered before any postseason grading (2026-10-31, about 10:05 UTC)
The existing under rules, frozen in `NBA_UNDER_PREREG.md` (code at 0d328161ae, `nba_under.py`), have never been graded
on postseason games. Their 2023-24 / 2024-25 results were picked after looking at both seasons. They take the first
TEST A slots, unchanged:
1. **UNDER3050** (amendment 4): ROLE1 v3 minutes × rates is 30–50% below the line; the under at −150 or better; not
   threes.
2. **UNDER3050L** (amendment 9): UNDER3050 less flags whose line ÷ last-5 average is in (1.05648, 1.41667].
3. **UNDER20P** (amendment 1): the projection < 80% of the line; the under at −150 or better; not threes.

- **Prices:** the original backtest's: the better of FanDuel and DraftKings at the main line nearest even, tip − 30.
- **Inputs:** the postseason box scores (`nba_postseason.logs_post`) join the regular-season rows, so every input
  is from games before tonight, as in the original.
- **Each is judged on the pre-registered bar** (NBA_Q15_PREREG.md: ROI ≥ 15%, ≥ 300 bets, > 0 in each postseason,
  one-sided bootstrap lower bound > 0 at α = 0.01).
- Also reported, without changing the verdict: the 12+ minute (bettable now) subset, and FanDuel-only prices.
- Slots 4–5 stay open.

