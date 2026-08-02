# PGA model — status, 2026-07-30

**v1.0 is FROZEN.** Constants `27bf0a242491c19d`, source `a8780c8de09971fd`.
Role is scientific validation, not development. No model change is adopted until the
pre-registered thresholds in `pga_validate.py` are met on prospective data.

---

## Where we got to

The model started this session flagging bets at **+13% to +19% EV against a 3–6% hold**. Those
edges were an artifact, and finding out why took the model apart.

**What was actually wrong** — the model is accurate on favourites and over-predicted longshots
about 5× (top-20 bottom decile: predicted .055, realised **.010**). Meanwhile the flag rule was an
*absolute* probability difference, which on a distribution with an inflated tail fires almost only
on longshots: 11 flags in the longest-odds quartile against 3 in the shortest. It structurally
excluded favourites — the one region where this model works.

Neither headline metric could see it. **Ordering accuracy is a rank metric, exactly invariant to
monotone compression**, and **RMSE is minimised by shrinking toward the mean**, so "RMSE at the
noise floor" is consistent with over-shrinkage rather than evidence against it.

**Five fixes, each measured before shipping:**

| fix | basis |
|---|---|
| Tail recalibration, `SHAPE_SLOPE = 1.30` | bootstrap CI **[-0.0105, -0.0030]** excludes zero; reliability slope **1.282 → 1.043** |
| Relative ratio gate `[1.15, 2.0]` | inside 2× the model is accurate (1.06×); beyond it, over by 2.08–2.48× |
| Convex log-odds blend `BLEND_W = 0.40` | convex so `ours == fair` returns fair exactly — agreement can never manufacture edge |
| Priced-subset devig `N_eff` | TOP_20 priced 102 of 147, holding 17.07 of 20 slots — fair was inflated 17%, ratios read 15% low |
| Explicit EV floor `EV_MIN = 0.03` | `EV = (p_bet/fair)/vig − 1`; vig is 21–29%, so a 1.15 ratio floor admitted guaranteed losers |

**Result on the live board:** flags **67 → 4**, mean EV **+177.5% → +4.6%**, worst flag
**+811.7% → +5.7%**. Flag rate **27.7% → 1.0%**, finally consistent with a competent book's
pricing error (~0.9%) where 27.7% was impossible. Compression slope **.354 → .799**, and the
odds-quartile distribution *inverted* — flags now sit with favourites.

---

## The honest limits

- **`BLEND_W = 0.40` is unidentified.** Bootstrap CI spans **[0.00, 1.00]**. It was derived from a
  regression whose market predictor was an outright close (mean .009) scored against a top-20
  outcome (base rate .164) — an 18× scale mismatch. Not fixable without historical top-N prices,
  which do not exist (Odds API `h2h` → 422).
- **On the only scale-matched test the model is a coin flip** vs the market: it wins 52% of
  event-bootstraps, CI spans zero.
- **~1,900 settled bets** would be needed to separate +9% EV from zero at these odds. That is why
  validation runs on a **sequential likelihood-ratio test**, not ROI.

---

## Validation regime (pre-registered at n=0, changing it restarts the record)

Wald SPRT on the paired per-bet log-likelihood ratio. H0: outcomes at the devigged market rate.
H1: at the model rate. Boundaries **+2.773 / −1.558** (α .05, β .20) — asymmetric on purpose:
~2.8 nats to believe the edge, ~1.6 to abandon it. Synthetic self-test decides in a median **218
bets** when the model is right, **45** when it is 2× biased.

Halts: H-1 lower boundary · H-2 slope < 0.70 over 200 · H-3 n≥100 with ROI CI upper < 0 ·
H-4 data integrity. Adoption: a challenger must win a **paired** SPRT over ≥100 prospective
settled bets. Retrospective improvement counts for zero.

**Capture rule:** the bet set is the flags from the last snapshot strictly *before* first R1 tee.
Necessary because these lines move violently — Knapp over 2.5 went 1.72 → 2.42 (+40%) inside 2.5
hours.

---

## Current record

| | |
|---|---|
| Ledger | 6 rows, **0 settled**, all `-shadow` |
| G2 arming gate | n=1 of 15 |
| v1.0-eligible bets this event | **zero** — collection began 9.5h after first tee, so the capture window has no data |

Rocket Classic will not contribute to the v1.0 record whatever happens. Its value is proving the
machinery settles correctly. **The record starts next tournament.**

---

## Streams

| stream | state | vig | evidence |
|---|---|---|---|
| top-N | armed | 21–29% | slope 1.043 on 986 majors runners |
| matchups | armed | 5.8% | none — G2 n=1 |
| birdies | armed | 6.0% | reliability slope 1.06, leak-free |
| make-the-cut | **armed** | ~6% | none — structural argument only |
| round-score O/U | shadow | 6.0% | σ right to 0.4%; **slope 0.050 on n=12** |
| outrights | **off** | 44% | proven negative: −85.6% ROI on 528 bets |

**Best structural fit is a two-way market**, not top-N: break-even ratio 1.06× vs 1.22–1.29×. A
small edge dies against a 25% overround and survives a 6% one.

---

## Next

1. **Run `bash pga_after_event.sh`** when R1 finishes (~1.7h out), and again Sunday. Settles 3
   birdie bets tonight, matchups and top-10 Sunday.
2. **Let the record accumulate from the next tournament**, where the capture window is intact.
3. **Do not wire live top-N between rounds yet.** Tail recalibration is deliberately skipped
   in-play, so it would run on raw probabilities — back into the longshot inflation
   `SHAPE_SLOPE` exists to fix. Whether 1.30 is right, wrong or unnecessary once a real round
   conditions the distribution is unmeasured. Measuring it means simulating as-of after R1/R2/R3
   across past events against realised finishes.
4. **Highest-value open task:** forward-collect top-N prices with outcomes. ~200 settled top-N
   bets would let `BLEND_W` be fitted against the actual market instead of an 18×-mismatched
   proxy. Paper trading generates this at zero cost.
5. **Round-score stays shadow** and accumulates. Early read is discouraging — the book prices at a
   granularity (0.5–1.4 strokes) finer than the model's per-round σ of 2.79.
