# PRE-REGISTRATION — NBA cold-start tier on REAL lines

Written and committed **before** the test script exists or has run. 2026-10-22.

## Why this test
The cold-start tier (no WOWY prior → proportional minutes redistribution) was validated on
2026-07-16 at **63.7% (margin 5-8) / 67.8% (8+) on 1,345 flags** — against the *proxy* line
(the player's own trailing median). The same proxy produced the WOWY tier's 66.8%, which on
real lines today came out at a −1.96% to −2.58% centre with every CI crossing zero. The proxy is
not evidence. This test re-measures cold-start on real lines before it is allowed near a ledger.

## The rule under test — fixed, nothing fitted
Every parameter below was set in July without real lines. **Nothing is tuned in this test.**

- **X (the absence):** prior-active player (≥5 apps in the 400-day pool, last app ≤12 days ago),
  trailing-10 avg ≥ 28.0 min, not in tonight's box; the highest-minutes such player per
  team-game; absence game 1 or 2 only.
- **Rotation R:** prior-active teammates (same activity test) with trailing-10 avg minutes in
  **[12, 32]**, excluding X. Defined from PRIOR games only — tonight's box is not used to build it.
- **B (the beneficiary):** in R, appears in tonight's box (props void on a DNP), and has
  **fewer than 2** prior games with X absent — i.e. no WOWY prior. Disjoint from the WOWY tier
  by construction.
- **Projection:** `proj_min = base_min_B + vacated_X × base_min_B / Σ_R base_min`,
  `vacated_X` = X's trailing-10 avg minutes; `proj_stat = rate_B × proj_min`, `rate_B` = B's
  per-minute rate over prior games in the current season (season = Aug-Jul), falling back to the
  400-day pool if fewer than 5 current-season games.
- **Real line:** the over rung nearest even money per (date, player, stat), best over price
  across the four books — identical to `nba_margin_refit.load_real_lines`.
- **Bet:** OVER when `proj − line ≥ 5.0`.

## Primary cells (the verdict is decided ONLY on these)
- **PTS, margin ≥ 5.0**
- **PRA, margin ≥ 5.0**

Secondary, reported but NOT decisive: REB ≥ 2.0; a margin sweep; the always-over null on the
same cold-start universe.

## Statistics
- ROI per unit staked at the recorded best over price; units, hit%, n, distinct dates.
- 95% CI by **date-clustered bootstrap** (resample dates with replacement), 4,000 reps, seed 7.
- Replication halves split at **2024-10-29** (the date `nba_margin_refit` used). Nothing is fit
  on either half; the halves exist only to check the sign replicates.

## Decision lines — per primary cell
| verdict | condition | consequence |
|---|---|---|
| **KILL** | pooled ROI ≤ 0, **or** the two halves disagree in sign | cold-start flags are **shadow-only**, never written to `bet_ledger` |
| **B — informative** | pooled ROI > 0, both halves > 0, but CI lower bound ≤ 0 | **shadow-only**; accrue forward paper, re-decide at ≥300 forward flags |
| **A — actionable to paper** | CI lower bound > 0 | may write PAPER bets to `bet_ledger`, tier-tagged `cold` |

No result in this test can authorize real money. A cell needs n ≥ 100 to be judged at all;
below that it is reported as **thin** and treated as KILL for wiring purposes.

## Known limits, stated now
- Grades only players who played (`reference_dnp_pricing_confound`): void-on-DNP makes this
  roughly right for props, but it is not exact.
- Real lines are **tip snapshots only** — this measures price at close, not the news window.
- Absence is inferred from the box score; live uses the injury report. Live should be at least as
  early, so this is a conservative proxy for timing but not for selection.

---

# RESULT — appended after the run, 2026-10-22. Nothing above this line was edited.

`nba_coldstart_realline.py`: 10,242 cold-start candidate stat-rows, **3,088 with a real line**.

| cell | n | dates | hit% | ROI | 95% CI | halves | **verdict** |
|---|---|---|---|---|---|---|---|
| **PTS ≥ 5** | 33 | 29 | 54.5% | +5.82% | [−27.39, +38.68] | +29.72% / −22.87% | **THIN → KILL** |
| **PRA ≥ 5** | 137 | 89 | 48.2% | **−8.61%** | [−24.81, +7.47] | −0.46% / −18.19% | **KILL** |
| reb ≥ 2 *(secondary)* | 82 | 66 | 47.6% | −8.01% | [−30.15, +13.62] | −5.80% / −10.70% | thin |

Null on the same cold-start universe: always-over pts **−9.37%** [−15.09, −3.98], pra −9.17%,
reb −8.62% — a WORSE population than the league-wide null (−6.56%). The PRA cell (−8.61%) sits on
its null: the selection adds nothing measurable.

**Consequence, as pre-registered: cold-start flags are shadow-only.** `nba_flags.LIVE_TIERS` is
empty; flags go to `nba_shadow.sqlite`, graded by `nba_flags.py --grade`.

### Implementation check (so the kill is about the rule, not a bug)
Mean projection vs outcome on the 3,088 rows: pts 11.93 vs 11.30 (+0.62), reb 5.19 vs 4.84,
pra 20.13 vs 18.93 (+1.19) — sane magnitudes, mildly optimistic, the same direction the WNBA's
k=11 shrink exists to correct. **The book's line is nearly unbiased** (line − actual: pts −0.08,
pra +0.12). The market prices these spots better than the projection does.

### Hypothesis for a FUTURE pre-registration — NOT tested, NOT validated
The largest "edges" are backup centres inheriting a guard or wing's minutes (Drummond proj 30.4 PRA
vs line 14.5 with Patrick Williams out; actual 18). Proportional redistribution is position-blind;
real rotations redistribute within position, and the book knows it. This was noticed by LOOKING at
these rows, so it cannot be validated on them — it needs a fresh prereg and forward shadow data.
