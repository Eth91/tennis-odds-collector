# Step 2a: pricing line value, then re-scoring candidates B and C

Read-only, on the Mac.

- **Pre-registered:** amendment 1 of `NBA_INJURY_REACTION_PREREG.md`, commit 3a2ddec3cb (2026-11-04 02:55 UTC),
  pushed before the conversion was fitted or any candidate was scored.
- **Code and guards:** `nba_injury_step2a.py` and `test_nba_injury_step2a.py` (12 mutants, all killed), committed
  before the run (15fdfeb0a5).
- **Audit files:** `audit/inj_step2a/` (every flag with its full CLV, plus the result JSON).

## Verdict
**Both candidates are dropped.** Neither has a positive mean CLV once the line value is priced.

| Candidate | Flags scored (dates, games) | Mean full CLV [95% game interval] | Null | Over the null | Survives? |
|---|---|---|---|---|---|
| **C:** DraftKings stale after FanDuel moved its line | 179 (9, 26) | **−5.4%** [−6.8, −4.1] | −6.4% | +1.0 pts | **no** |
| **B:** FanDuel points-type teammate overs, still stale | 564 (9, 28) | **−4.0%** [−5.7, −2.1] | −6.3% | +2.3 pts | **no** |

- Survival needed a mean above 0 **and** 3+ points over the null. Both fail the first test outright, and C fails both.
- For context, the null sits at about −6.4%, which is roughly the vig. B and C recover 1–2 points of it, nowhere near
  all of it.
- By the amendment, neither goes to a forward test, and no variant is re-scored on this backup.

## The conversion (what one line point is worth)
- **Model:** negative binomial, with the mean solved from each book's main line and no-vig over, and the dispersion
  varying with the mean.
- **Fit:** 2023-24 FanDuel and DraftKings main lines with outcomes.
- **Check:** 2024-25, which was held out.
- **Gate result:** every market passed. The predicted and realized one-point steps agree within 0.65 points, against
  a 1.5-point limit.

| Market | Step for 1 point below (predicted / realized) | 1 point above | 2 below | 2 above | Over rate, no-vig vs realized |
|---|---|---|---|---|---|
| Points | +6.4 / +6.7 | −6.1 / −6.1 | +13.1 / +13.2 | −11.8 / −12.1 | 49.9% / 49.4% |
| Rebounds | +16.4 / +16.6 | −14.9 / −14.8 | +31.2 / +31.7 | −26.7 / −26.3 | 49.5% / 47.9% |
| Assists | +18.7 / +18.6 | −16.7 / −17.3 | +34.9 / +34.9 | −29.4 / −29.6 | 49.4% / 49.1% |
| Threes | +28.3 / +28.1 | −22.7 / −22.4 | +47.4 / +47.6 | −36.4 / −36.1 | 48.4% / 47.6% |
| PRA | +4.7 / +5.1 | −4.5 / −4.9 | +9.4 / +9.9 | −8.9 / −9.8 | 50.0% / 49.9% |
| Points + rebounds | +5.2 / +5.4 | −5.1 / −5.4 | +10.6 / +11.0 | −9.9 / −10.3 | 50.0% / 49.5% |
| Points + assists | +5.4 / +5.6 | −5.2 / −5.9 | +10.8 / +11.0 | −10.2 / −11.0 | 50.0% / 50.3% |
| Rebounds + assists | +10.8 / +10.7 | −10.3 / −10.0 | +21.3 / +21.1 | −19.5 / −19.8 | 49.9% / 48.8% |

Steps are in points of probability.
- **Points-type lines:** one point is worth only about 5–6 points of probability. That's about the vig on a single
  bet.
- **Rebounds, assists and threes:** a point is worth 15–28.
- **Reported, not gated:** where the 2026-27 log has a rare second two-sided rung, the books price it 2–4 points
  flatter than the conversion. If the books' slope were right, line value would be worth even less. So that can only
  make B and C worse, not better.

## Why the window doesn't pay (diagnostic only; it can't revive either candidate)

| Candidate | Close line better for the bet | Same line | Close line worse |
|---|---|---|---|
| C | 51 bets, +1.2% | 104 bets, −6.0% | 24 bets, −16.6% |
| B | 179 bets, +3.8% | 295 bets, −5.3% | 90 bets, −15.4% |

- **When the line does move your way,** a one-point gain on a points-type line is worth about 5–6 points of
  probability. That only just beats the ~6% vig.
- **Most of the time** the line doesn't move (the vig is lost), and 13–16% of the time it moves the other way.
- **C restricted to DraftKings still a point behind FanDuel's new line** (131 bets) is −4.5%. With DraftKings
  already at FanDuel's line (50 bets) it's −7.5%.
- **Information only:**
  - B with no news before the report: −2.7% [−5.0, −0.2];
  - B with news first: −5.0%;
  - C on FanDuel price-only moves: −5.3%.

## What this means for the injury flagger rebuild
Step 1 showed the official report does move teammates' lines, spread over the first hour. Step 2a shows those moves
are too small and too uncertain to beat the vig:
- for a bet on the stale line at one book (B);
- for a bet on the slower book after the faster one moves (C).

That was the thesis of the rebuild, and on this data it doesn't hold. No candidate goes forward, and nothing live
changes.

## Limitations
- **In-sample, small.** 9 dates and 26–28 games. That's enough to rule these out: both intervals sit wholly below 0.
  It isn't enough to say nothing near them could work.
- **The conversion is fit to 2023-25 tip-time main lines.** It passed a held-out gate, but it values a line point the
  same at any time before tip.
- **DraftKings checks were 3–15 min apart.** A faster DraftKings feed would catch lags sooner. Its stale prices would
  still carry the same vig, and the line-better cases only made +1.2%.
