# NBA WOWY per-36 × minutes: pre-registration

Written and committed on 2026-11-06 (about 21:10 UTC), before any projection below was computed and while the
2023-24 lineups were still being built. Research only: nothing changes live. `nba_flags.LIVE_TIERS` stays empty.

## The theory (the user's words)
"We take WOWY per 36 splits - convert to the per36 to either our projected number of minutes based on our highly
complex formula we create or their average minutes without that player in the game or the averag of their last 3-5
games"

A projection is a per-36 rate × projected minutes / 36. The rate is the WOWY tab's: the player's per-36 with the
teammate off the court.

## Already seen (so not evidence for anything below)
- **The 2025-26 carry-over fit** (`NBA_WOWY_SELECT_PREREG.md`): over his overall per-36, the game the teammate misses
  carries about 1/5 of the off-court gap for points (+0.17), rebounds +0.15 and assists +0.32.
- **The 2024-25 selection test at tip lines** (same file): all 7 criteria FAIL.
  - "Star out" and "next man up" were real (+1.1 to 1.2 points) but already priced.
  - Those 2024-25 lines have been used before. None of the projections below has been computed on them.
- **The minutes models** (`NBA_MINUTES_PREREG.md`):
  - V3, the live role model, misses a new starter's minutes by 6.2-6.3.
  - Last-5 misses them by 7.7-8.3 and runs 6-7 minutes low.
- **2023-24:** the lineups have not been built or looked at.

## Data
- **Lineups:** the 2023-24, 2024-25 and 2025-26 regular seasons, rebuilt from cdn.nba.com play-by-play by
  `nba_onoff.parse`.
  - 2023-24 and 2024-25 starters and names come from the cdn.nba.com liveData box scores.
  - 2025-26 comes from the 2026-11-03 VM backup of `nba_matchup`.
- **The engine's minutes:** `nba_role.project(..., mode="v3")`, the role model ROLE_OPEN runs.
  - It reads `logs_full` from `nba_gamelogs.sqlite` (priors from the season before).
  - The code is used as it is, read-only.
- **Lines:** `basketball_nba_odds_hist.sqlite`, snap_kind `tip` (about 30 minutes before tip), 2023-24 and 2024-25
  regular seasons.
  - The main line is the one with both sides posted and the closest two prices.
  - FanDuel's main line is used first, then DraftKings'.
  - Players are matched by name within the game, as in the selection test.

## Events (point in time: only games before g)
These are the same as the selection test:
- **Teammate Y** is a regular (10+ games and 20+ minutes a game for this team before g).
  - He doesn't play in g.
  - He played in at least one of the team's 3 games before g. These are absence games 1-3.
- **Player X** has 300+ prior minutes for the team, with 60+ of them with Y on the court and 60+ with Y off it.
- **X played in g.** A DNP is void.
- **Two or more regulars out:** Y is the one with the most minutes a game before g. That makes one projection per
  player, game and market.
- Who is out comes from who played, as in the engine's own backtests. That stands in for the injury report and is
  the same for every projection.

