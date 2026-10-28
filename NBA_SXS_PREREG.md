# PRE-REGISTRATION: the replay tool and the side-by-side test of flagging rules

Written 2026-10-27 (committed 05:47 UTC), before any rule below has been run on any data. Research only: nothing is
bet, nothing is shown as a pick, and `nba_flags.LIVE_TIERS` stays empty.

## Why
User: "the issue with backtests is they don't reflect the profitability of forward tests whatsoever." Our
backtests do three things the live system cannot:
1. They know who sat from the box score. In the first 4 live nights, 9 of 30 regulars who didn't play were not
   listed Out or Doubtful 30 minutes before tip.
2. They bet at one archived snapshot (tip − 30), not at the price that was up when the rule would have fired.
3. They reuse two seasons that 30+ amendments were tuned on.

## The replay tool (`nba_replay.py`)
It replays the live logs as they were known at each moment:
- every FanDuel and DraftKings quote change (`nba_lines.quotes`, with each poll in `cycles`);
- every official injury report (`nba_news.snapshots`);
- box scores from before the game date only.

**A rule** is a function of what was known at time t. It returns signals (game, player, market, side, line,
book, price) at the price on the board at t.
- **Observations:** a book observes a game at a full poll (status ok or partial), or at a targeted poll that
  wrote a quote for that game. A rule never acts on a price no poll saw.
- **The nightly runner** executes the same code over each finished day, so a rule's live record and its
  replay match by construction.

**Grading** (identical for every rule):
- **Result:** from the box score. A DNP is void; a push returns 0; the stake is flat 1 unit at the signal's
  price.
- **The close:** FanDuel's board at its last observation of the game before tip.
- **CLV, the primary measure:** EV at the close = q × price − 1. Here q is FanDuel's closing no-vig
  probability of the signal's side at the signal's line:
  - if FanDuel is two-sided at that line, the no-vig of that rung;
  - if not, FanDuel's over-only alternate at that line, with the vig removed at the main rung's rate:
    q_over = (1 / o_alt) ÷ (1 / o_main + 1 / u_main), and an under is 1 − q_over;
  - otherwise the signal has no CLV, and its coverage is reported.
- **Tip:** a game whose tip's ET date is not its date (postponed) is void.

## Development vs forward
- **Fingerprint:** each rule has a fingerprint (a hash of its source and parameters) and a registration time
  in `nba_sxs_rules.REGISTRY`. A test fails if a rule's code changes without a new registration, and a new
  registration restarts its forward clock.
- **Development:** signals before registration (replayed from 2026-10-22).
- **Forward:** signals at or after registration. Only forward signals count toward a verdict.
- **Registration:** all rules below are registered at **2026-10-27T12:00:00 UTC**.

## The rules (definitions fixed now)
Shared definitions:
- **Regular:** a player who averaged ≥ 20 minutes over his last ≤ 10 appearances (≥ 3) before the date, with
  his latest appearance for the team.
- **Newly Out/Doubtful on report P:** his team was on an earlier report that day, and he was not Out or
  Doubtful on it (or not listed).
- **Teammates:** players with a board for the game whose latest appearance before the date was for the team.
  The absent player and anyone Out or Doubtful on the latest report are excluded.
- **Main rung:** two-sided, with the over nearest even money.
- **Limit:** one signal per (rule, game, player, market, side), the first.

1. **NULL_TIP30** (control). At FanDuel's last observation at or before tip − 30: every FanDuel main-line
   over in points, rebounds and assists, at FanDuel's price. Its CLV should be about −4% (the vig). This
   checks the grader.
2. **NEWS_FD.** A report P on which a regular is newly Out or Doubtful, for a game ≥ 30 min after P. At
   FanDuel's first observation of the game after P (within 10 min, or no signal): each teammate's FanDuel
   main-line over in points, rebounds, assists and PRA, at FanDuel's price. It counts only if FanDuel's main
   line and over price are unchanged from its last observation before P.
3. **NEWS_DK.** The same trigger and teammates, at DraftKings' first observation after P (within 15 min). It
   uses DraftKings' main-line over, unchanged from DraftKings' last observation before P.
