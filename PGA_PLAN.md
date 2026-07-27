# PGA PROFITABILITY PLAN — 2026-07-27
Goal: a profitable golf betting operation. Priority order: inefficient submarkets > info/speed
edges > pricing residuals. NOT the goal: out-modeling books on the sharp market (MLB lesson).

## CONSTITUTION (laws from the MLB/WNBA campaigns — non-negotiable)
1. REAL LINES ONLY. No backtest without actual historical prices. No proxy lines, ever.
2. MARKET FIRST, MODEL SECOND. Rank submarkets by softness BEFORE building any predictor.
   Limits are a treasure map: small max bet = the book knows it's weak there.
3. WALK-FORWARD: dial on old seasons, ONE shot on the recent season, then live paper.
   The holdout is spent after one look. Live record is the only unspent judge.
4. LEAK PARANOIA: as-of data only. Every strong sandbox result is presumed leaky until the
   as-of rebuild proves otherwise (NRFI/put-away/K-SIM v1 all died of self-inclusion).
5. SPEED BEATS SMART: information edges (weather waves, WDs, tee times) outrank
   modeling edges. Never gate a speed play on the book having already reacted.
6. HIT%=PRICE in efficient two-sided markets. A 70% golf slice at plus money is a leak
   until proven otherwise on as-of data.
7. PAPER METERS FIRST: every stream ships as a self-grading shadow before money;
   promotion bar and kill tripwire (<b/e after N) defined BEFORE launch.
8. ONE MODEL presentation: single "⛳ PGA" ping format + board section; streams tracked
   separately underneath.

## WHY GOLF SHOULD BE SOFTER THAN MLB (theses to verify, not assume)
- 156-player fields: books must price thousands of derivative objects (matchups, 3-balls,
  top-20s, props) weekly; sharp attention concentrates on ~20 names + outrights.
- 3-balls/tournament matchups: historically THE soft golf market; small limits.
- Wave/weather asymmetry: AM/PM tee waves can differ by strokes in wind; matchup/3-ball
  prices post BEFORE weather firms → cross-wave timing edge (our opener-strike analog).
- Props (birdies o/u, round score o/u): template-generated from a scoring model →
  tail mispricing potential (our alt-K-ladder analog).
- Weekly cadence: books re-price 1000s of objects every Monday — recurring opener softness.

## PHASE 0 — RECON (no modeling; ~2 sessions)
0.1 Market inventory at OUR books (FD/DK via existing collector tech): which golf markets
    post, when (Mon open vs Wed), 2-sided vig per market, limits per market (manual check).
0.2 Data source audit:
    - The Odds API (already paid, 3.4M credits): golf sport keys, outrights + h2h coverage,
      HISTORICAL depth for golf (spot-check credits cost). Matchup/3-ball coverage = key ?.
    - DataGolf: free endpoints vs Scratch tier (~$30/mo): SG data, rankings, predictions,
      HISTORICAL MATCHUP+3-BALL ODDS ARCHIVE (if accessible = our entire backtest substrate).
      [USER DECISION: subscribe if free tier insufficient]
    - Free: PGATour stats site (SG per round), OWGR, weather APIs (free tier fine),
      tee times via PGA site/leaderboard APIs.
0.3 Results/grading source: leaderboard + per-round scores API (statsapi-equivalent for golf).
GATE G0: we can (a) collect live golf lines at our books, (b) obtain real historical prices
for at least ONE derivative market, (c) grade automatically. If (b) fails for all markets →
golf is forward-test-only (collect now, backtest never; decide whether to proceed on paper).

## PHASE 1 — SOFTNESS SCAN (structural, no predictor; 1 session per market)
For each market with historical prices (else queue for forward meters):
1.1 Blind vig/hold map + favorite-longshot bias scan (by price band, by field strength).
1.2 3-ball position bias (does the "name" player get overbet?), matchup fav/dog blind ROI.
1.3 Opener-vs-close CLV behavior: how much do prices move Mon→Thu? Where is the drift
    systematic? (recurring weekly opener-softness candidate).
1.4 Props curve audit: birdie/score lines vs realized distributions (template tails).
OUTPUT: ranked softness table → pick TOP 2 submarkets only. Everything else parked.

## PHASE 2 — FAIR-PRICE RULER (1-2 sessions; NOT an oracle)
A simple SG-based rating (DataGolf rankings if licensed, else rolling SG-total Elo from
results) + matchup/3-ball simulator (round-score distributions, within-group correlation).
Purpose: detect when a posted price is off OUR ruler AND off consensus — a mispricing
detector, not a better model. Calibrate vs closing lines; EXPECT convergence (K-SIM lesson);
value = the residual ranker + prop-curve pricer.
GATE G2: ruler within ~2pts logloss of closing devig on matchups. If it can't get close,
it can't detect mispricing — stop, rely on pure structural/timing plays.

## PHASE 3 — EDGE CANDIDATES (strict priority order; sandbox→one-shot→paper each)
E1. WAVE/WEATHER TIMING (highest prior — our proven playbook): cross-wave matchups/3-balls
    bet when forecast diverges from price-set assumptions. Data: hourly forecasts + tee
    times + price timestamps. Backtest if historical odds allow; else straight to meter.
E2. WEEKLY OPENER STRIKE: Monday prices vs Thu close on our top-2 markets (CLV harvest).
E3. PROPS TAILS: birdies/score-line curves priced off our ruler (alt-ladder analog).
E4. STRUCTURAL BIASES from Phase 1 (fav/longshot, name-bias) if any survive both years.
E5. COURSE-FIT RESIDUALS (lowest prior — most modeled by books; only if E1-E4 thin).

## PHASE 4 — LIVE OPERATION (mirror the MLB machine; 1 session to wire)
- golf collector into fanduel_props.sqlite pattern (fd/dk golf markets, timestamped).
- ⛳ PGA one-format pings + board section + combined record; per-stream tables underneath.
- Paper meters for anything unbacktestable; auto-grading from results API.
- Tripwire: any stream <52% implied-b/e pace after 25 graded → auto-bench + alarm.
- 4-week forward test minimum before real money (weekly cadence = be patient).

## PHASE 5 — REVIEW & SCALE
Review at 4 tournaments graded (~late Aug, aligns with 8/23 MLB review): promote streams
beating paper expectations to 0.5u real; kill the rest. Success = any stream with
+8% ROI on 30+ graded bets at real prices. Capacity check: golf matchup limits (~$250-500)
cap this as a side stream like MLB — treat accordingly.

## BUDGET & CADENCE
- Costs: $0 baseline (existing Odds API + free sources); DataGolf Scratch ~$30/mo pending
  Phase-0 verdict [USER DECISION]. No new infra (VM hosts collectors).
- Calendar: Wyndham (Aug 6-9), FedEx playoffs (Aug 13-30) = perfect paper window;
  fall series = promotion window. NFL props opener (Sept) remains the other Q3 priority.
- Effort guardrail: Phase 0-2 ≈ 4-6 sessions total. If Phase 1 finds NO soft submarket
  with obtainable prices, we stop at a cheap "golf is closed" verdict — that outcome is
  a win too (the MLB lesson: a proven no beats an expensive maybe).
