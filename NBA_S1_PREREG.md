# PRE-REGISTRATION: S1, the news-window signal (forward only)

Written 2026-10-27, before S1 has run on any data. Research only: nothing is bet, nothing is shown as a pick,
and `nba_flags.LIVE_TIERS` stays empty.

## Why (development data, 2026-10-22..25)
- **FanDuel's stale window** (`nba_news_latency.py`). After an official report newly lists a regular
  (≥ 20 min) Out or Doubtful:
  - FanDuel had moved 0.7% of his teammates' props by our first fetch, about 3 s after publication;
  - the ones that move do so after about 3 minutes (median; 75% within 16);
  - 18% had already moved in the hour before the report.
- **Blind teammate overs** at FanDuel's price 30 s after the report: CLV +0.28 points, ROI +1.6%
  (n 540, correlated within 15 events).
- **The shadow flags:** 77 graded, ROI −8.3%. 64 of the 77 were logged 2+ hours after their news, after
  FanDuel had priced it.

S1 keeps the speed and lets the model choose the teammates.

## Rule
1. **Trigger:** a new official report P on which a regular (averaging ≥ 20 min over his last ≤ 10
   appearances) is newly Out or Doubtful for a game more than 30 min from tip. "Newly": his team was on
   an earlier report that day and he was not Out or Doubtful on it.
2. **Price:** FanDuel's board at the first observation after P (the nba_watch fetch after the report),
   for his teammates' props (points, rebounds, assists, threes, P+R, P+A, R+A, PRA) at FanDuel's main
   line. The prop counts only if FanDuel's main line and its no-vig P(over) are unchanged from the last
   observation before P, so the price is stale.
3. **Model:** proj-1.1.1, with F0's game-day inputs as of P (`live_inputs` with the report statuses and
   lineups seen at P), gives P(over | no push) at FanDuel's main line.
4. **Signal:** over, if the model's P(over) − FanDuel's no-vig P(over) ≥ 0.05. At most one signal per
   player, market and event, at FanDuel's over price at that observation.

## Grading and decision
- **CLV, the primary measure:** FanDuel's no-vig P(over) at the same line at tip − 30, minus at the signal.
- **ROI:** flat 1 unit at the signal price; a DNP is void and a push returns 0.
- **Bar:**
  - ≥ 300 graded signals;
  - mean CLV with a lower 95% bound above 0 (date-clustered);
  - ROI's lower bound above 0, read at 500 signals.
- **Below 300:** "not enough prospective evidence".
- **Reported, no decision:** by market, by the size of the model's edge, and by delay after P.

## Implementation
`nba_news_window.py` runs every minute on the VM. For each new report, once nba_watch has fetched lines
after it, it logs S1 signals (with the model's inputs) to `nba_proj_log.sqlite` table `news_signals`.
It is graded nightly into `docs/nba_s1_score.json`.
