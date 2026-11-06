# NBA WOWY selection test: pre-registration

Written and committed on 2026-11-06, before any subset below was computed and before the 2024-25 data was built.
The user asked whether the WOWY tab's on-court split matters once selection criteria are added.

## Already seen (so not evidence for anything below)

The pooled 2025-26 test (scratch `wowytest/wowy_test.py`) covered 12,851 events of a rotation player in absence
games 1-3 of a regular teammate.

- **Coefficient on his "teammate off the court" per-36** (over his overall per-36):

  | Stat | Coefficient | 95% interval |
  |---|---|---|
  | Points | +0.17 | 0.08 to 0.27 |
  | Rebounds | +0.15 | |
  | Assists | +0.32 | |
  | Shot attempts | +0.37 | |

- **Placebo:** about 0. The placebo uses the same split for a teammate who played.
- **Generic bump** when a regular sits: +2.6 minutes and +0.8 points on the player's rate.
- **Sample size:** a points split under 150 off-court minutes carried nothing.
- **Points gap bins:** off − overall gaps of +3 to +6 per 36 became +1.4 per 36, and gaps of +6 to +10 became +2.1.
- No subset defined below has been looked at. 2024-25 has not been built.

## Data

- **Lineups:** the 2024-25 and 2025-26 regular seasons, rebuilt from cdn.nba.com play-by-play by `nba_onoff.parse`.
  - Starters and teams for 2024-25 come from the cdn.nba.com liveData box scores.
  - For 2025-26 they come from the 2026-11-03 VM backup of `nba_matchup`.
- **Lines:** `basketball_nba_odds_hist.sqlite`, snap_kind `tip` (about 30 minutes before tip), 2024-25 regular season.
  - The main line per book, player and market is the line with both sides posted and the closest two prices.
  - FanDuel is used first, then DraftKings.
  - Players are matched by name (accents, punctuation and suffixes removed) within the game. The match rate is
    reported.

## Events (point in time: only games before g)

- **The teammate out:** teammate Y is a regular. That means 10+ games and 20+ minutes a game for this team before
  game g. He doesn't play in g but did play in at least one of the team's 3 games before it. These are absence
  games 1-3.
- **The player:** player X has 300+ prior minutes for the team, with 60+ of them alongside Y on the court and 60+
  with Y off it.
- **Rates:**
  - "overall" is X's prior per-36 for this team this season.
  - "off" is his per-36 in prior lineups without Y, summed the way the tab sums them.
  - "gap_s" is off_s − overall_s.
  - "off-min" is his prior minutes with Y off the court.
- **Star:** Y has the highest prior usage per 36 among the team's regulars. Usage here is FGA + 0.44·FTA + TOV.
- **Same group:** X and Y share a position group (G = PG/SG, F = SF/PF, C). Each player's group is his most frequent
  box-score starting slot so far that season, so both must have started at least once.

## Criteria (each is a side and a market)

| | Rule | Bet |
|---|---|---|
| C1 trusted points split | off-min ≥ 300 and gap_pts ≥ +4 | points over |
| C2 shot volume | off-min ≥ 300 and gap_fga ≥ +3 | points over |
| C3 star out | Y is the star, off-min ≥ 200, gap_fga ≥ +2 | points over |
| C4 next man up | same group, off-min ≥ 200, gap_fga ≥ +2 | points over |
| C5 assists | off-min ≥ 300 and gap_ast ≥ +2 | assists over |
| C6 rebounds | off-min ≥ 300 and gap_reb ≥ +2.5 | rebounds over |
| C7 mirror | off-min ≥ 300 and gap_pts ≤ −4 | points under |

## Measures

**M1, carry-over (both seasons, no lines).** The population is events where X played 12+ minutes in g, as in the
pooled test.

- "excess" is X's stat in g minus his prior per-game average. It's taken in the criterion's market, with the sign
  flipped for an under.
- "selected − rest" is the selected events' mean excess minus the mean excess of every other event that season.
- **M1 passes** when selected − rest is above 0 in both seasons and the pooled 95% interval excludes 0. The
  interval comes from resampling whole games.

**M2, the lines (2024-25 only).** The population is events where X has a tip main line in the market and played. A
DNP is void.

- Each bet is a flat unit on the criterion's side at the posted price. A push is refunded.
- The measures are the hit rate and ROI, with a 95% interval from resampling games.
- The baseline is the same side on every absence event in that market.
- **PASS:** the ROI interval is above 0.
- **PROMISING:** M1 passes and the ROI is above +5%, but the interval includes 0.
- **FAIL:** anything else.

With 7 criteria, one false PASS at the 5% level happens about 30% of the time. So even a PASS only earns a forward
test. That's a shadow on 2026-27 with nothing bet, under its own pre-registration. It never goes straight to betting.

## Not changed after this point

The thresholds, populations, line rule and pass rules above stay as written. Fixes to bugs are allowed: name
matching, parsing, or a wrong join. Each one is listed in the result with its effect.
