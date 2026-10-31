# NBA_Q15 report: can an NBA model make 15%+ after the vig? (2026-10-31)

**Research only. Nothing is bet, and `nba_flags.LIVE_TIERS` stays empty.** The protocol is in `NBA_Q15_PREREG.md`,
and every experiment, failures included, is in `NBA_Q15_LOG.md`.

## The verdict
- **No model reached a validated 15% after the vig.** Nothing passed the pre-registered bar once a leak was removed.
- **The strongest model is real but smaller than the goal.** It is a market-anchored logistic model plus the engine's
  minutes projection, betting only unders:
  - **Regular season:** about +7% to +12% at the better of FanDuel and DraftKings.
  - **Playoffs:** +21% to +30% over three postseasons it was never fit on.
  - Neither number has been confirmed live.
- **The under pings' backtests were mostly hindsight.** The engine's backtest projection quietly knew each game's
  final margin, and that leak made up most of the edge behind the UNDER pings. Leak-free, and on this season's live
  data, those rules are about break-even.

## What was tested
- **Data:**
  - **Prices:** every main-line player prop at FanDuel, DraftKings, BetMGM and Caesars about 30 minutes before tip,
    in 8 markets. 286,731 props from the 2023 playoffs to the 2025 playoffs.
  - **Box scores:** every regular-season and playoff game.
- **What it couldn't test:** no historical prices exist for sides, totals, quarters or live betting, and there is
  only one snapshot per prop. So nothing about timing could be tested historically.
- **The split:**

| set | games | use |
|---|---|---|
| TRAIN | 2023-24 regular season | fitting, walk-forward by month |
| VALIDATE | 2024-25 regular season | choosing a model and threshold |
| TEST A | the 2023, 2024 and 2025 postseasons | 5 frozen candidates, graded once |
| TEST B | 2026-27 forward | decides "validated"; not yet run for the model |

- **The pass bar:**
  - TEST A ROI ≥ 15% on ≥ 300 bets;
  - positive in each postseason;
  - bootstrap lower bound > 0 after a 5-way Bonferroni;
  - VALIDATE ≥ 10% with both halves positive.
- **Then TEST B:** 200+ forward bets at ≥ 10% with positive CLV.

## The market is nearly efficient
- **Log loss:** the tip − 30 price scores 0.6873 against a coin's 0.6925. Props are close to coin flips, and the
  price already holds most of what can be known.
- **Blanket bets lose about the vig:**

| | TRAIN | VALIDATE | playoffs |
|---|---|---|---|
| every over | −8.7% | −6.2% | |
| every under | −1.7% | −3.9% | about +2% |

- **The known bias:** overs are overpriced, most of all in the playoffs. There they hit 46.0% against a 49.6% fair
  price.

## The leak
- **How it worked:** the engine's backtest projection rescales the team's minutes to 240 over the players it treats
  as active tonight. "Active" came from tonight's box score.
  - In a close game, a deep-bench player gets a DNP-CD and is dropped, so everyone else's projection rises.
  - In a blowout, he plays garbage time and stays, so projections stay low.
  - The projection knew the final margin (correlation −0.32), and blowouts are exactly when unders win.
- **Who it affects:** the live engine uses the injury report, so the live pings never had the leak. But their
  backtested numbers did:

| rule | backtest, as published (2023-24 / 2024-25) | leak-free | 2026-27 live, no leak |
|---|---|---|---|
| UNDER20P | +7.7% / +6.9% | +2.0% / −1.2% | 222 bets, about +2% |
| UNDER3050 | +16.8% / +15.0% | +4.1% / +6.0% | 55 bets, about −9% |
| UNDER3050L | +24.5% / +20.2% | +10.5% / +9.7% | 44 bets, about −3% |

- **What else it changes:** the deployed engine's backtests (BOOST and the other studies on the same projection) need
  re-running. That is a separate task for the engine session.

## The strongest model: Q15_LR
- **What it is:** a logistic model that starts from the market's no-vig probability and adds 34 pre-game features:
  - his recent minutes and rates, the line against his averages;
  - rest, pace and the opponent;
  - teammates out, and book disagreement;
  - **the engine's leak-free ROLE1 v3 projection against the line**, the feature that carries the edge.
- **How it's fit:** walk-forward by month, so every prediction comes from a model fit only on earlier games.
- **The bet:** the under, when the model's EV is at least τ at the better of FanDuel and DraftKings, and the player is
  projected for 12+ minutes. The 12-minute floor keeps it bettable under the books' 2026-10-16 restriction.
- **Log loss:** 0.68681 against the market's 0.68751 on VALIDATE, and 0.68528 against 0.68698 in the playoffs.
  Brier 0.24688 against 0.24722.

**Out-of-sample results** (leak-free; prices are the better of FanDuel and DraftKings at the consensus line):