4. **DK_LAGS_FD.** At every FanDuel observation of a game up to tip − 5: wherever FanDuel is two-sided at a
   line L and DraftKings' latest board prices L, take a side if FanDuel's no-vig probability of it ×
   DraftKings' price − 1 ≥ 0.03. The bet is that side at DraftKings.
5. **T4_TIP30.** T4 as registered (`NBA_T4_LIVE_PREREG.md`): the boards at tip − 30, FanDuel two-sided at L,
   DraftKings at L, EV > 2%, either side, at DraftKings.
6. **ENGINE_CARD** (logged, not replayable). The live flag engine's carded plays (`nba_shadow.flags`,
   card = 1, the earliest row per play), at the logged time, line and price.
7. **S1** (logged). `nba_proj_log.news_signals`, at the logged observation time, line and over price.

## Verdicts (forward signals only, the same bar for every rule)
- **Under 200 graded signals with CLV:** "accumulating (n/200)".
- **At ≥ 200**, from the date-clustered bootstrap 95% interval of the mean EV at the close:
  - lower bound > 0 → **BEATS THE CLOSE**;
  - upper bound < 0 → **LOSES TO THE CLOSE**;
  - otherwise **NO EDGE SHOWN**.
- **ROI**, read at ≥ 500 graded signals: lower bound > 0 → **PROFITABLE**.
- **Correction before registration (2026-10-27, about 05:53 UTC): minimum dates.**
  - The CLV verdict also needs ≥ 10 game dates, and the ROI reading ≥ 20.
  - **Why:** the development replay showed NULL_TIP30 making about 250 signals a night and DK_LAGS_FD about 100.
    Without a date minimum, either would reach 200 signals in one or two nights, when a date-clustered interval
    is meaningless.
  - No rule definition changed.
- **Grader check:** if NULL_TIP30's forward mean CLV is outside −8% to 0% (with ≥ 200 signals and ≥ 10 dates), every
  verdict is marked **GRADER CHECK FAILED**.

## Running
- Nightly on the VM after the box scores (12:05 UTC): `nba_sxs.py --run docs/nba_sxs_score.json`. It writes
  every signal to `nba_sxs.sqlite` and the scoreboard to JSON.
- Ad hoc: `nba_replay.py --rule MODULE:NAME --from DATE --to DATE` replays any rule over the logs. That gives
  a development record, never a verdict.

---

# AMENDMENT 1: four volume rules (2026-10-27, written before any of them was run)

**Why.** User: "Volume is king ... if we can predict which players on any given night will receive more or less
volume than normal, then we can easily make money from the NBA." They asked to restrict flags to players with a
reason for a volume change:
- the next man up in the depth chart when the player ahead of him is out (their example: Aday Mara with Chet
  Holmgren out);
- a minutes bump;
- a player new to the starting lineup who usually doesn't start.

The three studies the same day (`NBA_ML1_PREREG.md`, `NBA_WHY_PREREG.md`, `NBA_ZONES_PREREG.md`) found:
- generic conditions and outcome-mined filters predict nothing;
- the zone matchup is real but priced.

These rules aim at specific volume mechanisms instead. They depend on who sat and who started, which box scores
only know in hindsight, so they are tested here, point in time, forward.

**Shared definitions** (in addition to those above):
- **Position group:** G, F or C, from `nba_player_index.json` (the first letter of its position).
- **Starts:** how many of his last 10 appearances (minutes > 0, before the date) he started, from nba_matchup's
  box scores.
- **Lineup at t:** the latest `nba_lineups.sqlite` snapshot fetched at or before t for the date.
  - A team's starting five are its players with a position, under a lineupStatus of Expected or Confirmed.
  - A team is skipped when the snapshot does not list five starters for it.
- **Next man up behind X:**
  - a teammate in X's position group, not Out or Doubtful, with a FanDuel board for the game;
  - his last-10 minutes are below X's;
  - he has the most last-10 minutes of those (ties go to the lower player id).
