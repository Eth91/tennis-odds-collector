# PRE-REGISTRATION: UNDER20 and UNDERML, the forward test of T2's finding (2026-10-28, about 22:20 UTC, before code)

**Where it comes from** (`NBA_TESTS4_PREREG.md`):
- T2's logistic model passed on held-out 2024-25: log loss 0.68818 against the book's 0.68878, and EV ≥ 5% bets made
  +3.5% on 11,155. It held on FanDuel-only prices and without the hindsight features.
- 92% of its bets were unders. The simple rule "under when our projection < 0.8 × the line" made +5.6% (5,940) and +4.5%
  (4,508) at tip lines. That cut was chosen after seeing T2's bets.
- So neither is proven. This is their forward test.

**User's choices:** both rules, 30 minutes before tip; the simple rule pings (SHADOW), the model is silent. Nothing
bets: `nba_flags.LIVE_TIERS` stays empty.

## Shared
- **When:** each game's first pinger run at or after tip − 30 and before tip − 5 (as RETURN_UNDER and FOUL_BIG). In the
  side-by-side it is the tip − 30 tick.
- **Board:** FanDuel's current main rung for each player prop in the 8 markets.
- **Out tonight:** the official report's Out or Doubtful for the player's team, read as of the run. Out players are
  not judged.
- **Projection:**
  - V3 minutes (`nba_boost.v3_minutes`: ROLE1 v3, every out rotation player absent, the active roster less the outs)
    × `nba_boost.rates` (last season worth 150 minutes), summed for a combo;
  - the same as T2's backtest, except that the outs come from the report and not the box score;
  - no V3 means no projection.
- **One signal per (rule, game, player, market).**

## UNDER20 (pinged)
- The under when the projection < 0.80 × the line, at FanDuel's under price. There is no price cap, as tested.
- **Ping:** "🔵 UNDER {player} {market} u{line} {price} FD · proj {proj} ({ratio} of the line), {minutes} min · shadow".

## UNDERML (silent)
- **The model:** T2's logistic model without the hindsight outs features, refit on 2023-24 exactly as in
  `nba_tests4_checks.py`'s "without the hindsight outs features" run. Exported as `nba_under_model.py` (the VM has no
  scikit-learn); its predictions must equal scikit-learn's.
