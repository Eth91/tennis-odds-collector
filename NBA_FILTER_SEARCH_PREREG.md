# PRE-REGISTRATION — a basketball-informed filter search for NBA beneficiary overs

Written and committed **before any feature is built or any outcome is examined.** 2026-10-23.

## Why, and the trap this is built to avoid
Every NBA test so far lost at the close. The decisive measurement (2026-10-23): on the bets the WNBA
pricing model selects, its projection was **12.61**, the book's line **10.30**, the result **10.57** —
and the player's own season average **10.51**. The role bump the model bets on does not show up in
outcomes, and the book is within a quarter-point of the truth. Whatever edge exists must come from
*which* spots to take, not from a better projection of the bump.

The user's ask: an ROI-maximising set of selection criteria — "Excel Solver on a whole new level" —
built from how basketball works. The trap: searching many filter combinations over two seasons will
always find one with a large ROI, even in pure noise. So this registration fixes the **procedure**,
not a result, and includes a benchmark that measures exactly how large a "best filter" noise produces.

## Universe — every candidate over, not just the model's picks
WOWY-tier beneficiaries (absence game 1-2, X ≥ 28 min trailing-10, B with ≥ 2 games without X and
≥ 3 with), every stat FanDuel/DraftKings posted two-sided for B that night (points, rebounds,
assists, pra, pts_reb, pts_ast, reb_ast), the main rung (nearest even money), the best over price of
the two books, graded on the box score. Regular seasons 2023-24 and 2024-25 (the real-line history).

## Time blocks — fixed now
| block | dates | use |
|---|---|---|
| **TRAIN** | 2023-24 regular season | factor research and the search |
| **VALIDATE** | 2024-10-22 → 2025-01-31 | rank the search's survivors |
| **HOLDOUT** | 2025-02-01 → 2025-04-13 | **one look**, at the single final rule set |

## The basketball factors — each with its mechanism and the direction expected *before* measuring
All are known before tip; anything "season-to-date" uses only games strictly before the bet's date.

**1. The opponent's defense** (season-to-date, from the box scores of every game)
- *Pace* (possessions per game, both teams) — more possessions, more counting stats. **Expect: high pace → overs better.**
- *Points/rebounds/assists allowed per 100 possessions* to all, and **to B's position** (defense vs
  position). **Expect: soft defense → overs better** — while noting the WNBA found this real but too
  small to bet; a search that only rediscovers it should fail the noise benchmark.
- *Rim protection* (opponent blocks per game) — a rim-protecting defense suppresses drivers and
  bigs' scoring. **Expect: high blocks → points overs worse for rim-heavy scorers.**
- *Three-point and free-throw volume allowed* (opp 3PA rate, FTA rate) — defenses that concede
  threes or fouls feed spot-up shooters and slashers respectively.
- *Defensive rebounding allowed* (opp OREB rate) — offensive-rebound chances for bigs.

**2. How B scores** (prior-season profile — no look-ahead; from shot zones and play types)
- Shot zones: share of shots at the rim, in the paint, mid-range, corner three, above-break three.
- Play types: pick-and-roll ball handler, isolation, spot-up, roll man, post-up, transition, cuts.
- Box-score rates: three-point attempt rate (3PA/FGA), free-throw rate (FTA/FGA), usage share.

**3. Who the absent player was** (X) — what his absence vacates
- X's shot share and assist share of his team, X's position vs B's (`position_compat`), X's minutes.
  **Expect: overs better when X's role overlaps B's** (a guard's shots go to guards).

**4. Matchup interactions — B's style against the defense's weakness**
- B's rim share × opponent rim protection; B's three-point rate × threes allowed; B's free-throw rate ×
  fouls allowed; pick-and-roll handlers × assists allowed. **Expect: style-vs-weakness → better.**

**5. The usage bump vs the defense**
- B's with/without-X change in minutes and shots (`d_min`, `d_fga`) against the opponent's defensive
  rating. **Expect: a real usage bump into a soft defense is the best spot; a bump into an elite
  defense regresses.**

**6. Game context**
- Rest days and back-to-backs for both teams; home/away; the team-strength gap (season net rating)
  as blowout risk — starters sit in blowouts. **Expect: rested, competitive games → overs better.**

**7. The line itself** — what the book already knows
- Line vs B's season-to-date average and vs his last-10 average (did the book move the line for the
  absence?); the over price; the model's projection minus the line. **Expect: a line still near B's
  season average while his role grows = the stale-line spot — the only factor tied to the timing edge.**

## The search ("Solver") — fixed now
- **Rules**: conjunctions of 1 to 3 conditions. A condition = one factor in its lowest or highest
  third, cut points computed on TRAIN only. Each factor is used in its pre-stated direction OR its
  opposite — both are searched and both count toward the number of rules tried.
- **Objective on TRAIN**: total units, requiring n ≥ 150 bets on ≥ 40 dates.
- **THE NOISE BENCHMARK**: shuffle the outcomes among the bets of each date (keeping each date's mix
  of stats and prices), re-run the identical search, record the best objective; repeat 100 times. A
  real rule must beat the **95th percentile** of those 100 noise-best values. If none does, the
  verdict is KILL with no further looks.
- **VALIDATE**: the top 20 TRAIN rules that beat the benchmark are scored once on VALIDATE; survivors
  must be > 0 ROI there.
- **The final rule set**: the single best VALIDATE survivor, or the union of the top three, chosen by
  the rule above — no other choices.
- **HOLDOUT**: that set, scored once.

## Decision lines — on the HOLDOUT
| verdict | condition | consequence |
|---|---|---|
| **KILL** | no rule beats the noise benchmark, or the final set's HOLDOUT ROI ≤ 0 | nothing ships |
| **B** | HOLDOUT ROI > 0, date-clustered 95% CI includes 0 | a forward shadow tier (its own amendment) |
| **A** | HOLDOUT CI lower bound > 0 | forward shadow tier, eligible for paper bets by its own amendment |

Every number is at the close. No result here authorises money.

## Data, stated now
From data already held: box scores (`logs_full`) → pace, allowed-per-100, position splits, blocks,
3PA/FTA allowed, rest, home/away, net rating; positions; WOWY splits. To fetch (prior seasons only,
2022-23 and 2023-24): player shot zones, player play-type frequencies, team opponent shot-zone defense.
Real lines: `basketball_nba_odds_hist.sqlite`, FanDuel + DraftKings.

## Disclosed before running
The HOLDOUT months were part of earlier tests' *overall* results (the margin refit, cold-start and
pricing tests reported pooled ROI over 2023-25, including a 2024-10-29+ half). None of those examined
any factor above, so the HOLDOUT is fresh **for this question** — but it is not virgin data, and a
pass here is weaker evidence than a pass on games no test has touched. The forward shadow record
(2026-27) is the only fully clean test; any rule that passes here must also face it.
