# GOLF MODEL RESEARCH — state and registry

Phase 2. The market-relative phase is closed (see EXPERIMENTS.md, EXP-001..016): no PGA family
prices under a 5% hold, the four tightest were all tested and rejected, the book is internally
coherent, and every disagreement correlation measured was null or negative. The question now is
whether the underlying golf model can be made to understand player x course x conditions better
than it does.

PRODUCTION IS FROZEN. Nothing here modifies pga_ruler constants, calibration, ranking, live
betting or outputs. 2026 is the protected holdout and is not read by any experiment below.

---

# AUDIT — what the frozen model actually does (2026-08-15)

`pga_ruler.fit()` reads ONE table and five columns: `rounds(event_id, date, player, rnd, score)`.
It is a round-score rating engine and nothing else. Everything below is either already measured
into a constant, already tested and rejected, or absent.

## Already MEASURED (do not re-derive)
| thing | value | how it was established |
|---|---|---|
| recency | HALF_LIFE_D 270d | tuned on 2024-25, 2026 held out; clean interior peak, .5885 -> .5967 |
| skill shrinkage | K_SHRINK 11.0 | empirical Bayes, noise 7.786 / true between-player 0.709, 659 players |
| round correlation | RHO 0.05 | three independent estimates, all in [0.034, 0.109]; was 0.25, 5x too high |
| player volatility | SIG_SHRINK 78.0 | between-player variance of sd is 0.052 (8% spread) vs 4.02 sampling noise |
| rank compression | SPREAD 1.30 | tuned 2025, held-out 2026: mean abs slope error .4464 -> .1602 |
| tail shape | SHAPE_SLOPE per market | 986 runners / 9 majors, real closes, event fixed effects |
| cut rule | per-event 65/50/70/none | 242 events; agreement 62.7% -> 97.6%, make-cut slope 0.570 -> 1.060 |

**PLAYER VOLATILITY IS ANSWERED.** "Some players are streakier" is 8% real and 92% illusion.
GM-002 reproduced this independently from the round side (93% noise). Do not test it again.

## Already REJECTED (do not rebuild)
| mechanism | why it died |
|---|---|
| strokes-gained as a MAIN effect | partials ~0 once SG_TOT known (OTT +.001, APP +.016, PUTT -.044); every blend hurt; the rating already correlates +0.876 with SG_TOT and is built from finer round-level data |
| personal course history | true variance 0.0715 against 7.49 of round noise; 74% of the apparent effect survives a course-key placebo, i.e. form wearing a venue label |
| separate recent-form term | nothing left to absorb once HALF_LIFE_D is 270d |

## Existing but UNVALIDATED machinery
`pga_context.py` (course_factor, field_strength, course_fit, wind_factor), `pga_wave.py`
(fit_wave), `pga_holes.py` (green-penalty index), `sg_course_fit.py`, `build_interaction_table.py`
(the cached `ix` residual x skill x weather table). Built, wired to varying degrees, results
mostly unrecorded.

## Data on hand
| table | rows | span | note |
|---|---|---|---|
| rounds | 118,961 | 2023-01 .. 2026-08 | 297 events, 2,462 players. The backbone. |
| birdie_rounds | 49,854 | 132 tids | par-3/4/5 holes AND birdies separately -- a real skill axis |
| sg_stats | 7,150 | 4 seasons | 10 categories, ~305 players, SEASON level only, one fetch stamp |
| course_holes | 2,340 | 114 tids / 68 courses | per hole: par + that event's scoring distribution |
| ix (research) | 35,072 | 2024-01 .. 2026-07 | round residual x prior-season skill x weather |
| pga_wx (NEW) | building | 2023 .. 2026 | correct per-event-year venue + daily weather |

---

# DATA RISKS

## R1 — WEATHER COORDINATES ARE WRONG, AND IT REACHES PRODUCTION  ⚠️ OPEN
`pga_context._course_latlon` geocodes a BARE CITY NAME and caches one coordinate per TOURNAMENT
NAME. Both are broken. Measured distances from the real venue:

    Masters Tournament        1,598 km   Augusta MAINE, not Georgia
    Memorial Tournament       5,742 km   Dublin IRELAND, not Ohio
    Puerto Rico Open          5,793 km   Rio Grande BRAZIL -- wrong HEMISPHERE
    The Open                  5,848 km   Kenosha WISCONSIN
    Genesis Scottish Open     4,870 km   North Berwick MAINE
    Hero World Challenge      1,771 km   New Jersey, not the Bahamas
    U.S. Open / PGA Champ.       n/a     ROTATING venues; one coord per name cannot be right

