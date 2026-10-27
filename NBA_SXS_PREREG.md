# PRE-REGISTRATION: the replay tool and the side-by-side test of flagging rules

Written 2026-10-27 (about 06:00 UTC), before any rule below has been run on any data. Research only: nothing is
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
- **Correction before registration (2026-10-27, about 08:00 UTC): minimum dates.**
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
