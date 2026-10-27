# PRE-REGISTRATION: proj-1.2 and market tests, from the audit and the pricing research

Written 2026-10-27, **before any of these tests has been built or scored, and before proj-1.1.1's
amendment-1 result was seen.**

**Already seen:**
- the audit (`NBA_PROJECTION_AUDIT.md`, E1–E7);
- proj-1.0 and proj-1.1 results;
- the minutes diagnostic;
- the pricing research (`/Users/ethandown/dev/reports/NBA player prop pricing.md`, hypotheses H1–H10).

Nothing here changes proj-1.0, proj-1.1 or their records.

**Base model ("B"):** proj-1.1.1 if amendment 1's decision passes (NBA_PROJ11_PREREG.md), otherwise
proj-1.0. Its walk-forward means and analog ensemble are used as they are.

**Seasons:**
- 2023-24 for fitting: development.
- 2024-25 for testing: development after exposure. It was used for proj-1.0 and proj-1.1, but never for
  these four questions.
- Prospective logging decides everything else.

**Lines:** FanDuel lines at the about −29 min snapshot; pushes excluded; proportional de-vig.

## Primary tests (Holm across the four; one-sided α = 0.05)
**T1. Mean recalibration (research H4).**
- **Fit:** for each of the 8 stats, a Mincer-Zarnowitz line `actual = a_s + b_s · μ_s`, fitted on every
  2023-24 row of B.
- **Apply:** on 2024-25, μ″ = max(0, a_s + b_s·μ). The analog ensemble is rebuilt around μ″, the same
  construction as B.
- **Primary metric:** FanDuel log loss, T1 − B (upper 95% bound < 0).
- **Secondary:** normalized CRPS, and bias by projection quintile, which should sit within ±0.3 for points.

**T2. Fitted model–market blend with a gap term, by stat family and side (research H3).**
- **Families:**
  - scoring: points, P+R, P+A, PRA;
  - boards and assists: rebounds, assists, R+A;
  - threes;
  - defense: steals, blocks.
- **Side:** which way B leans against FanDuel's no-vig price.
- **Model:** `logit p = a + b·logit p_FD + c·(logit p_B − logit p_FD)`, one fit per family × side (8 cells)
  on 2023-24, applied to 2024-25.
- **Primary metric:** T2 − FanDuel log loss, all props (upper bound < 0).

**T3. FanDuel-implied minutes (research H2).**
- **Scale:** for each player-game with a FanDuel points main line, find k ∈ {0.50, 0.51, …, 1.60} whose
  scaled points distribution has its median nearest the line. Scaling means every draw's minutes and
  counts × k, the same as the known-minutes diagnostic.
- **Price the other stats:** price rebounds, assists, threes, steals and blocks (not combos, which
  contain points) at their FanDuel lines from B's distribution scaled by the same k.
- **Primary metric:** T3 − FanDuel log loss on those markets pooled (upper bound < 0).

**T4. Other books against FanDuel's price (research H6). A betting-rule test; research only, nothing is bet.**
- **Rule, fixed now with no threshold search:** take every player-game, market and line at the T−30
  snapshot where FanDuel has a two-sided price and DraftKings, BetMGM or Caesars has the same line. Bet
  side S at book X when FanDuel's no-vig probability of S times X's decimal odds minus 1 is above +0.02,
  that is, an expected value above 2% against FanDuel's fair price. Flat 1 unit; one bet per book and side.
- **Primary:** ROI pooled over 2023-24 and 2024-25 (nothing in the rule is fitted, so both seasons are
  out of sample for it), lower 95% bound > 0. Both seasons' point estimates must also be > 0.
- **Secondary:** ROI by book and by market, and the number of bets.

## Secondary, descriptive (no decision)
- **H7:** FanDuel's over premium under four de-vig methods (multiplicative, additive, power, Shin), by
  market, both seasons.
- **H8:** FanDuel combo vs components. Do realized combo over rates track the combo price, or a
  combination of FanDuel's own component prices? Reported only.

## What happens next
- **If T1 and/or T2 pass:** proj-1.2 = B + T1 and/or T2 is logged in shadow beside proj-1.0 and proj-1.1.1
  at tip − 30. It gets its own version, and the same prospective decision lines (2,000 graded props, then
  2,000 more to replicate).
- **If T3 passes:** its live form needs FanDuel's points line at tip − 30, which is on the board. It is
  logged the same way.
- **If T4 passes:** its live form (FanDuel vs DraftKings, the two books collected live) is logged in
  shadow from the quote change logs. It is graded on ROI at the prices that were offered, plus CLV against
  FanDuel's later price.
  - **Bar:** ≥ 500 prospective signals and a lower 95% bound > 0.
  - Nothing is shown as a pick and nothing is bet; `nba_flags.LIVE_TIERS` stays empty.
- **Failures:** a test that fails is reported and not retried with other settings. A change means a new
  version and a new pre-registration.

## Prospective-only hypotheses (no historical data to test)
- **H1:** minutes weighted by each teammate's probability of playing, from report status and lineup
  snapshots. Needs report history, which begins 2026-10-22.
- **H5:** the model against early prices, from the live change logs.
- **H9:** blowout and overtime scenarios from the game spread. game_lines begin 2026-10-22.

Each of these gets its own pre-registration once there is data to test it on.
