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