At least 10.6% of the weather rows in `ix` come from a known-wrong coordinate, and that is a LOWER
BOUND because bare-city ambiguity applies everywhere. A wrong coordinate does not fail -- it
returns real weather for somewhere else. This is very likely why weather interactions have been
hard to find: the regressor is partly another continent's noise.

The same cache feeds the LIVE `wind_factor`. REPORTED, NOT REPAIRED -- the simulator is frozen and
fixing it in place would change production inputs. Awaiting a decision.

## R2 — weather coverage collapsed and nothing noticed
`ix` wind coverage: 2024 86%, 2025 14%, 2026 3%; 49 of 207 events have any wind at all.
`weather_for()` returns `{}` on an unresolved venue, so whole tournaments went missing silently and
read as missing-at-random. `_course_latlon` also caches FAILURES permanently, so one transient
error blacklists a course forever.
FIX IN PROGRESS: `pga_wx_research.py` -> `pga_wx.sqlite`, keyed by EVENT_ID (so rotating majors
resolve per year), geocoded with city+state+country and a HARD country-match gate, failing loud.

## R3 — SG is season-level with one fetch stamp
`sg_stats` carries a single `fetched` of 2026-07-30, so a season's value is its FINAL total. Usable
only LAGGED A FULL SEASON. Within-season use is look-ahead. (`ix` already enforces this.)

## R4 — course_holes scoring columns are the event's own outcome
`score_diff`, `birdies`, `bogeys` etc. are that tournament's result -> prior editions only.
`par` is architectural and safe to use same-year.

---

# REGISTRY

## GM-001 — does DISTANCE pay more where there are more PAR 5s?  ❌ REJECTED
Par mix is the one course characteristic that is variable (par-5 counts 2/3/4/5 across 130
course-editions), architectural (on the scorecard, zero look-ahead) and mechanistically tied to a
skill we hold. Single-course events only (13 of 114 run multiple courses and `rounds` does not say
which course a player played). Dev 2024 -> OOS 2025, 20,269 rows, 76 courses, 2026 untouched.

    DRIVE_DIST x n_par5   d=+0.0243  clustered SE 0.0300  t=+0.81
    OOS MSE 7.6085 -> 7.6082 against a target sd of 2.741
    placebo (par mixes shuffled across courses): |t| >= real in 94/200 -> p = 0.470

Seven other skills tested; DRIVE_ACC (t=+2.00), SG_OTT (+1.95) and SG_APP (+2.08) all made OOS
MSE WORSE. All eight coefficients shared the same sign, which is the signature of one shared
skill-correlation artifact rather than eight independent findings.

⚠️ METHOD: the placebo t distribution has sd **1.14, not 1.0**. Clustered SEs still understate
noise across ~76 courses, so a nominal t=2.0 here is p~0.08 empirically. Calibrate against the
placebo, never against the t table.

## GM-002 — are the four rounds exchangeable?  ⚠️ PARTIAL / see GM-003
The model draws all four rounds from one sigma. Selection is the whole difficulty: R3/R4 hold only
cut-makers, and their R1/R2 are truncated because they made the cut. Three comparisons, each
holding selection fixed:

    R1 -> R2  full field, no selection at all   sd 3.003 -> 3.070  +0.0668  t=+3.20
    R3 -> R4  identical post-cut cohort         sd 2.792 -> 2.851  +0.0591  t=+2.24
    placebo, round labels shuffled              +0.0013  t=+0.07   properly null

LEG B — "SUNDAY PLAYERS" DO NOT EXIST. ❌ REJECTED
    corr(R4-R1 tendency 2023-24, same 2025) = -0.016 over 190 players
    observed tendency variance .5085 | sampling noise .4723 | TRUE .0363
    -> 93% of the apparent spread is sampling noise
Independently reproduces the SIG_SHRINK result from the round side.