- **Features:** logit(FanDuel's no-vig over at the main), the line, projection ÷ line, V3 minutes − his last-10
  minutes, his season mpg, his last-5 ÷ season mean of the market's stats, rest days (capped at 4), back-to-back, the
  team's game index, and the market (one-hot). Missing values take the 2023-24 medians.
- **The bet:** either side where p × FanDuel's price − 1 ≥ 0.05.

## Judged
- Like every rule, by the side-by-side's CLV and ROI, at ≥ 200 signals over ≥ 10 dates.
- Registered at the deploy time in `nba_sxs_rules.py`.

# AMENDMENT 1: which UNDER20 flags ping (2026-10-28, about 22:20 UTC, before deploy)
- **Dry run on tonight's FanDuel board:** 930 props, 54 UNDER20 flags. Many were threes unders at −180 to −250.
- **Backtest split (post-hoc, information):** UNDER20 under −150 or better made +7.3% / +6.9% (4,256 / 3,048); worse
  than −150, +1.1% / −0.6%. Threes made +0.5% / +0.2%. Every other market was positive in both seasons.
- **User:** ping only "−150 or better, no threes". **Everything is still recorded:**
  - UNDER20 stays as registered (all flags);
  - a second side-by-side rule, **UNDER20P**, is the pinged subset (under −150 or better, not threes), registered
    with the others.
  - The forward record shows whether the filter holds.

# AMENDMENT 2: the cut swept, information (2026-10-28, about 22:35 UTC; post-hoc)
**User:** "what if we run 25% or 30% or 35% or 40%, does the ROI increase?" (`nba_under_sweep.py`, 2023-24 tip lines;
the same rows as T2's checks.)

| unders −150 or better, no threes | 2023-24 | 2024-25 |
|---|---|---|
| 20%+ below (live) | 3,916, +7.7% | 2,819, +6.9% |
| 25%+ below | 2,127, +8.7% | 1,469, +9.8% |
| **30%+ below** | **1,181, +15.2%** (90%: +11.0%, +19.6%) | **765, +14.2%** (+9.0%, +19.3%) |
| 35%+ below | 676, +14.8% | 395, +7.3% |
| 40%+ below | 397, +15.8% | 191, +7.8% |

- All flags (threes and heavy prices included) give +9.5% / +8.1% at 30%+.
- The bands: 20–25% below, +6.4% / +3.8%; 25–30%, +0.6% / +5.1%; 30–40%, +14.9% / +16.3%.
- **Reading:**
  - ROI rises to about 30% below, then flattens while the count falls.
  - Total profit is larger at 20%+ (2024-25: about 195 units against about 109).
  - The cut was chosen after looking, from five tried, so the forward record decides. No live change without the user.

# AMENDMENT 3: a star on 30%+ (2026-10-28, about 22:40 UTC, before code)
- **User:** "mark 30%+ as strong." UNDER20's pinged flags whose projection is under 70% of the line ping as "🔵⭐ UNDER";
  the rest stay "🔵 UNDER". No flag is added or removed.
- **The side-by-side tracks UNDER30P:** UNDER20P's flags with projection < 0.70 × the line. It is registered at the
  deploy time, so the 30% cut's own forward record starts clean.

# AMENDMENT 4: ping only 30–50% below (2026-10-28, about 22:30 UTC, before code)
**User:** "only ping when it's 30%+ below ... is there an optimal range, say 30–50% below? test all ranges."
`nba_under_grid.py` (post-hoc; −150 or better, not threes; 35 ranges tried).

| % below the line | 2023-24 | 2024-25 |
|---|---|---|
| 20–25 / 25–30 | +6.4% / +0.6% | +3.8% / +5.1% |
| 30–35 / 35–40 / 40–45 / 45–50 | +15.7 / +13.3 / +15.9 / +36.7% | +21.5 / +6.7 / +2.9 / +20.5% |
| 50–60 / 60+ | +6.4% (n 101) / n < 40 | +2.2% (n 50) / n < 30 |
| **30–50** | **1,022, +16.8%** | **710, +15.0%** (90%: +9.3%, +20.9%) |
| 30–max | 1,181, +15.2% | 765, +14.2% |
| 25–50 | 1,968, +9.0% | 1,414, +10.1% |

- **Reading:** the 30% floor is what matters. The cap barely does; past 50% below is weaker and rare, likely where our
  projection is off.
- **User:** ping 30–50% below (−150 or better, not threes). Every other flag is recorded silently.
- The pings are "🔵 UNDER" (amendment 3's star is dropped, since every ping is now 30%+).
- **UNDER3050** (the pinged subset) is added to the side-by-side. UNDER20, UNDER20P and UNDER30P stay, so the forward
  record compares them.

# AMENDMENT 5: the same ranges for overs (2026-10-28, about 22:45 UTC; information)
**User:** "test the same ranges for the overs." (`nba_over_grid.py`: the over when our projection is X% above the line,
best FanDuel/DraftKings over, 2023-24 and 2024-25 tip lines; 46 ranges.)

| overs −150 or better, not threes | 2023-24 | 2024-25 |
|---|---|---|
| 0–10% above | 25,259, −8.4% | 23,794, −5.7% |
| 10–20% | −3.4% | −2.4% |
| 20–25% / 25–30% / 30–35% | −1.8 / −2.3 / +0.9% | +0.6 / −1.7 / −4.9% |
| 35–40% / 40–50% / 50–75% | −7.6 / −0.5 / +0.4% | −1.5 / −4.2 / −2.4% |
| best range by the worse season (20–35%) | 7,442, −1.5% | 6,976, −1.2% |

- With all overs (threes and heavy prices included), every range runs about −2% to −3%.
- **No over range is positive in both seasons.**
- **Reading:** the book's no-vig over runs above the actual over rate (49.2% against 47.3–48.5%), so overs carry the
  public's shading on top of the vig. A projection far above the line is more often our miss. A projection far below
  catches lines the book is slow to lower.
- No over rule is added.
