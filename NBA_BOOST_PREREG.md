# PRE-REGISTRATION: BOOST, players who gain when a teammate is out

Written 2026-10-28 (about 19:15 UTC), before the rule was built or run on any data. It is research: nothing is bet
automatically, `nba_flags.LIVE_TIERS` stays empty, and pings carry the SHADOW label.

## The user's idea
"Just flag those players who benefit from a player on their team being out ... Tari Eason clears his rebound line
100% of the time playing 20+ minutes in games with Durant, Thompson, Smith Jr, but without Sengun ... Hartenstein
clears his 9.5 rebound line 100% of the time without Chet Holmgren ... some players matter more to one player being
out than others ... a PF/C matters more for rebounds than a guard. But a starter being out in general that takes a
lot of shots means most of the starters get a jump, but you gotta look at historical logs as some players do benefit
more points-wise."

## What the data said before the design (shown to the user)
- Hartenstein, 2024-25: 11.6 rebounds a game without Holmgren, 9.0 with him. But his posted rebound line averaged
  9.7 with Holmgren and 11.4 without him, and against the posted line he went 18 over, 17 under without Holmgren.
  The book's first line without Holmgren was 9.5; within about two games it was 10.5–12.5.
- Eason, 2025-26, without Sengun but with Durant, Thompson and Smith Jr., 20+ minutes: 6, 8, 8, 13, 9 rebounds
  (8.8 a game), against 6.2 with Sengun.
- So the bump is real, the books price it, and any edge is in catching the line before they do.

## The user's choices (asked one by one, 2026-10-28)
| Choice | Answer |
|---|---|
| Line a flag is judged against | Tonight's posted line |
| Which missing teammates trigger a look | Starters, defined as 26+ minutes per game |
| Which absence matters for whom | Position rules first, then the player's real with/without games take over |
| How the position rules decide | By the missing player's own numbers |
| When it fires | At the opener, games 1–3 of the absence |
| Markets | Points, rebounds, assists, threes and the combos (P+R, P+A, R+A, P+R+A) |
| Who else must have played in a history game | The missing player out, the other starters playing tonight in |
| History games needed | 3 |
| The 20+ minutes condition | Count every history game he played; he must average 20+ minutes in them |
| Flag bar with history | 80%+ of his history games beat tonight's line |
| Seasons | This season and last, same team only |
| No history (fewer than 3 games) | Position rules alone may fire, labeled "no history" |
| History vs position disagree | An absence the position rules call irrelevant needs 6+ history games |
| No-history bar | The position-rule projection is 15%+ over tonight's line |
| Price | Skip overs worse than −150 |
| Go-live | Backtest, then shadow pings either way |
| Backtest pass | Positive ROI in both 2023-24 and 2024-25, each with 100+ flags |

## The rule, exactly
Everything reads only games before the date. "Team games" are team T's box scores in this season and last season.

1. **Base games for a player on team T:** his games for T this season if he has 3 or more; otherwise his games for
   T last season if he has 10 or more; otherwise none.
2. **Starter:** a player whose minutes per game over his base games for T is 26.0 or more.
3. **On the team:** X is on T at a past game if his last appearance before that game was for T and his next
   appearance after it (before tonight) is for T or does not exist. Tonight, X is on T if his last appearance was
   for T.
4. **The missing player X:** a starter of T who is out tonight. Live: the official injury report lists him Out or
   Doubtful, as ROLE_OPEN reads it. Backtest: he is on T and did not play (box score; hindsight, as in ROLE1).
5. **Absence game n:** the number of consecutive T games X has missed, counting tonight, across both seasons. A
   spot is n = 1, 2 or 3.
6. **Relevance (the position rules, by X's own numbers):** rank T's players by per-game average over their base
   games (players without base games are left out).
   - rebounds: X is in T's top 2 in rebounds;
   - points and threes: X is in T's top 3 in FGA;
   - assists: X is in T's top 2 in assists;
   - a combo: any of its parts is relevant (P+R: points or rebounds; P+A: points or assists; R+A: rebounds or
     assists; P+R+A: any).
7. **The player B:** a teammate with a line tonight (live: the book's opener; backtest: the FanDuel/DraftKings main
   tip line, the one closest to even money). Backtest props where B did not play are void and dropped.
8. **History games for (B, X):** team games before tonight in which B played for T, X did not play and was on T,
   and every other starter of T who is playing tonight (live: not listed Out or Doubtful; backtest: played) played.
   h = the number of them.
9. **With history (h ≥ 3), the flag needs all of:**
   - B's average minutes over the h games is 20.0 or more;
   - the share of the h games in which B's stat beat tonight's line (stat > line) is 0.80 or more;
   - X is relevant to the market, or h ≥ 6.
10. **Without history (h < 3), the flag needs all of:** X is relevant to the market, and the position-rule
    projection is ≥ 1.15 × tonight's line with projected minutes ≥ 20.0. The projection, for each stat s (minutes,
    points, rebounds, assists, threes; a combo sums its parts):
    - **base_s(A)** for each player A: A's per-game average of s over his last 10 games for T in which X played
      (this season and last); at least 3 such games, otherwise A has no base. B needs a base.
    - **X's share:** X's per-game s over his base games (rule 1).
    - **The active roster:** players who played for T in any of T's last 3 games, minus everyone out tonight.
    - **Weight:** w(A) = 3 if A's position group (G, F or C, the first letter of the listed position, as ROLE1)
      equals X's, else 1.
    - **Projection:** base_s(B) + X's share × base_s(B) × w(B) ÷ Σ over the active roster with a base of
      base_s(A) × w(A).