- **Recently active:** X appeared in at least one of his team's last 4 games before the date.
- **Volume markets:** points, rebounds, assists, PRA. All bets are at FanDuel's main line and price.

The rules:

8. **DEPTH_NEXT** (fresh news).
   - **Trigger:** a regular X newly Out or Doubtful on a report, for a game ≥ 30 min after it (as NEWS_FD).
   - **Bet:** at FanDuel's first observation of the game after the report (within 10 min), the next man up
     behind X: overs in the volume markets at the current price. There is no stale-line condition.
9. **DEPTH_NEXT_TIP30** (known absences).
   - **Trigger:** at tip − 30, every regular X who is recently active and listed Out or Doubtful on his team's
     latest report.
   - **Bet:** the next man up behind each X (once each): overs in the volume markets. A player who is himself an
     X is skipped.
10. **NEW_STARTER.** At tip − 30, each player in his team's starting five in the lineup at that moment who
    started ≤ 30% of his last (up to) 10 appearances, with ≥ 3 appearances: overs in the volume markets.
    - *Corrected before registration (about 07:10 UTC).* The first wording, "≤ 3 of his last 10", let a player
      who had started 3 of his only 3 appearances count as a new starter. That surfaced on the development
      replay; the intent is "usually comes off the bench".
11. **LOST_START** (volume down). At tip − 30, each player who started ≥ 8 of his last 10 appearances, is listed
    Active, is not Out or Doubtful, and is not in his team's starting five in the lineup at that moment (the team
    listing five): unders in the volume markets.

**Registration and bars.**
- Registered at **2026-10-27T12:00:00 UTC**, with fingerprints that also cover their data helpers (lineups,
  positions, starts, schedule).
- The verdicts are the same as every other rule here: CLV first, at ≥ 200 signals and ≥ 10 dates.
- The development replay covers 2026-10-22..26. The lineup log starts on the evening of 2026-10-26, so
  NEW_STARTER and LOST_START have one night of development data.

---

# AMENDMENT 2: ROLE_OPEN, elevated roles at the opener (2026-10-27, before it was run on live data)
**Specified in `NBA_ROLE1_PREREG.md`.** This is the user's thesis: injury news, an elevated role, the first 1–3
games of the absence, and speed at the opener.

12. **ROLE_OPEN.**
    - **The moment:** a book's opener for a prop in points, rebounds, assists or threes. That is the first
      observation of the prop with a two-sided main rung (FanDuel or DraftKings).
    - **The spot:**
      - X averaged ≥ 17 min this season for the player's team (≥ 3 games);
      - X is listed Out or Doubtful on a report published before the observation;
      - this is X's absence game 1–3;
      - the player is on the active roster.
    - **The price:**
      - the ROLE1 v2 model gives the player's mean;
      - a negative binomial (r per market, `nba_role.NB_R`) gives P(side) at the opener's line;
      - that P is calibrated toward the opener's no-vig with β = 0.09.
    - **The signal:** EV′ = P′ × price − 1 ≥ 0.05. The bet is that side at the opener's price.
    - **Registered at 2026-10-27T13:00:00 UTC.** Its fingerprint covers `nba_role`'s model, pricing and data
      helpers.
    - **Verdict:** the same bars as every rule here.
    - **Live:** `nba_role_open.py --process` runs every minute on the VM with the same evaluation. It pings
      the phone (SHADOW) when it fires, and logs to `nba_role.sqlite`.

---

# AMENDMENT 3: the user's volume-to-line ratios at the opener (2026-10-27, before they ran on live data)
**Specified in `NBA_RATIO_PREREG.md`.** At a book's opener (its first observation of the prop with a two-sided
main rung, up to tip − 5), with ≥ 3 games this season:

13. **RATIO_FGA:** the points over when his FGA per game this season (box scores) ≥ the points line.
14. **RATIO_PA:** the assists over when his potential assists per game this season (nba_tracking) ≥ 2 × the
    assists line.
15. **RATIO_RC:** the rebounds over when his rebound chances per game this season (nba_tracking) ≥ 2 × the
    rebounds line.