## The projections
**Rates (per 36, X's prior minutes for this team this season):**

| | Rate | Role |
|---|---|---|
| W | per-36 in lineups with Y off the court (the WOWY tab) | the theory |
| O | overall per-36 | control: the same minutes with no WOWY |
| S | O + k·(W − O), with k = 0.17 for points, 0.15 for rebounds and 0.32 for assists | control: WOWY shrunk to what carried in 2025-26 |

**Minutes:**

| | Minutes | Needs |
|---|---|---|
| E | the engine's role model, V3 | X on the engine's active roster: played in one of the team's last 3 games, and plays tonight |
| WO | his average minutes in this season's earlier games for this team that Y missed | 2+ such games |
| L3 | average of his last 3 games for this team | 3 games |
| L5 | average of his last 5 games for this team | 5 games |

For the engine, active is the last-3 roster who play tonight. Absent is the last-3 rotation players who don't. Those
are the engine's own `tip_props` conventions.

There are 3 rates × 4 minutes = 12 projections, in points, rebounds and assists. Each is computed only where its
minutes source exists.

## Measures
**A, accuracy (all three seasons).** The events are those where all four minutes sources exist. In 2023-24 and
2024-25 the event must also have a tip line in that market.
- Per projection and market: mean absolute error against what he did, and the mean error.
- **The yardstick:** the tip line's own error, 2023-24 and 2024-25.
- **Minutes:** each minutes source's error against his minutes.
- **Does WOWY help:** MAE(W) − MAE(O) at the same minutes, with a 95% interval from resampling whole games.
  - "WOWY helps" for a minutes source and market means W's MAE is below O's in all three seasons and the pooled
    interval is below 0.
  - The same test is run for S against O.

**B, the lines.** 2023-24 is discovery; 2024-25 is confirmation.
- **The bet:** over when projection − line ≥ T, under when line − projection ≥ T.
  - Points: T = 1, 2 or 3.
  - Rebounds and assists: T = 0.5, 1 or 1.5.
- **Staking:** a flat unit at the posted tip price. A push is refunded and a DNP is void.
- **Combos:** 3 rates × 4 minutes × 3 markets × 3 thresholds × 2 sides = 216.
- **Discovery (2023-24):** of the combos with 100+ bets and ROI above 0, the top 3 by ROI carry forward. If none
  qualifies, nothing carries and every combo fails.
- **Confirmation (2024-25), the carried combos only:**
  - **PASS:** the ROI's 95% interval (resampling whole games) is above 0.
  - **PROMISING:** ROI above +3%, but the interval includes 0.
  - **FAIL:** anything else.
- **Baseline:** every over and every under in the event population at tip.
- **Every W combo** is also reported for both seasons, so the theory is shown in full. Those rows carry no verdict.

With 216 combos, the best of the discovery season will look good by chance. That is why only the confirmation
season judges. Even a PASS only earns a forward shadow on 2026-27 with nothing bet, under its own pre-registration.

## Not changed after this point
The events, rates, k values, minutes sources, thresholds, line rule and pass rules above stay as written. Fixes to
bugs are allowed: name matching, parsing, or a wrong join. Each one is listed in the result with its effect.

## Result (2026-11-06; `audit/wowy_per36/`)
The pre-registration is commit e482219708, made at 21:01 UTC. Its text says about 21:10.

**Data:**
- 2023-24 built 1,228 of 1,230 games. The rebuilt minutes and points match the box score in 100% of player-games.
- **Lines:** names matched at 98.4% in 2023-24 and 97.3% in 2024-25. That gave 41,553 and 40,575 tip main lines.
- **Events:** 7,558, 8,586 and 9,038 player-games across the three seasons.
  - The engine's minutes cover 98% of them.
  - The without-him average covers 78-83%: it needs 2+ earlier games he missed.

**Reading and fixes:**
- "Y is the one with the most minutes" was read as: among the regulars out for whom X has 60+ minutes on and 60+ off.
- No bug fixes were made after the pre-registration.

### A, accuracy
**Points.** Each cell is the miss against what he scored (MAE). The events have all four minutes sources and a tip
line.

| | 2023-24 (4,266) | 2024-25 (5,133) | 2025-26 (7,342, no lines) |
|---|---|---|---|
| Tip line | **5.09** | **5.08** | |
| Engine's own projection | 5.38 | 5.27 | 4.91 |
| WOWY × engine minutes | 5.53 | 5.37 | 4.96 |
| WOWY × without-him minutes | 5.49 | 5.45 | 5.09 |
| WOWY × last 3 | 5.48 | 5.38 | 4.96 |
| WOWY × last 5 | 5.42 | 5.36 | 4.94 |
| Plain per-36 × engine minutes | 5.34 | 5.24 | 4.86 |
| Plain per-36 × last 5 | 5.35 | 5.32 | 4.91 |

**Rebounds and assists** show the same order. The line has the smallest miss each time.

| Market | Season | Line's miss | Best projection's miss |
|---|---|---|---|
| Rebounds | 2023-24 | 2.05 | 2.08 |
| Rebounds | 2024-25 | 2.07 | 2.12 |
| Assists | 2023-24 | 1.84 | 1.88 |
| Assists | 2024-25 | 1.75 | 1.78 |

**Minutes.** Each cell is the miss against the minutes he played (MAE), with the bias in brackets.

| | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|
| Engine (V3) | **5.04** (+1.2) | **5.16** (+1.3) | 5.00 (+1.3) |
| Without-him average | 5.67 (−0.4) | 5.64 (−0.2) | 5.43 (+0.1) |
| Last 3 | 5.26 (−0.9) | 5.35 (−0.8) | 5.05 (−0.8) |
| Last 5 | 5.18 (−1.0) | 5.28 (−0.9) | **4.98** (−0.9) |

**Does WOWY help (W − O at the same minutes, pooled):**
- **Raw WOWY:** no, for every minutes source and market. It makes the projection worse, and every interval is above
  0.
  - Points: +0.04 to +0.13 worse.
  - Rebounds: +0.02 to +0.03 worse.
  - Assists: +0.00 to +0.02 worse.
- **Shrunk WOWY (S):** it passes the rule for points and assists with the without-him, last-3 and last-5 minutes, but
  the gain is under 0.01 a game.

### B, the lines
**Discovery (2023-24).** 85 combos qualified. The top 3 are all rebounds unders with the engine's minutes, and none
uses the WOWY rate.

| Carried combo | 2023-24 | 2024-25 (95%) | Verdict |
|---|---|---|---|
| plain per-36 × engine, rebounds under, 1.5+ below | 136, +18.3% | 96, +5.8% (−12.3%, +24.2%) | PROMISING |
| shrunk × engine, rebounds under, 1.5+ below | 130, +18.3% | 96, +9.3% (−9.8%, +27.3%) | PROMISING |
| plain per-36 × engine, rebounds under, 1+ below | 318, +16.7% | 254, +6.0% (−4.3%, +17.1%) | PROMISING |

The three overlap: they are mostly the same bets.

**The theory's own bets (all 72 WOWY-rate combos):**
- **Overs:** 35 of 36 lost in 2023-24 and 30 of 36 lost in 2024-25. The 6 that won made +2.3% or less.
- **Unders with the engine's minutes:** positive in both seasons.
  - Points 2+ below: +5.7% and +8.5%.
  - Points 3+ below: +10.9% and +6.2%.
  - Rebounds 1.5+ below: +13.7% and +9.2%.
  - The plain per-36 with the same minutes does as well or better, so these come from the minutes, not the WOWY
    rate.
- **Baseline (every bet in these games):** any over made −5.3% to −10.4%; any under made −5.6% to +0.4%.

**Read:**
- **WOWY per-36 doesn't improve a projection.** The raw split makes every version worse than his plain per-36.
  Shrunk to the part that carries over, the gain is a rounding error.
- **The tip line has the smallest miss of anything here.**
- **Engine minutes vs last 5:** the engine is the best minutes source in 2023-24 and 2024-25 and ties last 5 in
  2025-26. It runs about 1.3 minutes high.
- **The without-him minutes average is the worst source.**
- **The only thing that survives:** rebounds unders where the engine-minutes projection sits well below the line.
  - That is PROMISING, not PASS. It's about 100-250 bets a season, and the 2024-25 interval includes 0.
  - The WOWY rate isn't part of it.
- **Hindsight:** the backtest takes who is out from who actually played, as the engine's own backtests do. At tip
  that comes from the injury report, so late scratches make the backtest a little optimistic.
- **Next step:** a forward shadow, with nothing bet, under its own pre-registration. It needs the user's OK.

## Amendment 1: percentage thresholds (written 2026-11-06, before it was run)
The user's follow-up: "what if we put selection criteria where their adjusted minutes projection has to be x% over or
under the line depending on if youre playing an over or under"

**The bet:**
- Over when the projection is at least (1 + x) × the line.
- Under when the projection is at most (1 − x) × the line.
- x is 10%, 15%, 20%, 25% or 30%.
- Staking, pushes, DNPs, the line rule and the events are unchanged.

**Projections:** W (the theory) and O (control), each × E, WO, L3 and L5.
- S is dropped: it sat within 0.01 of O on every measure above.

**Combos:** 2 rates × 4 minutes × 3 markets × 5 thresholds × 2 sides = 240.
- Discovery (2023-24), confirmation (2024-25), PASS / PROMISING / FAIL and the baseline are as in B.
- Every W combo is reported for both seasons, with no verdict.

**Already seen:** the absolute-threshold results above, on both seasons. A percentage gap is close to an absolute one
at a given line, so this test isn't blind. The best-looking absolute rules were rebounds and points unders with
engine minutes.

### Amendment 1 result (2026-11-06; `audit/wowy_per36/nba_wowy_per36_pct.py`)
**Discovery (2023-24).** 90 combos qualified; the top 3 carried.

| Carried combo | 2023-24 | 2024-25 (95%) | Verdict |
|---|---|---|---|
| WOWY × engine, assists under, 30%+ below | 129, +18.3% | 148, −0.8% (−14.0%, +12.8%) | FAIL |
| plain per-36 × engine, assists under, 30%+ below | 106, +11.9% | 95, +17.7% (+0.5%, +34.8%) | PASS |
| WOWY × engine, points under, 30%+ below | 104, +11.8% | 135, +1.9% (−12.3%, +17.4%) | FAIL |

**WOWY-rate overs:** all 60 lost in 2023-24, and 54 of 60 in 2024-25. The 6 winners made at most +2.9%.

**Unders with the engine's minutes:** points and rebounds are positive in both seasons at every threshold from 10%
to 30%, with the WOWY rate and with the plain rate alike.

| Rule (WOWY × engine) | 2023-24 | 2024-25 |
|---|---|---|
| Points under, 20%+ below | 298, +6.1% | 371, +6.9% |
| Rebounds under, 20%+ below | 395, +10.7% | 359, +6.9% |
| Rebounds under, 25%+ below | 239, +9.9% | 202, +9.5% |

Assists unders flip negative in 2024-25 at every threshold below 30%.

**Read:**
- **The PASS is weak.**
  - It is one combo of 240, on 95 bets, and its interval's lower end is +0.5%.
  - It uses the plain per-36, not WOWY. The WOWY version of the same rule lost 0.8%.
  - The assists unders at 10-25% lost in 2024-25.
  - So it is most likely the one lucky combo that 240 tries produce.
- **The steady pattern is the earlier one:** points and rebounds unders where the engine-minutes projection is well
  below the line.
  - It holds at every threshold and in both seasons, with or without WOWY.
  - It wasn't in the top 3 of discovery, so under the rules it carries no verdict.
- **Overs lose.** The x%-over rule loses at every threshold, every minutes source and every stat.
- **Next step:** under the rules, a PASS earns only a forward shadow, with nothing bet and its own
  pre-registration. It needs the user's OK. Same hindsight note as above: who is out comes from who played.

## Amendment 2: 40% and 50% thresholds (written 2026-11-06, before it was run)
The user: "what about for the wowy over 40-50+% above or below the line"

**The bet:** as amendment 1, with x = 40% and 50%.
- Projections: W (the theory) and O (control), each × E, WO, L3 and L5.
- Markets: points, rebounds and assists. Sides: over and under.
- That is 2 × 4 × 3 × 2 × 2 = 96 combos.

**No discovery step:** each combo is judged on both seasons together.
- **PASS:** ROI above 0 in each season, and the pooled 95% interval (resampling whole games) above 0.
- **PROMISING:** ROI above 0 in each season, but the interval includes 0.
- **FAIL:** anything else.
- With 96 combos, about 5 false PASSes are expected at the 5% level. A PASS again only earns a forward shadow.

**Already seen:** amendment 1 up to 30%. There, overs lost at every threshold. Points and rebounds unders with engine
minutes won in both seasons.

### Amendment 2 result (2026-11-06; `audit/wowy_per36/nba_wowy_per36_big.py`)
**3 PASS of 96.** About 5 were expected by chance.

| PASS | 2023-24 | 2024-25 | Pooled (95%) |
|---|---|---|---|
| WOWY × last 5, points under, 50%+ below | 47, +42.9% | 58, +9.4% | +24.4% (+6.5%, +42.5%) |
| plain × last 5, points under, 50%+ below | 32, +50.6% | 57, +17.5% | +29.4% (+13.2%, +47.5%) |
| plain × engine, assists under, 50%+ below | 6, +57.3% | 7, +54.7% | 13 bets: no weight |

**Overs:**
- No WOWY over passes at 40% or 50%.
- WOWY points overs at 40-50% made −2.8% to −9.2% pooled, except WOWY × engine at 50%, which made +0.1%.
- The rest sat between −8% and +5%.

**Read:**
- **Fewer PASSes than chance:** 3 against about 5 expected, and one rests on 13 bets.
- **The two points-under PASSes are mostly the same bets,** with and without WOWY. Both are players whose last-5
  minutes put him at half his line or less, so the minutes are doing the work.
- **They shrank from one season to the next:** about +45% in 2023-24, +9% to +18% in 2024-25.
- **No support for WOWY at 40-50%,** on either side.
