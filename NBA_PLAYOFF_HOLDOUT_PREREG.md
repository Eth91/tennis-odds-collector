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

---

# RESULT — appended after the run, 2026-10-23. Nothing above this line was edited.

**Gates — all passed.** (1) The same fetch code re-pulled the 2024-25 regular season: 26,306 rows,
identical to `logs_full` on all 26,306. (2) All 124 postseason nights hold the same number of games as
the odds history. (3) 2,957 of 2,988 lines' players were found in that night's box (99.0%).

| | n | dates | hit% | ROI | 95% CI | claimed EV | consensus p vs realised |
|---|---|---|---|---|---|---|---|
| **Lead 1 — BetMGM is the outlier** | 104 | 55 | 45.2% | **−1.47%** | [−25.5, +23.1] | +5.84% | 0.477 vs 0.452 |
| **Lead 2 — EV ≥ 6%** | 107 | 63 | 33.6% | **+1.50%** | [−29.3, +35.8] | +9.13% | 0.426 vs 0.336 |

## Verdicts
- **Lead 1: KILL** — holdout ROI ≤ 0. Dropped.
- **Lead 2: NOT REFUTED** by the registered rule (ROI > 0, CI includes 0). The registered rule is
  the verdict. But the detail leans against the lead: the +1.50% comes entirely from 16 bets in the 2023
  postseason (+131%). The 2024 postseason lost 24.9% (n=53) and the 2025 postseason lost 16.3% (n=38).
  The bets hit 33.6% against a consensus 42.6%, overconfident by 9 points. Big disagreements are where
  the disagreeing book was most often right.

## Information only (pre-stated above; no claims)
**P1 itself, all books, EV ≥ 3%, on the playoffs: n = 671, +9.87%, CI [+1.01, +20.17]**, and positive in
each postseason: 2023 +45.8% (n=87), 2024 +5.1% (n=399), 2025 +3.3% (n=185). Here the consensus
*under*-stated the bets (0.459 vs 0.471 realised), the reverse of the regular season (0.485 vs 0.465).
The same bets at the other books' average price: −1.76%. By book: FanDuel +9.4%, DraftKings +15.2%,
Caesars +9.7%, BetMGM −1.5%. Unders +14.7%, overs +6.6%.

This is the one strong number in the run, and it is **not a verdict**. P1 was registered on the
regular season and KILLed there (+0.56%, the seasons split). The playoff figure was named only as
information. Over half its units (+39.8 of +66.2) come from the 2023 postseason's 87 bets on 25
nights; without them it is +4.5% (n=584). It is a hypothesis: **at the close, books may disagree
more usefully in the playoffs than in the regular season.** That would need forward data from at
least three books in the 2027 playoffs to test.

**What this settles.** The BetMGM lead was an artifact of cutting the regular-season data. It is
gone. The large-edge lead survives only on the letter of the rule. Price alone remains no edge in the
NBA regular season at the close.
