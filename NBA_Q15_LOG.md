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


## TEST A, slots 1–3: graded once (2026-10-31, about 10:40 UTC)
`nba_q15_under_post.py`, engine at 0d328161ae.
- **Harness check:** on the regular seasons the port gives amendment 4's numbers exactly (UNDER3050: 1,022 at
  +16.8% and 710 at +15.0%).
- **Data limits:**
  - The 2023 postseason starts on 2023-05-03, the first date with prices, so its first round is missing.
  - "12+ min" means 12+ projected (ROLE1 v3) minutes: the bettable subset under the 2026-10-16 restriction.
  - FanDuel-only results are the bets where FanDuel posted the chosen line.

| | UNDER20P | UNDER3050 | UNDER3050L |
|---|---|---|---|
| TEST A bets, ROI | **461, +15.0%** (+14.99%) | 88, +19.2% | 54, +15.8% |
| win / break-even | 62.5% / 54.4% | 64.8% / 54.2% | 63.0% / 54.1% |
| units, max drawdown | +69.1, 13.5 | +16.9, 8.5 | +8.5, 6.3 |
| 90% / 95% CI | [+5.0, +25.4] / [+3.1, +27.3] | [−2.6, +40.1] / [−6.7, +44.1] | [−10.9, +41.4] / [−16.4, +46.1] |
| one-sided lower bound, α = 0.01 | **+1.2%** | −11.1% | −22.6% |
| 2023 / 2024 / 2025 postseason | +43.9% (52) / +9.9% (211) / +12.8% (198) | +37.0% (18) / **−5.7%** (34) / +33.9% (36) | +46.7% (14) / +1.3% (23) / +10.1% (17) |
| 12+ projected minutes | 426, +16.1% (lower bound +0.7%) | 69, +30.6% | 41, +30.0% |
| FanDuel only | 265, +18.1% | 40, +24.9% | 22, +18.6% |
| VALIDATE (2024-25 RS), halves | +6.9% (+9.0%, +5.7%) | +15.0% (+16.9%, +13.8%) | +20.2% (+16.4%, +22.5%) |
| TRAIN (2023-24 RS) | +7.7% (3,916) | +16.8% (1,022) | +24.5% (786) |
| **verdict** | **fails** 1 (by 0.01 points) and 5 (VALIDATE < 10%) | **fails** 2, 3, 4 | **fails** 2, 4 |

- **TEST A by market (UNDER20P, read only, not used to choose anything):**
  - rebounds +18.0% (137), P+R +14.1% (69), R+A +21.9% (48), P+R+A +21.9% (49), assists +21.3% (39);
  - points +7.7% (69), P+A −0.3% (50).
- **Reading:**
  - Nothing passes the pre-registered bar.
  - **UNDER20P is the first rule in these studies with a significant edge on data no one had looked at:** 461
    postseason bets, positive in all three postseasons, and a lower bound above 0 after the 5-way Bonferroni.
  - Its edge is about +7% in the regular seasons and +15% in the playoffs. A fair expectation for a full season is
    the regular-season figure, high single digits, not 15%.
  - The 30–50% band has the higher ROI everywhere, but too few playoff bets to tell it from luck. Its band was chosen
    after looking at both regular seasons.
- **TEST A is now spent for the under family.** Any new candidate built from the projection ratio carries what
  these results showed, so slots 4–5 must be chosen on TRAIN/VALIDATE and their overlap with UNDER20P reported.

## E7: the engine's projection in the market-anchored model (2026-10-31, about 11:00 UTC; TRAIN / VALIDATE only)
- **Why:** the idea was on the list before TEST A was graded. E2's model only had a naive projection (L5/L10 minutes ×
  rate). The engine's ROLE1 v3 projection is what drives the under rules' regular-season edge.
- **What changed:** three features, from `nba_q15_proj.py` (engine at 0d328161ae):
  - the log of (projection + 0.5) ÷ (line + 0.5);
  - its negative part;
  - the projected minutes.
  
  Coverage: 97.6% TRAIN, 97.0% VALIDATE. Same walk-forward and same logistic model (C = 0.05).
- **Log loss, model vs market:** 0.68602 vs 0.68751 (TRAIN), 0.68610 vs 0.68751 (VALIDATE). That is about 3.5×
  E2's gain. LightGBM: 0.68764 / 0.68660, worse again.
- **Unders, model EV ≥ τ, 12+ projected minutes, better of FanDuel and DraftKings at the consensus line:**

| τ | TRAIN | VALIDATE | VALIDATE halves | VALIDATE bets a day |
|---|---|---|---|---|
| 6% | 10,617, +8.1% | 6,878, +6.9% | +10.4%, +4.0% | 43 |
| **8%** | 6,821, +9.7% [+6.7, +12.5] | **3,640, +12.1%** [+8.5, +15.9] | +16.3%, +8.4% | 23 |
| **10%** | 4,244, +10.2% [+6.7, +14.1] | **1,907, +18.4%** [+13.1, +23.4] | +22.8%, +14.6% | 12 |
| 12% | 2,634, +11.0% | 1,007, +19.5% | +25.4%, +13.9% | 7 |