11. **Price:** the over is priced −150 or better (decimal ≥ 1.6667). Live: the opener book's price. Backtest: the
    best FanDuel/DraftKings over price at the main line.
12. **One flag per (game, player, market).** With several starters out, a history flag is preferred to a
    no-history one, then the higher hit rate, then more history games.
13. **Over only.**

## The backtest
- **Data:** `.projdata/nba_gamelogs.sqlite` (logs_full 2022-23 to 2025-26, positions) and the 4-book tip-line
  archive (`~/nba-engine/basketball_nba_odds_hist.sqlite`, FanDuel and DraftKings), 2023-24 and 2024-25, regular
  season and playoffs. History for 2023-24 reads 2022-23 and 2023-24; for 2024-25, 2023-24 and 2024-25.
- **Graded:** stat > line wins at the price, stat < line loses one unit, equal is a push (stake back). ROI per unit.
- **Reported per season:** flags, hit rate (pushes dropped), ROI, the mean no-vig over probability (FanDuel's pair,
  else DraftKings'), and the same split by history vs no history, by market, by absence game n, and by relevant vs
  irrelevant-with-6+. A bootstrap 90% interval on ROI is reported for information.
- **Pass (the user's bar):** ROI > 0 in 2023-24 and in 2024-25, each season with ≥ 100 flags.
- **Honest limits:**
  - tip lines are not openers: the archive cannot show a stale opener, which is where the user expects the edge;
  - the backtest reads absences from box scores, while live reads the injury report;
  - the design was shaped after looking at two examples (Hartenstein, Eason), both in seen seasons.

## The forward test
- **Live (after the backtest, whatever it shows, as the user chose):** `nba_role_open.py`, at each book's opener for
  all 8 markets, the same decision as above with this season's box scores (`nba_matchup`) and last season's logs
  (`nba_gamelogs`), the injury report for "out tonight". One row per (rule, game, player, market) in
  `ratio_signals`, deduplicated across books. Ping: "🟢 BOOST {player} {market} o{line} {price} {book} · {X} out
  (game n) · {hits}/{h} beat {line} without him, avg {avg}" or "· no history, proj {proj}", then "· shadow".
- **Side-by-side:** registered in `nba_sxs_rules.py` as BOOST with its fingerprint, so the nightly replay records
  its CLV and ROI on the same bars as the other rules (CLV at ≥ 200 signals over ≥ 10 dates).
- Nothing is called an edge without the forward record.

## Result (2026-10-28, about 19:45 UTC): FAIL
`python3 nba_boost.py --json .projdata/boost_result.json`. The game logs hold regular seasons only, so the archive's
playoff props have no box score and drop out.

| | 2023-24 | 2024-25 |
|---|---|---|
| flags | 4,673 | 4,749 |
| hit rate (book's no-vig) | 47.8% (49.7%) | 49.5% (49.6%) |
| ROI (90% bootstrap) | **−9.0%** (−11.3%, −6.8%) | **−5.3%** (−7.6%, −3.1%) |
| with history (the 80%+ rule) | 804, −11.1% | 1,016, −6.3% |
| no history (position rules) | 3,869, −8.5% | 3,733, −5.0% |
| absence game 1 / 2 / 3 | −9.0% / −10.1% / −7.3% | −1.5% / −14.8% / −3.4% |
| irrelevant absence, 6+ games | 168, −24.6% | 204, +10.8% |

By market, every market loses in both seasons (−2% to −13%).

**Reading:**
- The flags hit about as often as the book's own fair price says (48–50% against 49.6%), so the books priced these
  bumps at tip, and the juice is the loss.
- The user's exact framing, 80%+ of past without-X games beating tonight's line, hit 47% and 48%. Restricted to
  100% histories: 319 flags, −5.2%, and 345, −15.1%.
- Trade-deadline artifacts (the missing player next appears for another team, 4.9% of flags) do not change it:
  without them −8.1% and −5.0%.
- Volume: about 30 flags a day (5–6 with history) on 10–11 players.
- The archive has tip lines only. Whether openers are stale before the injury news is priced is what the forward
  test can show and this backtest cannot.