| | Q15_LR8 (EV ≥ 8%) | Q15_LR10 (EV ≥ 10%) |
|---|---|---|
| TRAIN (2023-24), walk-forward | 4,611 bets, +7.2% [+3.9, +10.7], max drawdown 36.8u | 2,477 bets, +6.3% [+1.9, +10.7], 26.4u |
| VALIDATE (2024-25), walk-forward | 1,497 bets, **+8.0%** [+2.6, +13.2]; won 54.9% vs 51.0% break-even; +119u; drawdown 28.8u | 619 bets, **+12.5%** [+4.8, +20.6]; 56.5% vs 50.3%; +77u; 16.6u |
| TEST A (3 postseasons) | 556 bets, **+21.2%** [+13.1, +28.9]; 61.5% vs 50.6%; +118u; drawdown 11.1u; Bonferroni lower bound +9.3% | 210 bets, **+29.5%** [+16.6, +42.0]; 64.3% vs 49.9%; +62u; 6.0u; lower bound +11.0% |
| by postseason (2023 / 2024 / 2025) | +13.7% (150) / +21.1% (313) / +33.5% (93) | +23.8% (57) / +32.5% (126) / +27.7% (27) |
| TEST A, FanDuel only | 426 bets, +14.2% | 158 bets, +16.4% |
| pre-registered bar | **fails:** VALIDATE +8.0% < 10% | **fails:** 210 < 300 bets |

- **Brackets** are 90% bootstrap intervals, resampling player-games.
- **The 2023 postseason** has no earlier prices, so it was predicted by the 2023-24 fit, from games after it. 2024 and
  2025 use only earlier seasons.
- **TEST A by market** (Q15_LR8):
  - points +26.6%, rebounds +15.0%, assists +23.7%, threes +20.1%;
  - P+R +29.8%, P+A +14.8%, R+A +23.2%, P+R+A +26.7%.
- **Bets a day:** about 8 (LR8) or 3 (LR10) in the 2024-25 regular season.

**The live version** uses FanDuel and DraftKings only, for the line, the market and the price. It keeps the edge on
TRAIN / VALIDATE:

| | TRAIN | VALIDATE |
|---|---|---|
| EV ≥ 8% | 4,514 bets, +8.5% | 1,249 bets, +7.4% |
| EV ≥ 10% | 2,383 bets, +9.7% | 493 bets, +17.4% [+7.8, +26.5] |

## Why it falls short of 15%
1. **The regular season is the limit.** After the vig, the best honest regular-season estimate is high single digits
   to about 12%.
   - The 17% at EV ≥ 10% in 2024-25 is one season at 3 bets a day.
   - 2023-24 was +6% to +10% at the same setting.
2. **The playoff edge is above 15%, but small and unconfirmed:**
   - only about 200 bets per postseason;
   - about 2 points of it is the general playoff lean to unders;
   - it rests on three postseasons and has never run live.
3. **Line shopping is a third of it.** On FanDuel alone the playoff ROI drops from +21% to +14%. You need both
   accounts and must take the better price every time.
4. **One assumption remains.** "Teammates out tonight" still comes from the box score, though only for rotation
   players. The injury report almost always knows those by tip, but it is an assumption until the model runs live.

## TEST B: what has been measured live
- **The model isn't live yet.** The 2026-27 games so far only grade the old under rules, and those are about
  break-even, as the leak predicted.
- **CLV is unmeasured historically.** Live, the under rules' CLV against FanDuel's close is −4% to −7%, the same as
  the control (every over: −5.6%). There is no sign of beating the close at tip − 30.

## What to do next (in order)
1. **Run Q15_LR10 as a forward shadow test** (FanDuel / DraftKings version):
   - log the picks at tip − 30 with the price posted then, and grade them against the box score and FanDuel's close;
   - at about 3 a night, 200 bets takes about 2 months;
   - it is validated only at ≥ 10% with positive CLV.
2. **The 2027 playoffs (April–June) are the real test of the playoff edge.** Pre-register Q15_LR8 for them now,
   unchanged.
3. **Fix the engine's backtest leak** and re-run the studies built on it (the task is queued separately).
4. **Openers.** The live line database has every price change since 2026-10-22. The model at the opener, hours before
   the injury news, is the one place an edge could be larger than at tip − 30, and its CLV can be measured.

## Risk framework (only if any of this is bet after TEST B)
- **Unit:** 0.5% of the bankroll, flat. Full Kelly at a true +8% edge near even money is about 8%, and quarter-Kelly
  about 2%. But the true edge could be half the estimate or nothing, so stake no more than 0.5%.
- **Exposure:**
  - one bet per player per game (his points and P+R+A unders are one bet, not two);
  - no more than 3% of the bankroll on one night.
- **Drawdowns are normal:**
  - VALIDATE's worst run was 29 units at LR8 and 17 at LR10.
  - Review, don't chase, after a 30-unit drawdown.
  - Stop if 200 forward bets come in below +3%.
- **Price discipline:** only at the better of FanDuel and DraftKings, and only at or better than the logged price. A
  worse number erases most of the edge.

## Reproduce
```
git worktree add --detach ~/nba-engine-ro 0d328161ae      # the engine as deployed; link its .projdata
python3 nba_q15.py build                                   # the dataset -> .q15cache/ (NBA_Q15_CACHE overrides)
cd ~/nba-engine-ro && python3 ~/nba-engine/nba_q15_proj.py ~/nba-engine/.q15cache/e8_proj_rot.pkl --mode rot
cd ~/nba-engine
python3 nba_q15_model.py validate --proj .q15cache/e8_proj_rot.pkl                  # TRAIN / VALIDATE
python3 nba_q15_model.py validate --proj .q15cache/e8_proj_rot.pkl --market fd_dk   # the live version (E9)
python3 nba_q15_model.py test-a --proj .q15cache/e8_proj_rot.pkl                    # the postseasons
cd ~/nba-engine-ro && python3 ~/nba-engine/nba_q15_under_post.py --proj ~/nba-engine/.q15cache/e8_proj_rot.pkl
```
`--mode box` reproduces the leaky results. The tests are `test_nba_q15.py`.
