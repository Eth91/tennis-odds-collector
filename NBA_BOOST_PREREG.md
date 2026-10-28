# PRE-REGISTRATION: BOOST, players who gain when a teammate is out

Written 2026-10-28 (about 19:13 UTC), before the rule was built or run on any data. It is research: nothing is bet
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

## Result (2026-10-28, about 19:18 UTC): FAIL
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

# AMENDMENT 1: what pings, and the two registered rules (2026-10-28, about 19:23 UTC, after the result, before live)
**Asked after the result** (about 30 flags a day, losing at tip lines), the user chose: **only the history flags ping**
(5–6 a day). The no-history flags are recorded silently. Every flag is still tracked against the closing line.

- **Side-by-side:** two rules with the same decision, split by kind, so each has its own record:
  - **BOOST**: the history flags (rule 9);
  - **BOOST_NH**: the no-history flags (rule 10).

  Both registered at **2026-10-28T21:00:00 UTC** (`NBA_SXS_PREREG.md` amendment 9).
- **Live (`nba_role_open.py`):** rows go to `ratio_signals` as BOOST (pinged) or BOOST_NH (not pinged), one per
  (rule, game, player, market) across books. The value column holds the hit rate (BOOST) or the projection (BOOST_NH).
- **The combo markets are new to the live pinger** (it watched points, rebounds, assists and threes). On the first run
  after deploy, combo props already on the board are marked open without acting, as at install, so only true openers
  are judged.

# AMENDMENT 2: the no-history projection, as the user asked (2026-10-28, before it was built or run)
**Why:** live, Daniss Jenkins was projected 17.5 points on an 8.5 line. 8 of his last 10 games with Duren were last
April's, when Detroit rested its starters and he played 33–37 minutes.

**User:** "yes make that fix. You need to add likely minutes context: if a player jumps into the starting lineup
they'll likely get 20–25+ mins, but look at games where they also play with other starters. Like Hartenstein with
Shai." Asked: who steps in → **the top bench player at the missing starter's position**; his minutes → **at least
24**.

Changes to rule 10 only (the history rule 9 and everything else is unchanged):
1. **base_s(A)** is A's per-game average over games for T in which A, X **and every other starter playing tonight**
   (except A) played. This season's such games if there are 3 or more (the last 10), otherwise last season's if 3 or
   more (the last 10), otherwise A has no base.
2. **The step-in player:** among the active roster's non-starters in X's position group (G, F or C), the one with
   the most minutes per game over his base games (rule 1). None if X has no listed group.
3. **His minutes floor:** if his projected minutes are under 24.0, they become 24.0. Each of his stats then gains
   (24.0 − projected minutes) × base_s ÷ base minutes, his own per-minute rate.
4. The bar is unchanged: relevant, projection ≥ 1.15 × line, projected minutes ≥ 20.

**Check:** rerun the backtest. Reported as before, with BOOST_NH old vs new. The user chose live pings either way,
and BOOST_NH stays silent. Both rules are re-fingerprinted; if they are deployed before 21:00 UTC their registration
time is unchanged, otherwise it moves to the deploy time.

**Amendment 2: run (2026-10-28, about 19:50 UTC). Still FAIL.** History flags are unchanged (804, −11.1%; 1,016,
−6.3%).

| no-history flags | 2023-24 | 2024-25 |
|---|---|---|
| before (amendment 1) | 3,869, −8.5% | 3,733, −5.0% |
| after | 2,944, **−11.3%** | 2,922, **−0.7%** |
| of which the step-in player at the 24-minute floor | 129, hit 57.4% (no-vig 49.1%), **+11.3%** | 102, hit 60.8% (49.6%), **+15.6%** |

All flags: −11.3% and −2.2%.

**The step-in subset, found after looking, so not a pass:**
- 231 flags but only 95 player-nights, since several markets share one night. Per player-night: +12.0%, 90% bootstrap
  (−3.7%, +27.2%).