In nba_tracking, a missing row on a fetched date counts as 0. **Registered at 2026-10-27T13:00:00 UTC**, with
fingerprints covering `nba_ratio`'s data helper. The same bars as every rule. Phone pings only for rules whose
backtest passes (NBA_RATIO_PREREG.md).

# AMENDMENT 4: RATIO_PA28 (2026-10-27, before it ran live)
16. **RATIO_PA28:** RATIO_PA at 2.8× instead of 2× (`NBA_RATIO_PREREG.md` amendment 3). This threshold was
    chosen in sample, so only forward counts. Registered at **2026-10-27T13:00:00 UTC**. It pings (SHADOW).

# AMENDMENT 5: PTS_DVP (2026-10-27, before it ran)
17. **PTS_DVP:** as `NBA_RATIO_PREREG.md` amendment 5. It fires from about mid-November, when opponents reach 10
    games. Registered at **2026-10-27T13:00:00 UTC**; no pings.

# AMENDMENT 6: the six ideas' forward rules (2026-10-27, before they ran)
**As in `NBA_IDEAS_PREREG.md` amendment 1:**
18. **RETURN_UNDER** (idea 4, passed): at tip − 30, unders for the teammates of a cleared returning rotation
    player. Pinged (SHADOW).
19. **FOUL_BIG** (idea 2, passed): at tip − 30, unders for foul-prone bigs against teams that draw free throws.
    Pinged (SHADOW); it fires once teams have 10 games and nba_matchup has this season's personal fouls.
20. **MIN_RESTRICT** (idea 5, forward only): at FanDuel's next look after an X/Bluesky item reports a minutes
    restriction, unders. No pings.

All three are registered at **2026-10-27T13:00:00 UTC**.

# AMENDMENT 7: EARLY_SURGE (2026-10-27, before it ran)
21. **EARLY_SURGE:** the early-season volume surge at the opener (`NBA_EARLY_PREREG.md` amendment 1). Registered at
    **2026-10-27T13:00:00 UTC**; no pings.
    - Later the same day, the user turned on SHADOW pings at the opener (`NBA_EARLY_PREREG.md` amendment 2). The rule is unchanged.

# AMENDMENT 8: box scores and tracking as known at the decision (2026-10-28, apparatus only)
Written before any code for it and before its effect on any signal was measured.

**Why.**
- The replay hands a rule every box score dated before the game's ET date. On a back-to-back, FanDuel often posts
  the next day's openers at about 03:00–06:00 UTC (21:00–00:00 MT), while the previous night's games are still on.
  The replay then counts a game that had not finished at the decision time t. `NBA_SPEED_PREREG.md` amendment 34
  named this as a known limit.
- Tracking has the same problem, and a larger one. The league posts a night's tracking 1–2 days later, but the
  replay reads every tracked date before the game date, whenever it was fetched.
- Live, a rule sees a final only once `nba_finals.py` stores it, about 15 minutes after the buzzer. It sees tracking
  only once `nba_tracking.py` stores it.

**The rule.** For a replayed decision at time t:
1. **A game counts only if it was final by t.** This is on top of "before the date", which stays: a game on the
   date itself still never counts.
   - No store records when a game went final. `nba_matchup.sqlite` keeps the game's ET date only (`games`: gid,
     season, date, teams, scores). `nba_season_boxes.json` keeps {date, players}. Neither keeps the tip.
   - So **the final time is the tip + 3 hours.** The tip is the schedule's `gameDateTimeUTC` as `nba_lines` stored
     it: the latest `quotes.tip_utc` for the game, the same tip the replay already uses for the day's own games.
   - **Without a tip on the game's ET date** (no quotes, or the game was moved), the final time is the end of its ET
     date + 3 hours (03:00 ET the next day). That is the latest it can be.
   - **Why 3 hours:** a regulation game takes about 2¼ hours from tip, and an overtime adds about 20 minutes. Live
     sees a final about 15 minutes after the buzzer. So the replay can trail live by up to about 45 minutes after a
     typical game, and leads it only if a game runs past 3 hours.
