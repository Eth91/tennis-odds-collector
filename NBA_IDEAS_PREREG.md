# PRE-REGISTRATION: six basketball-logic ideas

Written 2026-10-27 (about 09:10 UTC), before any of them was computed. Research only: nothing is bet. User: "yes, run
1-6 and backtest them."

## Common setup (ideas 1–4 and 6)
- **Props:** the archive's tip lines in 2023-24 and 2024-25, for points, rebounds, assists and PRA. The main line
  is the FanDuel/DraftKings rung nearest even money; each side is priced at the best FanDuel/DraftKings price.
- **Features:** season to date, strictly before the game's date, from the full game logs (and the tracking
  history for idea 3). A player needs ≥ 5 games and a team ≥ 10 where noted. No hindsight, except where
  flagged.
- **Pass:** ROI > 0 in **both** seasons **and** above the idea's baseline in both seasons.
- **Forward:** each idea that passes enters the side-by-side, registered then.

## The ideas
1. **Back-to-backs (rest and fatigue).** The team played the previous calendar day.
   - **1a:** unders for players averaging ≥ 32 minutes. Baseline: their unders on other nights.
   - **1b:** overs for players averaging 15–24 minutes. Baseline: their overs on other nights.
2. **Foul-prone bigs.** F or C, ≥ 4.5 personal fouls per 36 minutes, against an opponent whose FTA drawn per game
   is above the league's 67th percentile (season to date, ≥ 10 games). Unders in points and rebounds.
   Baseline: all F/C unders in those markets.
3. **Rebounding opportunities.** The opponent's missed field goals per game (its FGA − FGM, season to date) above
   the league median.
   - **3a:** rebound chances ≥ 2 × the rebounds line **and** the opponent misses above the median: rebounds over.
     Baseline: rebound chances ≥ 2 × the line alone.
   - **3b:** the opponent's misses in the top tercile alone: rebounds over. Baseline: all rebound overs.
4. **A teammate returns.**
   - **The trigger:** a rotation player X (≥ 20 minutes this season, ≥ 3 games) plays tonight after missing
     ≥ 2 straight team games.
   - **The bet:** for each teammate B whose minutes in those missed games averaged ≥ 4 more than in games with
     X, unders in points, rebounds, assists and PRA in X's first game back.
   - **Baseline:** all unders in those markets.
   - **Hindsight:** X's return is read from the box score. Returns are usually announced before tip, but a late
     return would be hindsight.
5. **Minutes restriction. Forward only;** the official report never carries it, and there is no history.
   - **The trigger:** an X or Bluesky news item (`nba_news.news_items`, with a player id) whose text says
     "minutes restriction", "minute restriction", "minutes limit" or "limited minutes".
   - **The bet:** at FanDuel's next observation of his game (within 15 min of detection, up to tip − 5),
     unders at FanDuel's main line in points, rebounds, assists and PRA.
   - **Registration:** side-by-side rule MIN_RESTRICT, registered at 2026-10-27T13:00:00 UTC, with no pings.
6. **Expected blowouts and totals.** No game lines are in the archive, so both use team ratings, season to date
   (each team ≥ 10 games):
   - **predicted margin** = (team net points per game − opponent net) ÷ 2 ± 2.5 home edge;
   - **predicted total** = (team points + opponent allowed + opponent points + team allowed) ÷ 2.
   - **6a:** |predicted margin| ≥ 10: unders for players averaging ≥ 30 minutes, in points and PRA. Baseline:
     their unders in other games.
   - **6b:** predicted total in the 2023-24 top quintile: overs for players averaging ≥ 28 minutes, in points.
     Baseline: their overs in other games.

---

## Results (2026-10-27, about 09:20 UTC; `nba_ideas.py`): ideas 2 and 4 pass
- **Cuts (2023-24):**
  - opponent FTA drawn, 67th percentile: 23.5 a game;
  - opponent misses: median 47.1, top tercile 47.9;
  - predicted total, top quintile: 234.5.

| idea (side) | 2023-24 n, hit, ROI | baseline | 2024-25 n, hit, ROI | baseline | |
|---|---|---|---|---|---|
| 1a b2b, 32+ min (under) | 2,678, 54.3%, +2.0% | −1.0% | 2,729, 51.1%, −4.1% | −3.1% | fail |
| 1b b2b, 15–24 min (over) | 1,597, 44.0%, −15.1% | −8.6% | 2,009, 47.4%, −8.9% | −8.7% | fail |
| **2 foul-prone bigs (under)** | **365, 56.2%, +6.4%** | −0.7% | **120, 60.0%, +13.1%** | −1.9% | **PASS** |
| 3a RC 2× + opponent misses (over) | 1,373, 50.9%, −5.7% | −3.9% | 917, 55.0%, −1.2% | +0.5% | fail |
| 3b opponent misses, top tercile (over) | 4,621, 45.7%, −11.0% | −9.6% | 5,635, 46.6%, −9.4% | −8.1% | fail |
| **4 teammate returns (under)** | **1,984, 54.1%, +1.7%** | −1.1% | **2,275, 54.1%, +1.5%** | −3.4% | **PASS** |
| 6a expected blowout, 30+ min (under) | 280, 57.9%, +8.8% | +1.2% | 445, 53.0%, −0.4% | −5.5% | fail |
| 6b high expected total, 28+ min (over) | 1,269, 46.3%, −11.0% | −9.9% | 275, 47.6%, −8.4% | −5.6% | fail |

**Reading:**
- **Idea 4 is the most consistent result of the day:** 54.1% in both seasons on about 2,000 bets each. It sits
  above the roughly 52.4% break-even even at tip lines.
- **Idea 2 is strong but small:** 120 bets in 2024-25.
- Eight variants were tested, so two passes could include a fluke. That is why forward is the judge.
- **Idea 4's hindsight:** X's return is read from the box score.

# AMENDMENT 1: forward rules for the passing ideas (written before they ran)
- **RETURN_UNDER (idea 4).** At tip − 30, for a team where a rotation player X (≥ 20 min, ≥ 3 games this
  season) missed the team's last ≥ 2 games:
  - X must not be listed Out or Doubtful on the latest report;
  - if a lineup snapshot exists for the team, X must be listed Active there;
  - that is how the backtest's "he played" is read point-in-time.
  - **The bet:** each teammate B whose minutes in X's missed games averaged ≥ 4 more than in games with X:
    unders at FanDuel's main line in points, rebounds, assists and PRA.
  - **Pings:** SHADOW, because it passed.
- **FOUL_BIG (idea 2).** At tip − 30, an F/C with ≥ 4.5 personal fouls per 36 this season (≥ 5 games),
  against an opponent whose FTA drawn per game this season is > 23.5 (≥ 10 games): unders at FanDuel's main
  line in points and rebounds.
  - **Pings:** SHADOW.
  - **Data:** nba_matchup must store personal fouls; it adds the column, and the season is refetched.
  - It cannot fire before opponents have 10 games (about mid-November).
- **MIN_RESTRICT (idea 5)** as registered above, no pings.
- **Registration:** all three at **2026-10-27T13:00:00 UTC** (side-by-side amendment 6).