- 54 players; at most 19 flags from one (Moritz Wagner). Positive in 7 of 8 markets (assists −11%, n 17).
- They averaged 21.7 actual minutes, and only 40% played 24+. The floor overshoots their minutes, yet they beat the line.
- No clean season is left in the archive (it starts 2023-05), so only the forward record can test it.

# AMENDMENT 3: the step-in flags as their own rule, pinged (2026-10-28, before it ran)
**User:** after seeing the subset above, chose "own rule, ping it".
- **STEP flag:** a no-history flag (rule 10) where the flagged player is the step-in player (amendment 2) and his
  projected minutes were raised to the 24-minute floor.
- **Preference (rule 12):** a history flag, then the higher hit rate, then a STEP flag, then more history games.
- **Three registered rules** (`NBA_SXS_PREREG.md` amendment 9): BOOST (history, pinged), BOOST_STEP (pinged) and
  BOOST_NH (the other no-history flags, silent).
- **Ping:** "🟢 BOOST STEP {player} {market} o{line} {price} {book} · {X} out (game n) · steps in, proj {proj} at 24
  min · shadow".
- **Forward bar:** as for every rule, CLV at ≥ 200 signals over ≥ 10 dates. At about one flag every 1–2 days that
  takes a season. A first look at 50 player-nights is information only.

# AMENDMENT 4: starters and step-ins from the lineup tab (2026-10-28, about 20:20 UTC, before code)
**User:** "your step ins are wrong though, it'll be Ayo Dosunmu, Anthony Black will step in for Suggs and da Silva
for Banchero. The [props page's] expected starters in the lineup tab are the most accurate, so go off that."
(Amendment 2's pick, the top bench player at the position by minutes, chose Jevon Carter and Jamal Cain. Black was
excluded because he plays 26+ minutes, which made him a "starter".) Asked:
- at the opener → **the lineup tab's projected five, then NBA.com's expected lineup when it posts**;
- STEP → **only low-minute bench players** (projected under 24 minutes, raised to 24);
- the starter who is out → **the lineup tab's usual five**.

**Evidence behind the STEP choice** (backtest, amendment 2's step-in pick, no-history flags):

| step-in player | 2023-24 | 2024-25 |
|---|---|---|
| raised to the 24-minute floor | 129, +11.3% | 102, +15.6% |
| already projected 24+ | 269, −10.4% | 336, +6.3% |
| not the step-in | 2,546, −12.5% | 2,484, −2.4% |

**Live definitions (pinger and side-by-side).** They mirror `nba_research.py` (`lineups`, `projected_lineups`, at
6597057306), copied rather than imported, so the page can change without moving the rule:
1. **Usual five of team T:** the five players now on T with the most starts in T's last 10 games this season (ties:
   more minutes), counting only players with a start. It needs 3 team games this season. Box-score starter flags
   come from `nba_matchup` (this season and last).
   - **Starters** (rules 2, 4, 8 and amendment 2) are the usual five.
   - With fewer than 3 games, or no starter flags, rule 2's 26+ minutes applies. **The backtest always uses this**,
     since the 2023-25 logs have no starter flags.
2. **Tonight's five:**
   - NBA.com's lineup when posted: the latest `nba_lineups` snapshot for the date fetched by the decision time, the
     players with a position, Expected or Confirmed.
   - Otherwise the projected five: the usual five minus anyone out (Out or Doubtful). Each missing usual starter u is
     replaced, surest first, by the available player who maximizes, in order:
     - the number of T's games (in the seasons u played for T) that u did not start and he did;
     - whether his listed position shares a letter with u's;
     - his starts, then his minutes, in T's last 10 games.
3. **New starter:** in tonight's five but not the usual five. Each new starter is paired with a missing usual starter
   by the same order, surest first. **The step-in player** for X is the new starter paired with X; none if there is
   no pairing.
   - The backtest keeps amendment 2's pick (the top bench player at X's position by minutes).
4. **STEP flag:** unchanged (amendment 3). The step-in player's projected minutes were under 24 and raised to 24,
   and the rest of rule 10 holds.
