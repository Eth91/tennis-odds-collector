# Projection engine audit (2026-10-27)

Two parts:
- an independent code review: a separate reviewer, read-only, not shown my conclusions;
- an empirical audit, `nba_proj_audit.py` (development after exposure on 2023-24 and 2024-25; nothing
  tuned).

The sportsbook-pricing research is in `/Users/ethandown/dev/reports/NBA player prop pricing.md`.

## Bottom line
- No future data reaches any prediction. The probability, de-vig, blend and CLV math is correct.
- **One live defect matters now.** proj-1.1's "regulars out" input is defined differently live than in
  training (C1), and the prospective test began on 2026-10-27 with it. It is fixed as a new version
  (`proj-1.1.1`) before the first full slate.
- **The prospective grader had biases, all fixed before any grade existed** (0 graded as of the fix):
  - it dropped props whose line moved, favouring the model (C2);
  - CLV covered unmoved lines only (C4);
  - DraftKings rows leaked into the FanDuel decision lines (C5);
  - postponed games could be mis-graded (C6);
  - bootstrap clusters used the UTC date (C7).
- **Empirically the engine adds about no information beyond FanDuel's line** (E1, E2). FanDuel's own
  line has a small over lean (E4), and the other three books are not better than FanDuel (E5).

## Code review findings
| # | severity | where | finding | status |
|---|---|---|---|---|
| C1 | medium | `nba_proj11_feat.py` f0_features vs `nba_proj11_live.py` live_inputs | **"Regulars out" is defined differently in training and live.** Training: any regular missing from the box score, with regulars carried across seasons, so departed and traded players count as out (59%, 57% and 62% of October "out" events in 2023-24, 2024-25 and 2025-26). Live: only Out/Doubtful on the report, or Inactive in the lineup file. These inputs carry essentially all of proj-1.1's gain. | fixed in proj-1.1.1: regulars from current-season games on the current team, the same rule in both places |
| C2 | medium | `nba_proj_eval.py` prospective | The close was looked up only at the cutoff forecast's line. 12.5% of 2026-27 props (replay) lack that line at the close (main moved or pulled), and the move agreed with the outcome 56% of the time. Dropping them biases "beats the close" toward the model. | fixed: the forecast's pmf is logged, and props whose line moved are graded at the close's main line; exclusions are counted |
| C3 | medium (errs NO) | `nba_proj_eval.py` verdicts | The PIT rule "every decile in 10–12%" can only pass with an exactly uniform histogram (already noted post hoc in PROJECTION_RESULTS.md). | unchanged: it is proj-1.0's pre-registered rule and stays NO as written |
| C4 | low | prospective CLV | CLV only when the line never moved (24% of props excluded), and it could mix books. | fixed: same book; when the line moved, CLV is computed at the close's main line from the pmf |
| C5 | low | logging / grading | When FanDuel has no main line, logging falls back to DraftKings (2.2%), and those rows entered the FanDuel decision lines. | fixed: decision lines use FanDuel only; DraftKings rows are reported apart |
| C6 | low | prospective tips | One tip per game id (whichever row came last). A postponed game's stale forecast could be graded against the rescheduled game. | fixed: each record uses its own tip; void if the tip's ET date is not the game's date |
| C7 | low | bootstrap clusters | Clustered by the UTC date, so late games joined the next night. | fixed: ET date |
| C8 | low | `nba_proj11_live.refresh11` | Debuting players got group "F" (no position index), unlike proj-1.0. | fixed: positions passed through |
| C9 | low | `nba_proj_data.py` | Sub-30-second appearances round to 0 minutes before 2026-27 and are treated as DNPs (76–118 rows a season). | documented (frozen data) |
| C10 | low | historical odds | 1.3% of FanDuel snapshots are later than −29 min. | documented: the frozen proj-1.0 results are not re-run |
| C11 | low | 2026-27 replay | A pulled market keeps its old price as the "close". | documented (replay only) |
| C12 | low | proj-1.1 verdict text | Said "first 2,000 pass" when the reliability check failed. | fixed |
| C13 | low | grader speed | Box-score lookup scanned every row for every key. | fixed (set lookup) |
| C14 | low | B1 baseline | Pools this season with last season under 5 games; the prereg says last season. | documented (frozen) |

**Checked and correct:**
- `walk` is point in time, and traded players' rates follow them.
- The analog pool is strictly earlier.
- Half and whole lines, pushes, and combos within draws are right.
- De-vig, blend and the CLV sign are right.
- The close is the board strictly before tip.
- Odds `game_date` is the ET date, and name matching has no collisions.
- Box rows are clean, and injury-report and lineup timestamps are UTC with offsets.
- The residual layer refits monthly on earlier rows.
- Holm and the clustered bootstrap are right.

## Empirical findings (FanDuel lines, pushes excluded)
- **E1. Disagreements with FanDuel carry about no information.**
  - proj-1.0: when the model's P(over) is 15+ points above FanDuel's no-vig price, the over hits 49.4%
    (2023-24) and 48.7% (2024-25), against FanDuel's 49.6% and 49.3%. When it is 15+ points below, the
    over hits 46.2% and 49.1%, against FanDuel's 50%.
  - proj-1.1's strong under calls carry a little: 44.9% (2023-24) and 46.6% (2024-25), against FanDuel's
    50%. That is about the size of the vig.
- **E2. Model + line vs the line alone.** A logistic regression on logit(FanDuel) and logit(model),
  fitted on 2023-24 and scored on 2024-25, does no better than FanDuel alone: +0.0004 (proj-1.0) and
  +0.0002 (proj-1.1) log loss, intervals spanning 0.
- **E3. Mean calibration by projection quintile (actual − projected mean).**
  - proj-1.0 under-projects its bottom fifth (points +0.86, PRA +1.58 in 2024-25). Books post props for
    bench players mostly when their role grows.
  - proj-1.1 fixes the bottom but **over-projects its top fifth**: points −0.78 and PRA −1.60 (2024-25);
    points −1.74 and PRA −2.61 (2023-24). The residual layer overshoots big role bumps.
- **E4. FanDuel leans over.** Its no-vig P(over) exceeds the realized over rate by +1.7 points
  [+1.1, +2.4] (2023-24) and +0.6 [+0.0, +1.2] (2024-25), most in PRA, P+R, steals and threes. This is
  smaller than the vig: about 3.5 points a side at −115/−115.
- **E5. Other books are not better.** The de-vigged average of DraftKings, BetMGM and Caesars at the same
  line and moment scores +0.0002 and +0.0003 log loss worse than FanDuel. Where they disagree by 3–6
  points, the realized rate is usually nearer FanDuel.
- **E6. Minutes are the gap** (`NBA_STATS_FEASIBILITY.md`). The deficit to the close doubles when a
  regular teammate is out. With actual minutes, the same model beats the close by about 0.055 (an upper
  bound).
- **E7. Lineups at the cutoff** (NBA.com daily lineups file, 14 team-games on 2026-10-26):
  - 13 of 14 were "Expected", not Confirmed, at tip − 30;
  - all 5 expected starters were right in 13 of 14;
  - lineups were confirmed 20–26 min before tip.

## What follows (the improvement loop)
1. **proj-1.1.1:** F0 with one definition of "regulars out" in training and live (C1), re-run once on
   the development seasons, and replace the proj-1.1-dev logger.
2. **Grader fixes C2 and C4–C7, C12, C13:** for both versions, before any grade exists.
3. **proj-1.2 candidates:** pre-registered separately, informed by E1–E7 and the pricing research.
