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

---

# AMENDMENT 1: the two model changes (written after the diagnosis, before either was fit or run)

**What the diagnosis found** (`NBA_FLAGS_WINLOSS.md`):
- **Across all ~48k backtest candidates, the projection is unbiased:** minutes 1.01× projected, rate 1.00×.
- **The plays it flags (excess ≥ 1) are overprojected by about 2.5 units in both seasons.**
  - Minutes come in at 0.91× projected and rate at 0.88×.
  - More than half the losses are B playing 4+ minutes fewer than projected.
- **Live is the same** (81 plays): overprojected by 2.4 units, minutes 0.92×, 64% of losses 4+ minutes short.

The high projections we act on are partly noise (winner's curse). On minutes, part of it is plausibly what
the market knows and a last-10 average misses: a role that has changed in the last few games.

**Change R (rate): more shrinkage.**
- `rate = (stat in games without X + base_rate × K) / (minutes without X + K)`, with K raised from 60
  pseudo-minutes.
- K is chosen from {60, 120, 240, 480, 960, 1920} on **2023-24 only, over all candidates**. The choice
  minimizes the mean over stats of MSE(actual, rate × actual minutes) relative to K = 60.
- No line, price or result enters the fit.

**Change M (minutes): recency.**
- `proj_min = a + b × last-10 minutes + c × last-3 minutes + k × d_min` (d_min shrunk as now).
- Fit by least squares on **2023-24 only, over all candidates** (one row per date, B, X), against B's
  actual minutes.

**The test** (the card at tip lines, FanDuel + DraftKings prices):
- **The card's rules:** minutes band 3–8, fewer than 2 stars out, absent star < 32 min, price ≥ 1.80,
  excess 1–2, rebounds included, 1 per player (singles first), 2 per team-game.
- Margins unchanged (pts 5, reb 1, PRA 6.5).
- Built with the current projection, with R, with M, and with R + M.

**Decision:**
- A change is adopted only if its card units are ≥ the current card's units in **both** 2023-24 and
  2024-25.
- If R and M both pass, R + M is adopted only if it also passes. Otherwise the one with more total units
  is adopted.
- If neither passes, the projection is unchanged.
- An adopted change goes live only through a new NBA_SPEED_PREREG amendment, with a forward automatic
  revert.

**Amendment 1: run (2026-10-27).**
- **Fit (2023-24):** R picked K = 240. M fitted proj_min = 6.54 + 0.391 × last-10 + 0.396 × last-3 +
  0.164 × d_min.
- **Card units, 2023-24 / 2024-25:**
  - current +26.12 / +9.25;
  - R +12.95 / +5.37;
  - M +10.45 / −0.71;
  - R + M +9.48 / +7.36.
- **Decision as registered:** neither passes, so the projection is unchanged (`nba_flags_model_test.py`).