2. **A tracking date counts only if it was stored by t.** Every row for that date in `nba_tracking`'s `fetched`
   table must have `fetched_at` ≤ t. That stored time exists, so it is used. Otherwise the date counts as not
   fetched: no potential assists or rebound chances come from it, as live.
3. **Scope:** everything a replayed rule reads from box scores or tracking.
   - The View's appearances (`team_of`, `last10_min`, from `nba_gamelogs` logs and `nba_matchup`).
   - The data helpers built from the rules' matchup and tracking stores: RoleData, RatioData, DvpData, EarlyData,
     FoulData and VolumeData.
   - The replay applies the rule to the stores, not to the rules. At each moment it gives the rules the matchup
     and tracking stores without the games and dates not yet known, and filters the View's history the same way.

**What does not change.**
- **No rule, threshold, helper or View code changes.** A REGISTRY fingerprint hashes the rule's class source, the
  shared helpers, the View, its deps and its spec, and none of those is edited. Every fingerprint and registration
  stays valid, and no forward clock restarts.
- **Why that is honest:** this prereg defines a rule as "a function of what was known at time t". The replay broke
  that contract by handing rules games and tracking that were not known yet. The fix makes the tool match its own
  contract and the live pinger. No rule's text or code changes.
- Grading is unchanged. Results still come from the box score, the close from FanDuel's board.
- Lineups, injury reports, news items and boards were already read as of t.

**Recomputing.**
- `nba_sxs.py` keys a stored day by rule fingerprint, so on its own it would never recompute the older days. It
  now also keys a day by an apparatus version (8), so the first run after deploy recomputes every day from
  2026-10-22.
- The forward record so far (from 2026-10-27 12:00 UTC, at most a night or two) is replaced by its recomputation.
  No rule can have a verdict yet (a verdict needs 10 dates), so no verdict changes.
- A recomputed day is now also stable: data that arrives later no longer changes it.

**Tests (with mutants that must fail).**
- A synthetic back-to-back: last night's game ends after an overnight opener. The opener rules must not see it,
  and the tip − 30 rules must.
- Tracking fetched after t is not read.
- Mutants: the game counts from its tip; the as-of filter dropped from the stores or from the View's history; an
  unknown tip counts; `fetched_at` ignored.

**Measured after this is written (reported, never used to change it):** on read-only copies of the VM's stores
from 2026-10-22, how many graded signals change for each rule (added, removed, or different), and each rule's
development CLV and ROI before and after.

**Not done here:** storing when `nba_finals.py` stored each final. That would give the exact time live saw a game,
but it changes live code.

# AMENDMENT 9: BOOST and BOOST_NH (2026-10-28, before they ran)
22. **BOOST:** a starter (26+ min/g) out in absence game 1–3; at a book's opener, a teammate's over (−150 or better)
    when 80%+ of his past games without that starter but with tonight's other starters beat the line
    (`NBA_BOOST_PREREG.md`). All 8 markets. Pinged (SHADOW).
23. **BOOST_NH:** the same rule's no-history flags (fewer than 3 such games; the position rules put him 15%+ over the
    line). No pings.
24. **BOOST_STEP:** the no-history flags for the step-in player raised to 24 minutes (`NBA_BOOST_PREREG.md`
    amendments 2–3), split out of BOOST_NH before either ran. Pinged (SHADOW).
    - Re-registered at **2026-10-28T20:30:00 UTC**, before any of the three ran: the starters and step-ins now come
      from the lineup tab (`NBA_BOOST_PREREG.md` amendment 4).

Both are registered at **2026-10-28T21:00:00 UTC**.

25. **BOOST_PICKUP** (`NBA_BOOST_PREREG.md` amendment 6): the bench pickup for a new starter once NBA.com's lineup is posted, on the MINUTES study's fitted model. No pings.
    - BOOST_STEP now runs on the MINUTES blend for all new starters (amendment 6). BOOST, BOOST_STEP, BOOST_PICKUP and BOOST_NH are re-registered at **2026-10-28T22:00:00 UTC**.
