# NFL PLAYER PROPS PLAN — 2026-07-27 (chosen over NHL: calendar + data + no Oct/NBA collision)
Same CONSTITUTION as PGA_PLAN.md (real lines only, market-first, walk-forward, leak paranoia,
speed>smart, paper meters, one 🏈 presentation). Season opener ~Sep 10 = 5 weeks of lead.

## VERIFIED SUBSTRATE (2026-07-27)
- Historical props (Odds API, already paid): FD+DK player props 2023-2025+ — pass_yds,
  rush_yds, receptions, reception_yds, rush_attempts, pass_tds, anytime_td. ~25 events/wk.
- Grading + features: nflverse (FREE) — weekly player stats verified (5,597 rows/2024),
  also play-by-play, snap counts, injuries, depth charts.
- Live collection: task #11 plumbing (dormant) + fd_collect pattern; wire late Aug.
- CREDIT BUDGET: full 3-season × 2-snapshot pull ≈ 300k credits (of 3.36M) — sample
  weeks first (e.g. wks 3,6,9,12,15 × 3 seasons), expand only where signal.

## PHASES (compressed — lead time is the luxury here)
P1 SOFTNESS SCAN (backtestable NOW): blind vig/bias by market × band × position at real
   close prices; Tue-open vs Sun-close weekly CLV scan (two snapshots/event); known-bias
   checks: anytime-TD longshot torch, receptions over/under asymmetry, secondary-market
   (rush_attempts) sloppiness. OUTPUT: top-2 target markets.
P2 RULER: usage-share × team-volume projections from nflverse (targets/carries shares,
   pace, opponent splits). Detector, not oracle (K-SIM law).
P3 EDGES by priority:
   E1 INACTIVES TIMING (forward meter, live from wk1): 90-min-before-kickoff inactive
      reports → beneficiary bumps (WR2→WR1 target share) BEFORE reprice. THE proven playbook.
   E2 WEEK-OPENER CLV (backtestable now): Tue prices vs close on target markets.
   E3 Secondary-prop tails (attempts, alt yardage ladders — the alt-K analog).
   E4 Structural biases surviving both eras.
P4 LIVE: collector wired by Aug 31; 🏈 paper meters wk1-4; combined-board presentation.
P5 REVIEW after wk4 (~Oct 5): promote ≥+8% ROI streams to 0.5u; NBA port takes priority
   from October — NFL runs as automated side stream like MLB.

## IMMEDIATE NEXT (next session)
1. P1 sampled-weeks pull (~60k credits) + bias/CLV scans.
2. nflverse bulk pulls (2023-25 weekly + snap counts + injuries) into nfl_hist.sqlite.