## GM-003 — is the round-variance rise real?  ❌ NOT INTEGRATED (fails chronological validation)

    CHRONOLOGICAL   R1 -> R2   2025 OOS  +0.0038  t=+0.12   the effect is NOT there
                    R3 -> R4   2025 OOS  +0.0499  t=+1.13
    TRIMMING        survives 2% and 5% trims (ratio 1.021 throughout) -> not withdrawals/blowups
    EVENT MIX       cut events R1->R2 t=+3.28 | NO-CUT events t=+0.36
    CONDITIONS      corr(day played hard, spread that day) = +0.271 over 944 event-rounds

Partialling difficulty out REVERSES the naive story: residual spread by round is R1 +0.046,
R2 +0.102, R3 -0.086, R4 -0.064 -- not a monotone rise, a R2 BUMP. And the large stable pattern in
the raw multipliers (R1/R2 ~1.03 vs R3/R4 ~0.96, within 0.005 across all three years) is post-cut
TRUNCATION, exactly the artifact the design was built to avoid reading as signal.

The surviving story is a CUT-PRESSURE bump in R2, present only in cut events, with a plausible
mechanism -- but it does not replicate in 2025 and therefore does not enter the research model.

⭐ THE REAL FIND HERE IS THE +0.271: SPREAD SCALES WITH DIFFICULTY. The model uses one sigma
regardless of conditions. That is a distribution-shape miss affecting every probability it quotes,
and unlike the round effect it is large, stable and mechanistically obvious. Pursued in GM-004.

## GM-007 — the in-play advantage, and a shipped constant that looks too small  ⭐ VERIFIED

In-play forecasting scores far better than pre-tournament, and that is used as evidence the
in-play path is doing something clever. Most of it is arithmetic: a forecast made after R3 has
HALF the remaining uncertainty of a pre-tournament one before it learns anything (remaining-total
sd 5.64 -> 4.88 -> 3.99 -> 2.82 strokes). Sharpening from fewer rounds remaining cannot be ported
back to a pre-tournament forecast, however good the log-loss looks. Any in-play vs pre-tournament
comparison that does not hold rounds-remaining fixed is measuring this and nothing else.

The part that COULD port back is within-week form, which the model prices through RHO = 0.05.

    R1 -> R2   FULL FIELD, zero selection      corr +0.0954   t=+10.90   n=21,810 / 177 events
    R1 -> R2   no-cut events only              corr +0.0905   t=+2.74
    R1R2 -> R3R4  no-cut only                  corr +0.1587   t=+4.98
    R3 -> R4   no-cut only                     corr +0.0161   t=+0.79
    PLACEBO (partner-swapped within event)     +0.0118 mean, 0/200 beat the real one, p=0.000

Everything is measured on RESIDUALS to the as-of rating, because a raw correlation between a
players early and late rounds is guaranteed by TALENT. The partner-swap placebo confirms the
residual really is ability-free: it sits at +0.012, not at +0.095.

STABLE IN EVERY YEAR SEPARATELY -- a constant that only exists pooled is a pooled artifact:
    2023 +0.1192 (t=3.87)   2024 +0.1015 (t=8.09)   2025 +0.0835 (t=6.28)

TWO FUNCTIONAL FORMS AGREE. If rounds share a week effect of size rho, the correlation between
TWO-ROUND AVERAGES is rho/(rho+(1-rho)/2). Observed +0.1587 implies rho ~ 0.086; rho=0.05 would
predict +0.0952 and rho=0.0954 predicts +0.1742. Single rounds and two-round averages therefore
point at the same rho ~ 0.086-0.095.

WHY THE SHIPPED 0.05 IS LOW. The prior estimate of +0.039 came from ALL round pairs. R3->R4
measures +0.0161 here because those rounds are reached only by cut-makers, whose R1-R2 is
truncated by the very cut that selected them. Pooling a clean early correlation with a truncated
late one lands between the two -- which is exactly where +0.039 sits. The nested-ANOVA (0.055) and
36-hole-spread (0.109) estimates bracket the value found here; 0.0954 is at the top of the
published [0.034, 0.109] range, not outside it.

VERDICT: the within-event common component is ~0.09, not 0.05. RHO governs 72-hole variance and
in-play updating, so the frozen model understates both. RESEARCH FINDING ONLY -- production is
frozen and this changes no constant. Needs the same probability-calibration A/B that GM-006 runs
for dispersion before it would ever be a change worth making.

