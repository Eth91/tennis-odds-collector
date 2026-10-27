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

---

## Test A: result (2026-10-27, about 08:10 UTC): FAIL on minutes
- **Data:** 15,894 teammate-games in spots in 2025-26 and 15,192 in 2024-25 (`nba_role.py --test-a`).

| MAE (2025-26 / 2024-25) | model | season average | last 5 |
|---|---|---|---|
| minutes | 5.312 / 5.345 | 5.459 / 5.599 | **5.171 / 5.330** |
| FGA | **2.860 / 2.881** | 2.958 / 2.997 | 2.938 / 3.008 |
| FTA | 1.695 / 1.643 | **1.669 / 1.598** | 1.715 / 1.647 |
| points | **4.711 / 4.789** | 4.767 / 4.844 | 4.880 / 4.975 |
| rebounds | 1.974 / 1.998 | **1.959 / 1.997** | 2.025 / 2.063 |
| assists | **1.403 / 1.397** | 1.404 / 1.398 | 1.441 / 1.449 |
| threes | 0.927 / 0.934 | **0.911 / 0.916** | 0.950 / 0.965 |

- **Bias:** the model runs +0.70 / +0.76 minutes high.
- **The minutes change** (predicted vs actual, against base) correlates 0.378 / 0.376.
- **FGA:** the model beats both baselines in both seasons.
- **Minutes:** it beats the season average but not the last-5 average, so it fails the registered bar.
- **Negative binomial r** (2025-26): points 6.99, rebounds 11.1, assists 12.0, threes 9.7.

# AMENDMENT 1: the simplified minutes model (written before it was run), and a clean season to check it
**Why.** The model's base minutes use only games the absent player played. In absence games 2–3, the last 5
games already include games without him, which is why "last 5" wins on minutes.

**Change (minutes only; everything else unchanged):**
- **Base:** B's mean minutes over his last 5 games this season.
- **Bump:** each absent X's minutes, distributed by the same weights (base × 3 for the same position group), times
  the share of B's last-5 games in which X played. That is the part of X's absence not already in his last 5.
- No separate empirical bump. Capped at 40 and rescaled so the roster totals 240, as before.

**Check (decided now):** Test A again, with the same measures, on **2023-24** (last season 2022-23). That season
was not used in Test A.
- **Pass:** model MAE < both baselines for minutes and FGA on 2023-24.
- 2025-26 and 2024-25 are re-reported for information only; they have been seen.
- **If it passes:** the forward rule uses the simplified model.
- **If it fails:** ROLE_OPEN is still registered as a forward test, since the user asked for it, with the model
  that did better on the 2023-24 check. The report says plainly that the minutes model does not beat last-5.

**Amendment 1 check: run (2026-10-27, about 08:20 UTC). PASS, so the forward rule uses the simplified model
("v2").**

| 2023-24 (clean) MAE | v2 | season average | last 5 | (v1, for comparison) |
|---|---|---|---|---|
| minutes | **5.282** | 5.738 | 5.375 | 5.447 |
| FGA | **2.858** | 2.974 | 2.963 | 2.898 |
| points | **4.700** | 4.740 | 4.854 | 4.738 |
| rebounds | 1.969 | **1.966** | 2.029 | 1.987 |
| assists | **1.393** | 1.398 | 1.449 | 1.403 |
| threes | 0.893 | **0.883** | 0.919 | 0.898 |

- **Seen seasons, information only.** v2 also beats both baselines on minutes and FGA in 2025-26 (5.120 / 2.814)
  and 2024-25 (5.220 / 2.854).
- **Bias:** +0.70 to +0.76 minutes. The roster excludes players returning outside the last 3 games, so the
  others share 240 minutes.
- **The gains are modest:** about 2% better than last-5 on minutes and 4% on FGA.
- **Negative binomial r for pricing** (v2 on 2025-26): points 7.211, rebounds 11.747, assists 13.092,
  threes 10.157.

