# PRE-REGISTRATION — NBA tracking stats in the WNBA pricing model (real lines, at the close)

Written and committed **before any tracking data is fetched**. 2026-10-23.

## Why
The WNBA pricing machinery, run unchanged on NBA real lines (`NBA_PRICING_PREREG.md`), lost
−3.46% over 1,186 bets and was **overconfident by 10-17 points of probability**: it judges a
beneficiary by how often his own elevated-role games cleared the line, and 10-20 such games are a
noisy sample. A rebound or an assist is an opportunity *plus* a conversion; the conversion part is
mostly luck game to game. The NBA measures the opportunity directly — **rebound chances** and
**potential assists**, per game, back to 2022-23 (verified 2026-10-23). The WNBA has no such data.

## The single change under test — Arm S ("smoothed")
Arm T exactly as tested (`nba_pricing.price` → `wnba_tonight.prop_edges`, base rung,
`current_selection`, the four NBA departures), with ONE input change. In the beneficiary's game log
and in his with/without-X split, every game's
- `reb` is replaced by `reb_chances × p_reb(B)`,
- `ast` is replaced by `potential_ast × p_ast(B)`,
- combos (pra, pts_reb, pts_ast, reb_ast) are rebuilt from the replaced components; points, minutes
  and shot columns are untouched.

`p_reb(B)` / `p_ast(B)` = B's conversion (rebounds ÷ rebound chances; assists ÷ potential assists)
over his PRIOR games in the 400-day pool — strictly before the game date — shrunk toward the
league rate with **K = 40** pseudo-opportunities. The league rates are computed from the
**2022-23 season only**, which precedes every test date. Nothing else is fitted. A game with no
tracking row keeps its real value and is counted.

## Data
`stats.nba.com/stats/leaguedashptstats`, `PtMeasureType=Passing` and `=Rebounding`, one call per
game date with `DateFrom = DateTo` (verified: every row is one game, GP = 1), regular seasons
2022-23, 2023-24, 2024-25. **Integrity gate before any test runs**: the tracking feed's own AST and
REB must equal the box score's on ≥ 99% of joined player-games, or the data is treated as broken
and nothing is run.

## Universe, books, counting — identical to Arm T
WOWY tier (absence game 1-2, X ≥ 28 min trailing-10, B with ≥ 2 games without and ≥ 3 with),
FanDuel + DraftKings best price, base rung, overs, `current_selection`, flat 1 unit. Split for the
halves: 2024-10-29. Date-clustered bootstrap 95% CI (4,000 reps, seed 7).

## Decision lines — Arm S, pooled
| verdict | condition |
|---|---|
| **KILL** | pooled ROI ≤ 0, **or** halves disagree in sign, **or** Arm S does not beat Arm T's ROI in the same run |
| **B — informative** | pooled ROI > 0, both halves > 0, beats Arm T, CI lower bound ≤ 0 |
| **A — actionable** | the above with CI lower bound > 0 |
| thin | n < 100 → KILL for wiring |

Arm T is re-run in the same pass (it must reproduce −3.46% / n = 1,186, or the harness changed and
nothing is concluded). Must also beat the always-over null on the same candidates.

## Secondary — information only
Calibration of the model's stated probability against the realised hit rate, by EV band, Arm S vs
Arm T (the defect this is aimed at); per-stat ROI (the change only touches rebound/assist markets;
points-only bets are identical in both arms).

## What a pass would and would not mean
This is a test **at the close**, like every NBA test before it. A pass would justify a new shadow
tier (`priced_trk`) in the forward speed test via its own amendment — never a change to the
existing `priced` tier, whose forward record must stay what it was registered as. A pass does not
authorise money.

---

# RESULT — appended after the run, 2026-10-23. Nothing above this line was edited.

**Data:** 487 game dates, 147,417 rows, regular seasons 2022-23..2024-25. Integrity gate passed on all
three: tracked 99.2-100% of player-games; assists and rebounds agree with the box score 100% where both
exist; rows with no rebounding entry are 96-100% zero-rebound games (the feed omits players with no
rebound chances). League conversion, 2022-23: 0.575 rebounds per chance, 0.556 assists per potential
assist. Smoothed 831,727 prior rows; 43,340 kept real rebounds (no rebounding row); 5,388 had no
tracking row.

| | n | dates | hit% | ROI | 95% CI |
|---|---|---|---|---|---|
| Arm T (control — reproduced: n=1,186, −41.09u) | 1,186 | 286 | 50.0% | −3.46% | [−8.80, +1.99] |
| **Arm S, pooled** | **1,279** | 285 | 49.7% | **−4.71%** | [−9.66, +0.47] |
| before 2024-10-29 | 613 | 140 | 49.4% | −5.27% | |
| from 2024-10-29 | 666 | 145 | 50.0% | −4.20% | |

## Verdict: **KILL** — pooled ROI ≤ 0, both halves negative, and worse than Arm T.

**Calibration (the defect targeted) did not improve.** Arm S states 0.600 / 0.664 / 0.752 by EV band and
realises 0.493 / 0.473 / 0.557 — as overconfident as Arm T (0.597 / 0.656 / 0.745 vs 0.486 / 0.487 /
0.567). Replacing conversion luck with opportunity did not remove it, which locates the overconfidence
elsewhere: in the elevated-role sample regressing, not in the noise of the stat inputs.

**Correction to the registration's secondary note.** It said "points-only bets are identical in both
arms". The points *candidates* are; the points *bets* are not (395 vs 389), because `current_selection`
lets markets compete for each team-game's two slots and the points-vs-combo preference, so a changed
rebound or assist candidate can displace a points play. Per-stat results are therefore not clean
attributions. They are recorded, as registered, as information only:
points −4.80% → −7.32%, rebounds −8.12% → −3.60%, assists +6.81% → +0.95%, pts_ast +3.53% → +21.20%
(n = 50). None is a claim; the rebound improvement in particular is a post-hoc cut.

**Consequence:** no `priced_trk` tier. The tracking data stays (`nba_tracking.sqlite`), and is ready for a
differently-designed test if one is pre-registered.

---
**Note, 2026-10-28:** the VM's schedule for the current-season fetch (daily → hourly) and a completeness guard are
recorded in `NBA_SPEED_PREREG.md` amendment 34. Nothing above is changed.
