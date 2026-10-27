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