- **At τ 8%, both seasons:**
  - **By market,** every market is positive:
    - TRAIN: points +10.9%, rebounds +8.8%, threes +7.3%, assists +6.7%.
    - VALIDATE: points +7.4%, rebounds +10.5%, threes +12.8%, assists +14.9%.
    - The combos make +9% to +19%.
  - **By price,** every band from −150 to +110 and up is positive.
- **Overlap with UNDER20P:** only 28% (TRAIN) / 30% (VALIDATE) of the τ 8% bets have the projection under 80% of the
  line. The other bets make +9.0% / +11.0% on their own. This is a broader signal than the under rules, not a copy.
- **Overs:** −1% to +2% on TRAIN at every τ. Left out.

## TEST A slots 4–5, registered before grading (2026-10-31, about 11:10 UTC)
Code: `nba_q15_model.py` and `nba_q15_proj.py`, in the commit that adds this entry. `validate` reproduces the table above.
4. **Q15_LR8:** E7's logistic model, unders only, EV ≥ 8%, 12+ projected minutes. VALIDATE +12.1%, halves +16.3% /
   +8.4%.
5. **Q15_LR10:** the same at EV ≥ 10%. VALIDATE +18.4%, halves +22.8% / +14.6%.

- **The model for each postseason** is fit on the regular-season props dated before it: 2024 on TRAIN, 2025 on
  TRAIN + VALIDATE. No postseason outcome is used for fitting. The 2023 postseason has no earlier props (prices start
  2023-05-03), so it uses the TRAIN fit, from games after it. This is said wherever its number is shown.
- **Prices:** the better of FanDuel and DraftKings at the consensus line (primary). Also reported: FanDuel only.
- **The bar is unchanged:** ROI ≥ 15%, ≥ 300 bets, > 0 in each postseason, lower bound > 0 at α = 0.01. Both meet
  the VALIDATE condition.
- **Caveat stated before grading:** the people choosing these had seen UNDER20P's TEST A result, and about 30% of
  these bets share its signal. The share of TEST A bets with the projection under 80% of the line is reported, so
  the overlap can be judged.
- **This fills all 5 slots.** TEST A is closed after this run.

## TEST A, slots 4–5: graded once, then found to be leaking (2026-10-31, about 11:20 UTC)
- **As registered** (projection `e7_proj.pkl`):
  - Q15_LR8: 1,360 bets, +26.7%.
  - Q15_LR10: 738 bets, +30.2%.
  - Both are positive in every postseason, with lower bounds of +17.9% / +19.0%.
- **That is twice VALIDATE.** That is a reason to look for a bug before believing it. Checked and clean:
  - **Box scores:** the three Finals clinchers match the real scores (DEN 94–89, BOS 106–88, OKC 103–91), and team
    minutes sum to 240.
  - **Snapshots:** 19–39 minutes before the scheduled tip in the playoffs, none after.
  - **Our features:** every rolling stat is shifted one game, and season sums run up to the night before.
- **The leak, in the engine's backtest projection** (`nba_tests4.player_games` → `nba_minutes.Season.v3` →
  `nba_role.project`):
  - **How it works:** the projection rescales the team's minutes to 240 over the players it treats as active. Active
    means: from the team's last 3 games, and logged minutes tonight. So a deep-bench player who gets a DNP-CD in a
    close game drops out, and his minutes go to everyone else. In a blowout he plays garbage time and stays in.
  - **The result:** the projection knows the final margin. Against a version where only rotation players can be out,
    it adds 2.1 minutes in games decided by 0–5 and 0.6 in games decided by 30+. The correlation with the margin is
    −0.32 (playoffs: 2.6 vs 0.45, −0.34).
  - **Who has it:** blowouts cut starters' minutes, so the leak flatters unders. It is in every under backtest built
    on this projection, slots 1–5 and NBA_UNDER_PREREG's amendments included.
  - **Who doesn't:** the live engine builds "out tonight" from the injury report, so the live pings don't have it.