⚠️ ALSO FOUND: the within-event correlation DECAYS through the week. R1->R2 is +0.0905 and
R3->R4 is +0.0161 in the SAME no-cut events, where neither is selection-affected. A single RHO
cannot be right for both ends of the tournament.

## GM-008 — the full round-pair matrix: the week effect is ~0.085, with ONE exception  ⭐

The model represents within-week correlation as a single shared week effect, and that structure
makes a falsifiable claim: all SIX round pairs must correlate equally. Measured on no-cut events
only -- the sole place all six pairs share one unselected cohort:

    pair    lag     corr        pair    lag     corr
    R1-R2    1    +0.0905       R1-R3    2    +0.0833
    R2-R3    1    +0.0996       R2-R4    2    +0.0887
    R3-R4    1    +0.0161       R1-R4    3    +0.0709

Five of six sit between +0.071 and +0.100. The structure is NOT lag decay -- averaged by lag it is
+0.069 / +0.086 / +0.071, flat, and the lag-1 average is dragged down solely by the outlier. It is
also not a general late-tournament decay: R4 correlates perfectly normally with R1 (+0.0709) and
R2 (+0.0887). What is missing is specifically the R3-R4 ADJACENCY, about 3.4 SE below the others.

Read plainly: a constant week effect is the right SHAPE, its size is ~0.085 rather than the
shipped 0.050, and one pair violates it. The natural mechanism for that one pair is CONTENTION --
R3 sets the leaderboard, and R4 is then played under conditions R3 itself created (position,
pairing, pressure, whether a player still has anything to play for). That is a feedback the model
has no representation of, and it acts on exactly the pair where the correlation disappears.

⚠️ n = 27 no-cut events. The five-pair cluster is solid; the R3-R4 exception rests on a modest
sample and is PROMISING, not verified.

---

# RESEARCH STATE

## VERIFIED
- **event scoring dispersion is predictable from prior editions** (GM-004/005): persistence
  +0.692 raw / +0.611 after field-knowledge, OOS MSE -49.8% / -45.1%, placebo 0/400. Probability
  impact under test in GM-006.
- **the within-event week effect is ~0.09, not the shipped RHO=0.05** (GM-007): +0.0954 on the
  clean no-selection sample, stable in all three years, placebo p=0.000, and corroborated by the
  two-round-average form. Decays through the week (R1->R2 +0.0905 vs R3->R4 +0.0161).

## PROMISING
- spread scales with day difficulty (corr +0.271, 944 event-rounds) -- needs a PREDICTABLE
  difficulty proxy to be usable pre-tournament. GM-004.
- R2 cut-pressure variance bump: right sign, right mechanism, absent in 2025 and in no-cut events.
- the R3->R4 CONTENTION anomaly: five of six round pairs correlate ~+0.085, R3-R4 is +0.016
  (GM-008). R4 still correlates normally with R1 and R2, so it is the adjacency that breaks, not
  round 4. n=27 no-cut events.

## REJECTED
- distance x par-5 count, and 7 other skill x par-mix pairings (GM-001)
- player-specific round tendency / "Sunday players" (GM-002 leg B)
- round-variance rise as a modelling term (GM-003, fails 2025 OOS)
- SG as a main effect; personal course history; separate recent-form term (pre-existing)

## INTEGRATED
(nothing yet -- the research model is still the frozen model)

## BLOCKED
- all weather and wind x player work, until pga_wx.sqlite finishes and R1/R2 are resolved
- Top-N / 3rd-round-leader grading, until St Jude 2026 completes

---

# METHOD RULES FOR THIS PHASE
- CALIBRATE SIGNIFICANCE AGAINST A PLACEBO, NOT THE t TABLE. The empirical null t had sd 1.14.
- HOLD SELECTION FIXED BY CONSTRUCTION, then check whether the surviving pattern is the selection
  anyway. R3/R4 spread looks like a round effect and is truncation.
- PARTIAL OUT DIFFICULTY BEFORE READING A ROUND EFFECT. It reversed the sign here.
- A COEFFICIENT THAT IMPROVES IN-SAMPLE AND WORSENS OOS MSE IS NOISE, however significant.
- WHEN EVERY VARIANT SHARES A SIGN, suspect one shared artifact, not many findings.