## Test B: result (information, 2026-10-27, about 08:30 UTC)
Absence games 2–3 at the archive's tip lines (FanDuel/DraftKings main), v2 model, negative-binomial pricing:

| | 2023-24 | 2024-25 |
|---|---|---|
| sides with model EV ≥ 5% | 10,322 (31% of sides), ROI −3.5% | 10,972 (34%), ROI −3.8% |
| sides with model EV < 0 | ROI −6.2% | ROI −5.5% |

The model orders sides a little: what it likes loses less. But it is badly overconfident; a third of all sides
clear 5% EV. Unchanged, the forward rule would fire on about a third of openers in a spot, too many to bet by
hand.

# AMENDMENT 2: calibrate toward the book (written before the fit was run)
- **The calibrated probability** of a side:
  P′ = sigmoid( logit(book no-vig) + β × (logit(P_model) − logit(book no-vig)) ).
  β is the share of the model's disagreement with the book that is real.
- **The fit:** β by maximum likelihood on **2023-24** over sides at the tip lines in absence games 2–3. One row
  per prop: its over side, pushes dropped.
- **The check on 2024-25:** report the log loss of P′ against the book, and the ROI of P′ × price − 1 ≥ 0.05.
  Information, since tip lines are not openers.
- **The forward rule (ROLE_OPEN) uses P′ with this β**, and the rest is unchanged: an opener, a spot, EV′ ≥ 0.05.
  At openers β is likely conservative.

**Amendment 2: run (2026-10-27, about 08:40 UTC).**
- **The fit (2023-24, 16,323 props):** β = **0.09**. Log loss: book 0.68325, calibrated 0.68301, raw model
  0.70798.
- **The check (2024-25, 18,109 props):** log loss book 0.68541, calibrated **0.68523**, raw model 0.70780.
  - The calibrated model beats the book out of sample, by a little.
  - EV′ ≥ 5% fires on 265 sides (0.7%): ROI +3.5%, overs −2.9% (n 125), unders +9.3% (n 140).
  - That is far too few to call an edge.
- **Reading:** at tip lines, about 9% of the model's disagreement with the book is real. ROLE_OPEN uses
  β = 0.09 and fires rarely.

# AMENDMENT 3: add WOWY (written 2026-10-27, about 08:20 UTC, before it was built or run)
**User:** "once we get more seasonal data we can use WOWY and see how a player performs without that player but
with the others who will play. So you can add WOWY to ROLE1."

**Change ("v3" = v2 + WOWY):**
- **Matching games:** for each active player B, this season's team games before the date in which:
  - every absent rotation player tonight was out (did not play);
  - every active rotation player tonight (≥ 17 min over ≥ 3 games this season) played;
  - B played.

  That is "without that player but with the others who will play".
- **From those n games:** B's mean minutes, and his per-minute FGA, FTA, 3PA, REB and AST.
- **Blend:** weight w = n / (n + 3).
  - minutes = (1 − w) × v2 minutes + w × WOWY minutes;
  - each rate = (1 − w) × v2 rate + w × WOWY rate.
- The rest is unchanged: cap 40, roster 240, team volume conserved, efficiency, pricing, β.
- With no matching games (n = 0), v3 equals v2.

**Check (decided now):**
- **Test A, v3 against v2, on 2022-23**, a season no version has been tested on. There are no 2021-22 priors,
  so both use the league-default rates.
- **Pass:** v3's MAE is ≤ v2's for minutes and FGA on 2022-23, and on the 2022-23 rows where WOWY applies
  (n ≥ 1).
- The seen seasons are re-reported for information.

**If it passes:** ROLE_OPEN uses v3, re-fingerprinted before its 13:00 UTC registration, so the forward record is
unchanged. **If it fails:** ROLE_OPEN keeps v2, and v3 stays a reported option until more of this season is in.
