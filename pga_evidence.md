# PGA v1.0  frozen 2026-07-30 — cumulative evidence

_updated 2026-07-31T10:03:27Z · measurement only; the model is frozen and this file never tunes it_

## Verdict

**INSUFFICIENT DATA**

- no settled bets carrying both probabilities yet

## Pre-registered test (fixed 2026-07-30 at n=0)

| | |
|---|---|
| H0 | outcomes occur at the devigged market rate `p_fair` |
| H1 | outcomes occur at the model rate `p_bet` |
| boundaries | reject H0 at LLR >= +2.773; accept H0 at LLR <= -1.558 |
| alpha / beta | 0.05 / 0.2 |
| halt | H-1 lower boundary · H-2 slope < 0.7 over 200 · H-3 n>=100 and ROI CI upper < 0 · H-4 data integrity |
| adoption | a challenger must beat the frozen baseline on a PAIRED SPRT over >= 100 prospective settled bets |

## Evidence

No scored bets yet. Settled rows in the ledger: **7** — all 7 carry both probabilities and are scorable in principle, but every one was flagged AFTER that player had teed off, so the capture rule excludes them

Nothing can be concluded. The first scorable bets arrive when a tournament settles with `p_bet`/`p_fair` recorded.

## Shadow streams (candidate hypotheses — NOT in the v1.0 test)

No settled shadow bets yet. `E3-cut-shadow` logs but cannot arm until it beats the frozen baseline on a paired SPRT over >= 100 prospective settled bets.

## Registered open hypotheses

- **H-P1 — REFUTED 2026-07-31, and briefly shipped before it was.** Adopted as v1.2 on a correlation of +0.152, reverted in v1.3 when a proper null showed it was the WEEK, not the player. The measurement de-conditioned at the ROUND level only; event factors span 0.81-1.24, so an easy week lifts every residual in it. Removing the EVENT level too: **r +0.152 -> +0.012** (0.019 birdies per 18), within-event null **+0.145 -> +0.006**. The original cross-event null (-0.005) was blind to this because it broke the week level along with player identity. DO NOT RE-PROPOSE without event-level de-conditioning and a WITHIN-event null. Original text follows for the record: should player rates use the CURRENT tournament's completed rounds? They do not today: `pga_birdies.rates()` reads the harvested history, refreshed WEEKLY, so this week's R1 is absent and a player who shot 65 and one who shot 77 are priced identically — while the book has fully absorbed the difference. The only channel R1 reaches the model is the FIELD-level LAM anchor.

  Tested 2026-07-31 on 42,557 harvested player-rounds across 114 events. Conditions removed first at the round level (field rate that round / field rate that event), because a course plays harder or easier round to round and that would otherwise masquerade as form — the factors do range 0.88x to 1.13x. Player baselines are LEAVE-ONE-EVENT-OUT so the current tournament never informs its own expectation.

  Residual carry-over: **R1→R2 +0.150 (n=12,593), R2→R3 +0.156 (n=7,757), R3→R4 +0.156 (n=7,406)**, pooled **+0.152 on 27,756 pairs**, against a shuffled cross-event null of **-0.005**. Three independent round-pairs within 0.006 of each other and a clean null: the effect is real.

  Worth: residual sd is 1.79 birdies per 18, so r=0.152 moves the next round's projection ~**0.27 birdies**. This week's flags sit 0.5-1.0 birdies from their lines, so it would move some across but is not decisive.

  ⚠ **Predicting the rate is not the same as making money.** The book almost certainly prices R1 form already, so adding it should REDUCE flags rather than fatten edges — it removes a reason we disagree with the market wrongly. That is still the right direction: the forensic verdict on this model was that a LOW-INFORMATION model compressed toward the base rate and its distance from the market read as edge. The cure for that is more information, not a different threshold. NOT ADOPTED — must clear the paired-SPRT rule on prospective data.

## Standing instruction

No model change is proposed or adopted on this evidence. Every modification is a new hypothesis and must clear the adoption rule above on PROSPECTIVE data. Retrospective improvement on data the change was designed against counts for nothing.