5. **When:**
   - At each book's opener, with tonight's five as of then (NBA.com if posted, else projected).
   - Again for STEP only, at the first look after a player first appears as a new starter in NBA.com's lineup, for
     each of his props whose opener came before that snapshot, at that prop's current main line. Live, that is the
     first pinger run; in the side-by-side, it is that book's next observation.
   - One flag per (rule, game, player, market). Nothing within 5 minutes of tip.
6. **Re-registration:** all three rules change (the starters feed every one) and are re-fingerprinted. They are
   registered at the deploy time, since 21:00 UTC will have passed.

**Amendment 4: deployed d36ecff5be at about 20:16 UTC; all three rules registered at 20:30 UTC.** The backtest is
unchanged (it has no starter flags or lineups, so it keeps the minutes-based definitions). On the deploy run, the
second check against NBA.com's 20:15 lineup sent one STEP ping: Kenrich Williams (OKC, in for Holmgren, game 2) P+R
over 13.5 at −114, projected 15.7 at 24 minutes. Black (33.5 projected minutes), da Silva (28.1) and Dosunmu (33.1)
already project 24+ minutes, so by the user's choice they are not STEP flags.

# AMENDMENT 5: the step-in projection from his big-role games (2026-10-28, about 20:35 UTC, before code)
**User:** "Jared McCain likely sees 25–30 minutes tonight and he averages 15.7 points in games where he plays 25+
minutes, why is your projection 10.3? ... Huff and Walter ... Walter likely sees 27–30 minutes today and in games
when he sees 27+ minutes he's over his line 67% of the time and averages 15.2 points."

**Checked first** (nba_matchup, 2025-26 and 2026-27, any team):
- McCain: 8.5 points in all games; 13.0 in his 4 starts (29.8 min); 15.8 in his 13 games of 25+ minutes.
- Walter: 7.7 / 10.1 in 20 starts / 12.2 in 25+ min (13.1 in 27+).
- Huff: 9.4 / 10.8 in 48 starts / 13.5 in 25+ min.
- **The bias:** a 25+ minute game is partly chosen by how it went (a hot night, overtime, no foul trouble). For 91 bench
  players (under 22 min a game, 30+ games, 5+ starts and 5+ games of 25+ min, 2025-26): 10.3 points when they
  started (26.2 min) and 12.2 in their 25+ minute games (29.4 min).

**Asked:**
- baseline → **his starts, else his 25+ minute games shaded down 15%**;
- games → **any team, this season and last**;
- bar → **his baseline average 15%+ over tonight's line**;
- bench guy → **under 24 minutes a game this season**.

**The STEP projection (replaces amendment 2's 24-minute floor):**
1. **Bench guy:** the step-in player's (amendment 4; in the backtest, amendment 2's pick) minutes per game this season,
   any team, before the date. This season's games if 3+, else last season's if 10+. The bar is under 24.0.
2. **Baseline,** from his games for any team this season and last, before the date:
   - **starts:** his last 10 games with a starter flag of 1, if there are 3 or more; the per-game averages;
   - **otherwise 25+ minutes:** his last 10 games of 25.0+ minutes, if 3 or more. Points, rebounds, assists and
     threes are × 0.85; minutes are unshaded;
   - otherwise none.
   - The backtest has no starter flags, so it always uses the 25+ minute baseline.
3. **The flag:** a step-in bench guy with a baseline, with no history (h < 3), X relevant to the market, the baseline
   (summed for a combo) ≥ 1.15 × tonight's line, baseline minutes ≥ 20, and the price −150 or better. That is a STEP
   flag.
   - A step-in who is not a bench guy, or has no baseline, gets rule 10's redistribution with no floor (BOOST_NH if it
     fires).
   - The other players are unchanged.
4. **Ping:** "· steps in, avg {proj} in his {n} starts" or "· steps in, {proj} in his {n} games of 25+ min (−15%)".

**Check:** backtest on 2023-25, as before, STEP reported separately. As chosen earlier, it goes live whatever the
result. All three rules are re-fingerprinted and registered at the deploy time.
