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

## Result (2026-10-31, about 08:30 UTC): FAIL, all 9 rules
`python3 nba_roles_l3.py`, nothing changed after the first run. 83–84% of 20+ minute player-games have a points tip
line. ROI is per unit; "fair" is the book's no-vig chance for the side bet; [90% interval].

| rule | 2023-24: bets, hit vs fair, ROI | 2024-25: bets, hit vs fair, ROI |
|---|---|---|
| **A1** minutes +4 → over | 18,470, 46.3% vs 49.2%, **−10.9%** [−13.0, −8.8] | 15,520, 48.1% vs 49.2%, **−7.3%** [−9.6, −5.1] |
| A2 minutes −4 → under | 6,618, 50.8% vs 50.8%, −5.1% | 5,377, 49.6% vs 50.9%, −7.5% |
| A3 up: FGA +3 → points over | 1,820, 45.9% vs 49.3%, −11.4% | 1,776, 48.4% vs 49.4%, −6.9% |
| A3 down: FGA −3 → points under | 824, 51.5% vs 50.4%, −2.4% | 670, 49.6% vs 50.6%, −6.6% |
| A4 up: 3PA +2 → threes over | 1,221, 43.2% vs 49.6%, −17.6% | 1,056, 45.5% vs 48.7%, −10.5% |
| A4 down: 3PA −2 → threes under | 502, 52.2% vs 50.1%, −1.6% | 478, 52.9% vs 50.9%, −0.6% |
| **B1** new starter, game 1 → over | 4,979, 46.9% vs 49.3%, **−10.2%** [−14.7, −5.8] | 4,829, 52.5% vs 49.3%, **+1.2%** [−3.1, +5.5] |
| B2 B1, line not raised | 1,185, 53.1% vs 50.4%, −0.1% | 1,421, 51.1% vs 50.1%, −2.5% |
| B1 in game 2 | 1,761, 49.6% vs 49.2%, −4.5% | 1,725, 50.1% vs 49.2%, −3.8% |

**Also reported:**
- B1 in game 3: −9.4% / −5.2%.
- Every teammate in game 1: −10.2% / −4.0%.
- **The bump:** the new starter's line rises 1.45 / 1.27 on average (points: +2.07 / +1.83) from his last game to game 1,
  then only 0.27 / 0.18 more (points: +0.32 / +0.28) from game 1 to game 2.

**Reading:**
- **A:** players whose minutes or shots jumped over their last 3 hit their overs *less* often than the book's fair
  price (46–48% vs 49%). The books move with the last 3 games, and a little too far. Role changes don't go
  unpriced at tip.
- **B:** the books raise a new starter's line *before* game 1 (about +2 points), not between game 1 and game 2. Game 1
  split the seasons (−10.2%, +1.2%). Lines that hadn't moved (B2) hit about 1–3 points above fair, but the margin
  ate it.
- **The user's example, Terrence Shannon Jr. (this season, `nba_lines.sqlite`):**
  - With Edwards: FanDuel 7.5–8.5 points.
  - Edwards' first game out (10/28): FanDuel opened at 12.5, only 3 hours before tip, and it was 13.5 at tip. He
    scored 19.
  - Second game (10/30): opened at 14.5. He scored 11.
  - The book raised him about 5 points before game 1, and only 1 more for game 2.

**Not tests (picked after seeing the results; one of 6 mirrors):**
- Betting against the A rules mostly loses to the margin too.
- One exception: **threes under after 3PA rose 2+** was +7.7% [+3.2, +12.6] and +2.0% [−3.0, +7.2], hitting 56.8% vs
  50.4% and 54.6% vs 51.3%.
- That is a lead for a fresh pre-registration and a forward test on games not yet seen. It is not an edge.
- **Not tested here:** the opener window, the hours between a book posting a line and the injury news. The
  archive has no openers. The live BOOST / ROLE_OPEN shadow pings are the test of that.
