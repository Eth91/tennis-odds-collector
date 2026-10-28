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
