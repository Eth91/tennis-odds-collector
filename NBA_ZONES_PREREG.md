# PRE-REGISTRATION: does a player's scoring zone against the opponent's soft zones go over?

Written 2026-10-27, before any 2023-24 or 2024-25 shot was fetched. Research only: nothing is bet.

**User:** "does where a team gives up points on the floor correlate to where a player scores from the most ... say
they score a bunch in the restricted area and the paint and they're playing a team that allows a lot of points
from the restricted area and the paint, do those players go over more? That's backtestable." And: "volume is king."

**Why a backtest is fair here.** The injury backtests failed because they knew from the box score who sat. This test
needs no hindsight. A player's zone profile and the opponent's zone defense are both built from games before the
date. Two weaknesses remain: the archive's single tip − 30 price, and that amendment 30 already used these two
seasons for a different matchup factor (pace × position allowances, rejected).

## Data
- **Shots:** every regular-season shot, 2023-24 and 2024-25, from stats.nba.com shotchartdetail. Fetched a month
  at a time with `nba_shots.fetch_shots` into a research store (`.projdata/shots_hist.sqlite`).
- **Zones from court position** (tenths of a foot, basket at 0,0):
  - Restricted Area: within 4 ft;
  - Paint: |x| ≤ 8 ft and within the free-throw line, not RA;
  - Corner 3: |x| ≥ 22 ft below the break;
  - Above-the-break 3: ≥ 23.75 ft;
  - else Mid-range.
  - A make is worth 3 in the two 3-point zones, else 2.
- **Box scores:** nba_matchup's 2023-24 and 2024-25 regular season, for each shooter's team, the opponent, and
  FGA/points.
- **Props:** the archive's points props at the tip snapshot. Main line = the FanDuel/DraftKings rung nearest
  even money; the price is the best FanDuel/DraftKings over (as in amendment 30).

## Definitions (season to date, strictly before the game's date)
- **Player inside share:** the share of his points from the Restricted Area + Paint. Needs ≥ 5 games and
  ≥ 50 FGA.
- **Opponent inside allowance:** points opponents scored on that team from RA + Paint per game, ÷ the league
  per-team-game average over the same dates. Needs ≥ 10 team games.
- **INSIDE score (primary, the user's version):** inside share × (inside allowance − 1).
- **ZONE score (secondary):** Σ over the 5 zones of the player's points share × (the opponent's allowance in
  that zone − 1).

## The test (points props, each season)
- **Terciles:** cut points from the 2023-24 INSIDE scores, applied to both seasons. For each tercile: over hit
  rate (pushes excluded) and over ROI at the price.
- **Primary decision, "goes over more":** both must hold:
  1. top-tercile over ROI > bottom-tercile over ROI in **both** seasons;
  2. the pooled Spearman correlation of INSIDE score with (actual − line) is > 0, with a date-clustered
     bootstrap 95% interval above 0.
- **The volume questions (reported, no decision):**
  - correlation of the score with FGA − his season-to-date FGA average;
  - with points − his average;
  - with line − his average.

  If the score lifts points as much as it lifts the line, the market already prices it.
- **The same, for ZONE score** (secondary).

**If the primary passes:** a ZONE_MATCHUP rule enters the side-by-side, registered with its own fingerprint and
judged forward. It takes the FanDuel main-line over in points at tip − 30 for players in the top INSIDE tercile.

**If it fails:** report, and no rule.
