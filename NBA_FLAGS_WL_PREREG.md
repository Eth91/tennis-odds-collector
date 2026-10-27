# PRE-REGISTRATION: why the flags win and lose, then one model test

Written 2026-10-27, before any of the splits below were run. User: "find out why we're winning and why we're
losing and then make the model better."

## The model being diagnosed
A wowy flag projects player B with teammate X out:
- `proj = rate × (base_min + 0.98 + 0.356 × d_min)`;
- `base_min`: B's last-10 minutes;
- `d_min`: B's minutes with X out minus with X in, shrunk;
- `rate`: B's per-minute production in games without X, shrunk toward his last-10 rate (60 pseudo-minutes).

It flags the over when `proj − line ≥ margin` (pts 5, reb 1, PRA 6.5).

Every result therefore splits exactly into two parts, **minutes** (actual vs projected) and **rate** (actual per
minute vs projected per minute): `log(actual / proj) = log(min / proj_min) + log(rate / proj_rate)`.

## Data
1. **Live:** every graded shadow flag, 2026-10-22 onward. One opportunity per (date, player, stat, tier), its
   earliest flag, graded at the flagged line and price. Small (about 110): description only.
2. **Backtest:** every wowy candidate at the archive's tip lines, 2023-24 and 2024-25 (`vol4_rows`: same
   formulas, every absent star ≥ 24 min, absence games 1–4, FanDuel + DraftKings prices), joined to B's
   actual minutes. The card's universe:
   - minutes band 3–8;
   - fewer than 2 absent stars;
   - absent star under 32 min;
   - price ≥ 1.80;
   - excess 1–2;
   - rebounds included (amendment 32).

   Also the wider pool, excess ≥ 1.

## Measures (both data sets)
- **Record:** W-L, units and ROI. By stat, tier, excess band, price band, absent star's minutes, absence
  game, minutes band, and news latency (live only).
- **Accuracy:** mean (actual − proj) and mean (actual − line), and whether |proj − actual| beats
  |line − actual|.
- **The split:** for wins and for losses separately, the mean minutes term and the mean rate term. Plus
  the share of losses where B played ≥ 4 minutes fewer than projected.
- **Selection bias:** realized rate ÷ projected rate, for flagged plays against all candidates. A
  projection picked because it is high should come in low (winner's curse).
- **The line:** CLV (FanDuel's closing main line minus the flagged line), live only.

## What counts as a finding
A pattern counts only if it has the same sign in **both** backtest seasons and does not contradict the live
data. Everything else is reported as noise.

## Then: one model test, registered before it runs
After the diagnosis, at most **two** model changes, each aimed at a mechanism found above. They are written
into this file as an amendment **before** they are run. Each is tested on the card at tip lines, built once
with the current projection and once with the change.

**Adopt only if** the change's card units are ≥ the current card's units in **both** 2023-24 and 2024-25.

**Honest limit.** Both seasons have been looked at before: amendments 23, 27, 28 and 30 used them. So a
pass is weak evidence, and an adopted change is judged forward with its own automatic revert.
