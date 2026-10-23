# PRE-REGISTRATION — the two price leads, on playoff games no test has graded

Written and committed **before any playoff box score is fetched.** 2026-10-23.

## Why
`NBA_PRICE_EDGE_PREREG.md` (KILL) left two leads, found by cutting its own results after seeing them:
1. **BetMGM as the outlier**: P1 bets where the disagreeing book was BetMGM, +9.09% (n=1,258,
   CI [+2.65, +15.68]).
2. **Large edges**: the best-outlier bets with EV ≥ 6%, about +5.9% (6–10%: +5.15%, n=1,350;
   ≥ 10%: +10.12%, n=252).

A lead found by slicing has to be checked on data it never saw. The odds history holds **124
postseason nights (play-in and playoffs, 2023-05-03 → 2025-06-22)** that no test has graded, because
the stored box scores (`logs_full`) are regular season only. The two NBA Cup finals (2023-12-09,
2024-12-17) are also ungraded and are excluded: they are not postseason, and there are only two.

## The rules — exactly P1's, nothing re-tuned
`nba_price_edge.py`, unchanged: pre-tip snapshot; ≥ 3 books two-sided at the exact line; leave-one-out
proportionally de-vigged consensus; the single highest-EV book-side per (date, player, stat, line);
void if the player did not play; flat 1 unit at the offered price.
- **Lead 1**: those bets with EV ≥ 3% **where the book is BetMGM**.
- **Lead 2**: those bets with **EV ≥ 6%**, any book.

## Size and power, stated before any outcome
Counted from the odds alone (no box score needed): **Lead 1 ≈ 104 bets, Lead 2 ≈ 108** across the
three postseasons, a little fewer after voids. P1 at EV ≥ 3%: ≈ 677. At n ≈ 105 a single bet's
standard deviation (~1 unit) gives an ROI standard error of about ±10 points. So:
- if a lead's true edge were +9%, this check shows ROI > 0 about 80% of the time, but a CI clearing
  0 only about 15% of the time;
- if the true edge is 0 (what P1 as a whole found), ROI > 0 shows half the time.

**This check can refute a lead; it can barely confirm one.** The verdicts are named accordingly.

## Decision lines — each lead separately, one look
| verdict | condition | consequence |
|---|---|---|
| **KILL** | holdout ROI ≤ 0 | the lead is dropped |
| **NOT REFUTED** | ROI > 0, date-clustered 95% CI includes 0 | still only a lead; the test that can settle it is forward data, which needs BetMGM in the line collector (its own amendment) |
| **CONFIRMED** | CI lower bound > 0 | the same, with a stronger case for adding BetMGM |
| inconclusive | n < 50 | no verdict |

Two leads are tested, so one passing by luck is more likely than for a single test. Nothing here
authorises money. The live collector reads FanDuel and DraftKings only, and betting a BetMGM price
would need a BetMGM account.

## Information only
P1 itself (EV ≥ 3%, all books) on the playoffs; by postseason; by book; over vs under; the
same-bets-at-average-price control; the consensus probability vs the realised hit rate.

## Playoffs are not the regular season
Rotations shorten, stars play more, markets get more attention, and the same teams meet up to seven
times. A lead that fails here might still hold in the regular season, and one that passes here might
not. This is the only untouched data in the history, not a perfect copy of the betting season.

## Data and its gates — all must pass before any grading
Box scores: `stats.nba.com/stats/leaguegamelog`, PlayerOrTeam=P, SeasonType `Playoffs` and `PlayIn`,
seasons 2022-23, 2023-24, 2024-25 → `nba_postseason.sqlite`, table `logs_post`, same columns as
`logs_full`.
1. **Same source, same shape**: the same fetch code pulls the 2024-25 *regular* season and must match
   `logs_full` on points, rebounds, assists, threes, steals, blocks and names for ≥ 99.5% of
   player-games, with row counts within 0.5%.
2. **Coverage**: on ≥ 95% of the 124 postseason odds nights, the box score holds the same number of
   games as the odds history.
3. **Name match**: ≥ 95% of the postseason lines with ≥ 3 books find their player in that night's box.

If any gate fails, nothing is graded and the failure is reported.
