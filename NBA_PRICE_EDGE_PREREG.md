# PRE-REGISTRATION — is there an edge in PRICE alone? (NBA player props, real lines, 4 books)

Written and committed **before any outcome is examined.** 2026-10-23.

## Why
Every NBA selection test lost at the close (margin rule, cold-start, WNBA pricing Arm T −3.46%,
tracking Arm S −4.71%, filter search HOLDOUT −3.43%). The WNBA record says about half its edge was
timing (it beat the close 67%). What is left to test without forward data is **price**: does a book
that disagrees with the others offer a bet worth taking, and how much does shopping add to the
strategies already tested? This test needs no model of the player at all.

## Data, inspected before writing (no outcomes)
`basketball_nba_odds_hist.sqlite`, table `props`: 2,017,885 rows, books FanDuel, DraftKings, BetMGM,
Caesars (`williamhill_us`), 10 markets (points, rebounds, assists, threes, steals, blocks, pra,
pts_reb, pts_ast, reb_ast). **One snapshot per game, all four books at the same timestamp, ~29 min
before the scheduled tip** (median −29.4 min). Each book posts **one line** per player-stat (90
exceptions in 1.0M). Every line is a half point — no pushes. 189,281 player-stat-lines have three or
four books two-sided at the exact same number. Box scores (`logs_full`) cover regular seasons only,
so the graded universe is **2023-24 and 2024-25 regular seasons**; playoff lines are not graded.

## P1 — the primary test: bet the book that disagrees with the other books
For every (date, player, stat, line) in the snapshot:
1. Keep books quoting **both** sides at that exact line. Drop snapshots taken after the scheduled
   tip (in-play). Require **≥ 3 such books**.
2. For each book *b*: the reference is the **other** books at that line (leave-one-out — *b*'s own
   price never enters its own reference). Each reference book's over probability is de-vigged
   proportionally: `p = (1/over) / (1/over + 1/under)`. The fair over probability is their mean.
3. `EV(b, side) = p_fair(side) × price(b, side) − 1`, for over and under.
4. Take the single book-side with the highest EV. **Bet it if EV ≥ 3%.** At most one bet per
   (date, player, stat, line); with four books at most one line can have ≥ 3 books, so at most one
   bet per player-stat-night.
5. Graded on the box score: over wins if the stat > line, under if < line. A player not in that
   night's box score did not play → the bet is void (excluded). Names matched with
   `nba_margin_refit.norm`; a (date, name) that maps to two players is dropped as ambiguous.
   Flat 1 unit at the offered decimal price.

**Decision lines — P1 pooled, EV ≥ 3%.** Halves = the two seasons (2023-24 / 2024-25).
Date-clustered bootstrap 95% CI, 4,000 reps, seed 7.

| verdict | condition |
|---|---|
| **KILL** | pooled ROI ≤ 0, **or** the two seasons disagree in sign |
| **B — informative** | pooled ROI > 0, both seasons > 0, CI lower bound ≤ 0 |
| **A — actionable** | the above with CI lower bound > 0 |
| thin | n < 100 → KILL |

**Control, same bets:** the identical side on the identical line priced at the reference books'
*average* offered price instead of the outlier book's. The difference is what the outlier price
itself is worth.

