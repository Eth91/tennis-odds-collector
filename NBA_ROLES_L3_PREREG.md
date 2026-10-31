# NBA_ROLES_L3: do the books lag role changes? (pre-registered 2026-10-31, about 07:45 UTC, before any data)

The user's ideas:
- **A (the Roles tab, PR #120):** a player whose last 3 games are well off his season average is in a new role, and
  the books are slow to move his lines.
- **B (the Terrance Shannon case):** when a starter is first out, the player who takes his spot in the five still has
  his old line. The book bumps it about 2 points by the second game.

Both are tested on the tip lines we have. Nothing below is changed after the first run. A rule that passes becomes a
forward test (shadow, nothing bets), never a bet.

## Data
- **Box scores:** `nba_matchup.sqlite` player_games and games (starter flags, minutes, points, rebounds, assists),
  joined to `nba_gamelogs.sqlite` logs_full on (game id, player id) for FGA, 3PA and threes made. Regular seasons
  2023-24 and 2024-25.
- **Lines:** `basketball_nba_odds_hist.sqlite`, the "tip" snapshot, FanDuel and DraftKings only.
  - Names are matched to player ids with `nba_margin_refit.norm` over logs_full's names, as in the BOOST backtest.
  - **Main rung:** the line whose over price is nearest even money at either book.
  - **Price:** the better of FanDuel's and DraftKings' price for the side bet, at that line.
  - **No-vig probability:** FanDuel's pair at that line, else DraftKings'.
- **Markets (8):** points, rebounds, assists, threes, P+R, P+A, R+A, P+R+A.
- **Look-ahead:** every input uses only games before tonight. The one exception is B's starter flag (see the limits).

## Test A: last 3 games against the season average (the Roles rule)
A player-game counts when:
- he played tonight (minutes > 0) and has a tip line;
- he has 5+ games for his current team this season before tonight;
- his last 3 of them are among his team's last 4 games ("playing lately", as live);
- the median team has played 5+ games before tonight (the live switch).

For each stat (minutes, FGA, 3PA), the move is L3 − S:
- L3 is the mean of his last 3 games.
- S is the mean of all his games for this team this season before tonight, the last 3 included.

| signal | condition | bet |
|---|---|---|
| **A1 (primary)** | minutes move ≥ +4 | over, all 8 markets |
| A2 | minutes move ≤ −4 | under, all 8 markets |
| A3 up / A3 down | FGA move ≥ +3 / ≤ −3 | points over / points under |
| A4 up / A4 down | 3PA move ≥ +2 / ≤ −2 | threes over / threes under |

## Test B: a new starter in the first game a starter is out (the Shannon case)
- **X (the missing starter):**
  - X is in his team's usual five: the 5 players on the team with the most starts in its last 10 games this season
    (ties go to more minutes; a player needs a start; the team needs 3+ games).
  - X did not play tonight but was on the team: his last game before tonight was for this team, and his next game,
    if any, is for this team too.
- **Absence game n:** how many team games in a row X has missed, tonight included.
- **B (the bet):** a teammate who started tonight (box score), is not in the usual five, and has a tip line.

| signal | condition | bet |
|---|---|---|
| **B1 (primary)** | n = 1 (any missing starter) | over, all 8 markets |
| B2 | B1, and tonight's line is no higher than his line in the same market in his last game | over |
| B1 at n = 2, n = 3 | the same rule in the 2nd and 3rd game of the absence | over (comparison only) |

**Also reported:**
- the new starter's average line change from his last game before the absence to game 1, and from game 1 to game 2;
- the same split for every teammate, starter or not, at n = 1 (BOOST's game-1 result without its filters).

## Grading and pass bars
- **Grading:** stat over the line wins at the price; under it loses one unit; equal is a push (stake back). A player
  who doesn't play is void. ROI is per unit.
- **Reported per season and signal:**
  - bets, and distinct player-games;
  - hit rate (pushes dropped) against the mean no-vig probability of the side bet;
  - ROI, with a 90% bootstrap interval that resamples player-games (one player's 8 markets on a night move together);
  - ROI by market.
- **Pass:** in both 2023-24 and 2024-25:
  - ROI > 0;
  - the hit rate is above the mean no-vig probability;
  - at least 100 bets (B2: 50).
- **Multiplicity:** 9 rules are judged (A1, A2, A3 up and down, A4 up and down, B1, B2, B1 at n = 2). One pass out of
  nine across two seasons can be luck. A pass earns a forward test, not trust.
- **What it means for the user:**
  - A1 failing: the books already move with the last 3 games. The Roles tab stays a research view, not a bet list.
  - B1 or B2 passing: there's a game-1 window worth a live, shadow-only check at the opener.

## Honest limits
- **Tip lines, not openers:** the archive can't show a stale opener. If the books are slow for a few hours and fix the
  line by tip, these tests miss it. The current season's live quotes (`nba_lines.sqlite`, with openers) are too few
  for a test and are shown only as an example.
- **Absences come from box scores.** Live, they come from the injury report.
- **B uses the box score's starter flag.** NBA.com posts lineups about 30 minutes before tip, so the tip line usually
  comes after the lineup is known. A tip snapshot taken before the lineup was posted is hindsight.
- **Pot. assists and rebound chances are left out:** there's no tracking history for those seasons.
