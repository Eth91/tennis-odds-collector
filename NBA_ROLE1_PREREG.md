# PRE-REGISTRATION: ROLE1, elevated roles at the opener

Written 2026-10-27 (about 07:55 UTC), before the model was built or run on any data. It is research: nothing is
bet automatically, and `nba_flags.LIVE_TIERS` stays empty. Pings go to the user, who places bets by hand, and
carry the SHADOW label until the forward record (below) says otherwise.

## The user's thesis
"Beat the books off of finding specific players who will have an elevated role for that game due to injury news.
The entire idea is speed: as soon as the books post a line we need to be on it. The lines are softest when they're
first posted. Instead of predicting the exact points, assists, rebounds of a player, we need to better predict a
player's minutes and FGA and FTA. Usually last season's data doesn't predict this season's ... gather all of this
season's data and base our predictions off that. Usually the lines are softest on the first 1-3 games without that
specific player in the lineup."

The user's answers to clarifying questions:
- **Markets:** points, rebounds, assists, threes.
- **Last season:** a season blend. Minutes and role come from this season only; per-minute rates start from last
  season and this season's games take over.
- **Absent player:** a rotation player at about 17–18 minutes.
- **Delivery:** phone pings, bet by hand.

## The spot
- **Absent player X:** averaged ≥ 17.0 minutes in his games this season for his team (≥ 3 games), and is out
  tonight.
- **Absence game n:** the number of consecutive team games this season X has missed, counting tonight.
- **A spot:** n is 1, 2 or 3.
- **Beneficiaries:** each teammate B who played for the team this season.

## The role model (this season's games before the date only, except the rate priors)
1. **The active roster:** teammates who played for the team in any of its last 3 games and are not out tonight.
2. **Base minutes:** a recency-weighted mean (half-life 3 games) of B's minutes in this season's team games that
   X played. If B has fewer than 2 such games, all of B's games this season are used.
3. **X's minutes.** X's minutes (the same weighting) are spread across the active roster in proportion to
   base minutes × (3 if same position group as X, else 1). The groups are G, F and C. This gives each player's
   **prior bump**.
4. **Empirical bump.** When B has played games this season without X, his empirical bump is his mean minutes
   in them minus his base. The two bumps are blended with weight n_without / (n_without + 2) on the empirical one.
5. **Minutes total:** projected minutes are base + bump, capped at 40, then rescaled so the active roster
   totals 240.
6. **Per-minute rates** for FGA, FTA, 3PA, REB and AST blend this season with last season:
   - (this season's total + last season's per-minute rate × 150) ÷ (this season's minutes + 150);
   - with no last season, the league mean of his position group.
7. **Team volume is conserved.** For FGA, FTA, 3PA, REB and AST:
   - each active player's raw volume = projected minutes × his rate;
   - all of them are then scaled so the roster's total equals the team's per-game total this season (in games
     X played).
   - X's share is thereby redistributed in proportion to minutes × rate.
8. **Efficiency.**
   - Points = (FGA + 0.44 × FTA) × his points per true-shooting attempt, blended with last season (K = 60
     attempts).
   - Threes = 3PA × his 3P%, blended (K = 40 attempts).

## Test A: predicting minutes and volume (before any pricing)
- **Data:** 2025-26 (last season 2024-25) and 2024-25 (last season 2023-24), from the full game logs
  (`.projdata/nba_gamelogs.sqlite`, `logs_full`). Every teammate who played in every spot.
- **Measures:** mean absolute error and bias for minutes, FGA, FTA, points, rebounds, assists and threes.
- **Baselines:** B's season average to date, and B's last-5 average.
- **Pass:** the model's MAE is below both baselines for minutes and FGA in **both** seasons. Also reported: the
  correlation of the predicted and actual minutes change against base.
- **Hindsight:** X's absence is read from the box score, which is fair here. The bet condition below only fires
  after X is listed out, so knowing he is out is part of the setup. Teammates who did not play are not scored;
  live, a DNP is a void.

## Test B: tip lines, information only
Spots with n = 2 or 3 (X also missed the previous game, so no late-scratch hindsight), at the archive's tip line
(2023-24 and 2024-25). Reported:
- the model's EV against the line, by band;
- the over/under hit rate and ROI where EV ≥ 5%.

The archive has no openers, and tip lines are the hardest version of the market, so this test decides nothing.

## The bet rule (ROLE_OPEN) and the forward test
- **The moment:** a book's opener, its first observation of a prop with a two-sided main rung. FanDuel or
  DraftKings.
- **The conditions:** B is in a spot, and X is listed Out or Doubtful on a report published before that
  observation.
- **The price:** the model gives P(side) at the opener's line from a negative binomial with the model's mean.
  Its dispersion per market is fit by method of moments on 2025-26 (the model's predictions in Test A).
- **The signal:** if P × price − 1 ≥ 0.05 on a side, signal that side at that book's opener price. One per
  (game, player, market, side), the first.
- **Development record:** replayed on 2026-10-22..27 in the side-by-side (`NBA_SXS_PREREG.md` amendment 2).
- **Forward:** from registration, judged by the side-by-side's bars (CLV at ≥ 200 signals and ≥ 10 dates; ROI
  at 500).
- **Live:** a per-minute job (`nba_role_open.py --process`) runs the same rule on new openers and pings the
  phone, labeled SHADOW, the moment it fires.

**If Test A fails:** the model is simplified before any registration, and the report says so.