## P2 — what shopping adds to the strategies already tested (execution only; information)
The selection is **not changed**; only the price paid is.
- The always-over null of the shared universe (`nba_pricing_realline.walk()`: WOWY tier, every stat,
  the FD+DK main rung) and **Arm T's selected bets** (`collect()`, unchanged), each priced at:
  FanDuel only (where FD posts that line), DraftKings only (likewise), **best of FD+DK** (the control:
  must reproduce Arm T's n = 1,186 / −41.09u, or the harness changed and nothing is concluded), and
  **best of all four books** at the same line.
- Line shopping (null universe): the over at the **lowest line any book posts** for that player-stat,
  at the best over price on that line, vs the main rung at best of four.

## Information only (pre-stated, no claims)
P1 by EV band (0–2, 2–4, 4–6, 6–10, ≥ 10%); by the book bet; over vs under; by market; restricted to
bets at FanDuel or DraftKings (the only books the live collector reads); restricted to WOWY-tier
candidates (injury spots). Calibration: mean `p_fair` of the bets vs their realised hit rate — if the
consensus is right these match; if the outlier book was the sharp one (it had moved on news), the
realised rate falls short of `p_fair`.

## Limits, stated now
- **One snapshot, ~30 min before tip.** No line movement, so no measure of how long an outlier price
  lasts, or whether it was still up when a bettor saw it. A pass says the price existed at that
  moment, not that it was bettable at size or stayed available.
- **No alternate lines in the history.** The 12% FD-vs-DK ladder gap seen live (2026-10-22) cannot be
  backtested; only the forward line collector can measure it.
- Books limit accounts that consistently take outlier prices. A pass is an edge on paper, not a
  promise of sustained volume.
- The live collector reads FanDuel and DraftKings only. If the edge sits at BetMGM or Caesars,
  capturing it live needs those books added (its own amendment).

## Guards (each mutation-tested before the run)
De-vig arithmetic; leave-one-out (a test that fails if *b*'s own price enters its reference); the
≥ 3-book and two-sided filters; in-play snapshots excluded; over/under and combo grading; void on
no box score; ambiguous names dropped; the P2 control reproduces Arm T exactly.

No result here authorises money.

## Addendum — P2 definitions fixed before any outcome is examined (2026-10-23)
Written after the code and its guards were built (all 16 mutations caught) but **before it was run.**
P2 re-prices bets chosen by the existing harness, so its price table mirrors `load_lines()` exactly:
in-play snapshots and ambiguous names are **kept** in P2 (they are dropped in P1), and a book's price is
its **over** quote at that line even if its under is missing (the harness requires two sides only for
the FD+DK line as a whole). "Best of four" therefore can never be worse than best of FD+DK. The
control check: every Arm T bet's FD+DK price, rebuilt from this table, equals the harness price, with
n = 1,186 / −41.09u, and the null reproduces n = 35,353 / −6.97%.

---

# RESULT — appended after the run, 2026-10-23. Nothing above this line was edited.

**Universe.** 434,034 player-stat-lines in the pre-tip snapshot; 190,536 with three or four books
two-sided at the same number; 4,275 void (player did not play) or outside the graded seasons; 20 names
dropped as ambiguous.

## P1 — bet the book that disagrees, EV ≥ 3%

| | n | dates | hit% | ROI | 95% CI |
|---|---|---|---|---|---|
| **pooled** | **7,797** | 322 | 46.5% | **+0.56%** | [−1.98, +2.97] |
| 2023-24 | 3,559 | 159 | 45.8% | −0.69% | |
| 2024-25 | 4,238 | 163 | 47.1% | +1.60% | |
| control: same bets at the other books' average price | 7,797 | | | −10.43% | |

## Verdict P1: **KILL** — the two seasons disagree in sign. Pooled is break-even.

**Why it breaks even.** The outlier price is real money: the same bets at the other books' average
price lose 10.43%, so the disagreeing book pays about 11 points more. But the disagreeing book is
**partly right**. The bets claimed an average EV of +4.95% (a 48.5% chance by the consensus) and hit
46.5%. That shortfall of about 2 points appears in **every EV band** (0.494 vs 0.471 at 0–2%, 0.477 vs
0.470 at 6–10%): when one book's price differs, it has usually moved on something the others had not.

**Information only — leads, not claims** (cut after seeing outcomes; many cuts were made):
- By EV band the ROI rises steadily: −3.85% (0–2%), −1.53%, +0.43%, **+5.15% (6–10%, n=1,350)**,
  **+10.12% (≥ 10%, n=252)**. Neither band's CI excludes 0.
- By the book bet: **BetMGM +9.09%, CI [+2.65, +15.68] (n=1,258)**; Caesars −9.54% [−16.86, −2.29];
  FanDuel +0.42%; DraftKings +1.21%. When BetMGM is the odd one out, BetMGM tends to be wrong. When
  Caesars is, Caesars tends to be right. At FanDuel or DraftKings only: +0.66%.
- Unders +3.89% [−0.12, +7.76] vs overs −1.80%. At WOWY-tier injury spots: +2.10% (n=1,795).

## P2 — what shopping adds (selection unchanged; both controls reproduced exactly)

| price paid | null (n=35,353) | Arm T (n=1,186) |
|---|---|---|
| best FD+DK (control) | −6.97% | −3.46% |
| best of four books | −6.34% | −2.96% |
| **gain from adding BetMGM + Caesars** | **+0.63 pts** | **+0.50 pts** |

Where both FanDuel and DraftKings post the line (null, n=17,051): FanDuel only −5.20%, DraftKings only
−6.59%, best of the two −4.26%, best of four −3.77%. Shopping the two books is worth about 1–2 points
over either one alone. Line shopping (the lowest line any book posts, null universe): −5.10% vs −6.34%,
+1.24 pts. **Nothing turns positive.** The WNBA's +3.31-point shopping gain does not appear at the
NBA close.

**Disclosed fix during the run.** The first run's Arm T control failed (n = 1,967 vs 1,186) because the
code took `collect()`'s rows without `current_selection`. The guard stopped P2 there, as designed. The
fix applies `nba_pricing.select`, which is what "Arm T's selected bets" means. P1's output was
byte-identical between the two runs.

**What this settles.** At the close, price alone is not an edge: a book that disagrees with the others
is right about as often as its better price pays for. Shopping trims 0.5 to 2 points of vig and does not
rescue any strategy tested. The two leads above (BetMGM as the outlier; EV ≥ 6%) were found by
cutting this data. They need a sample no test has touched.