## E8: every slot re-graded without the leak (2026-10-31, about 11:40 UTC)
`nba_q15_proj.py --mode`, with the same frozen rules and thresholds. Nothing was re-chosen.
- **rot:** only rotation players (the engine's own absences filter, 17+ minutes over 3+ games) can be out tonight.
  The deep bench is always active.
- **lag:** rot, and only players who also missed the previous game. No first-night absence, which leans against
  unders.
- **lag, no vacated:** lag, with our own box-score "teammates out" features dropped too.

**The under rules** (engine port, RS 2023-24 / RS 2024-25 / TEST A):

| rule | as backtested (leaky) | rot | lag |
|---|---|---|---|
| UNDER20P | +7.7% / +6.9% / +15.0% (461) | +2.0% / −1.2% / +6.4% (1,393, lower bound −2.6%) | +1.5% / −3.2% / +6.3% |
| UNDER3050 | +16.8% / +15.0% / +19.2% (88) | +4.1% / +6.0% / +22.5% (214, lower bound +1.5%) | +2.9% / −3.4% / +12.3% |
| UNDER3050L | +24.5% / +20.2% / +15.8% (54) | +10.5% / +9.7% / +25.7% (134, lower bound +3.9%) | +6.1% / 0.0% / +13.2% |

- Without the leak the projections are lower, so a fixed ratio threshold flags more props. These numbers are the rules
  as written, not re-tuned.
- **Most of the under family's regular-season edge was the leak.**

**The model** (logistic + the leak-free projection):

| version | log loss VALIDATE (market 0.68751) | Q15_LR8: TRAIN / VALIDATE / TEST A | Q15_LR10: TRAIN / VALIDATE / TEST A |
|---|---|---|---|
| leaky (as registered) | 0.68610 | +9.7% / +12.1% / +26.7% (1,360) | +10.2% / +18.4% / +30.2% (738) |
| rot | 0.68681 | +7.3% (4,599) / +8.1% (1,497) / **+21.7% (557)** | +6.0% (2,478) / +12.1% (618) / **+29.1% (209)** |
| lag | 0.68707 | +8.4% / +5.6% / +23.2% (541) | +7.9% / +10.2% / +30.5% (199) |
| lag, no vacated | 0.68729 | +8.9% / +3.5% / +25.7% (377) | +9.0% / +8.7% / +31.8% (142) |

- **rot, TEST A in detail:**
  - Q15_LR8: 90% CI [+13.7, +29.4], lower bound +10.0%. By postseason: +14.6% (149), +21.6% (315), +33.5% (93).
  - Q15_LR10: lower bound +10.6%. By postseason: +22.2% (56), +32.5% (126), +27.7% (27).
  - VALIDATE halves: LR8 +11.3% / +5.5%; LR10 +9.6% / +14.3%.
- **Blanket unders, priced props only** (the baseline):
  - TEST A: +3.1% / +0.4% / +2.2% by postseason (overs hit 45.7% / 47.2% / 45.4% against 49.9% / 49.6% / 49.5%
    no-vig).
  - TRAIN −1.7%, VALIDATE −3.9%.
  - The playoffs lean under by about 2 points of ROI. The model adds about 20 more.
- **Verdict on the bar, leak-free:**
  - Q15_LR8 fails 5 (VALIDATE +8.1% < 10%).
  - Q15_LR10 fails 2 (209 < 300 bets).
  - The under rules fail on VALIDATE and on bets.
  - **Nothing passes.**
- **What survives:**
  - A real edge from the engine's projection: half of E7's log-loss gain is left, still twice E2's.
  - Selected unders make +6% to +12% in the regular season.
  - In three postseasons they make +22% to +32% in every leak-free version, with a lower bound near +10% after the
    5-way Bonferroni.
  - The leak fix was prompted by the TEST A result, and 3 versions were graded on it. They all agree.

## E9: FanDuel and DraftKings only, as the live system sees the market (2026-10-31, about 11:55 UTC; TRAIN / VALIDATE)
- **The setup** (rot projection, unders, 12+ projected minutes):
  - The line: FanDuel's main line, else DraftKings'.
  - The market: their no-vig at that line.
  - n_books, line gap and hold from those two only.
  - Bet at the better of the two.

| τ | TRAIN | VALIDATE | VALIDATE halves | VALIDATE bets a day |
|---|---|---|---|---|
| 8% | 4,509, +8.5% [+5.0, +11.8] | 1,254, +7.4% [+1.1, +13.2] | +6.5%, +8.5% | 7.7 |
| 10% | 2,382, +10.1% [+5.7, +14.8] | 491, **+17.0%** [+7.6, +25.9], lower bound +4.2% | +22.2%, +11.2% | 3.0 |
| 12% | 1,239, +10.0% | 195, +23.3% | +25.5%, +21.4% | 1.2 |

- **Reading:** the edge doesn't need the other two books, so it can be run live. In the regular season it is +7% to
  +10% at τ 8–10%, with VALIDATE's +17% at τ 10% on 491 bets the high end.

## E10: a small look-ahead in our own features, fixed (2026-10-31, about 12:15 UTC)
- **The bug:** the new tests (`test_nba_q15.py`) found it. For a player with no last season, the shrinkage prior for
  his per-minute rate was the league's rate over **all** box scores, later games included.
  - It is now the league's rate over every game before the date.
  - The team normalizers (pace, allowed rates) are also all-data constants. They only rescale a feature, which
    standardization absorbs exactly, so they are left as they are.
- **The rebuild changed nothing material** (rot projection):

| | before the fix | after |
|---|---|---|
| Q15_LR8 VALIDATE | +8.1% | +8.0% |
| Q15_LR8 TEST A | +21.7% | +21.2% |
| Q15_LR10 VALIDATE | +12.1% | +12.5% |
| Q15_LR10 TEST A | +29.1% | +29.5% |
| E9 τ 10% VALIDATE | +17.0% | +17.4% |

- **Mutation check:** 12 of 12 mutants killed. They covered:
  - dropping each shift(1);
  - the league prior;
  - push grading;
  - the consensus-line price check;
  - the split boundary;
  - the 12-minute and under-side filters;
  - the engine features.
- **Reproduce:** `nba_q15_model.py --market fd_dk` reproduces E9.
