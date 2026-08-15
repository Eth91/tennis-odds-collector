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
It is a round-score rating engine -- but see the FIELD STRENGTH correction below: it also runs a
two-pass field-quality adjustment internally, which the first draft of this audit missed. Everything below is either already measured
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

## GM-009 — wind: real for scoring, NULL for dispersion, and a correction to my own claim

Run on the rebuilt pga_wx table (per-event-year venues, country-gated, ambiguous cities refused,
curated majors). Everything demeaned WITHIN EVENT across that event's rounds, so course, setup,
field and par cancel and only day-to-day variation at one venue remains.

    wind -> scoring      +0.0440 strokes per km/h  = +0.44 per 10 km/h   t=+1.75  n=128 events
    wind -> dispersion   -0.0106 strokes per km/h                        t=-1.25  n=128 events

WIND DOES NOT SPREAD THE FIELD. The sign is negative and insignificant. That MATTERS for GM-004:
the dispersion that is predictable from prior editions is NOT a wind effect, so the two findings
are independent and GM-004 does not reduce to windy venues stay windy.

⚠️ CORRECTION TO MY OWN FIRST READING. The initial run compared old-pipeline wind (+0.3678) with
rebuilt wind (+0.3935) and I called the fix real, more signal. Those were DIFFERENT SAMPLES --
48 events versus 128. Restricted to the 47 events present in both:

    old coordinates   n=187 days   corr(wind, scoring) +0.3398
    new coordinates   n=187 days   corr(wind, scoring) +0.3159

Indistinguishable, and if anything the old is higher. The correct claim is that the coordinate fix
bought COVERAGE -- 48 -> 128 events, 191 -> 511 day-observations -- not a stronger per-observation
signal. Only ~10.6% of old rows came from a known-wrong venue, and the shared events are largely
the ones the bare-city geocode happened to get right, so the old correlation was DILUTED rather
than destroyed. The Masters-from-Maine defect is still real; its measured cost is smaller than the
headline comparison implied.

USABILITY. Same-day wind is not a pre-tournament input -- charter rule 20 forbids using what was
not known at prediction time. Archived actual wind is legitimate only for in-play or day-of
pricing, which is where pga_context.wind_factor already lives.

⚠️ ASSUMPTION: rounds.date is the event START date, identical for all four rounds; the warehouse
has no per-round date. Round r is mapped to start+(r-1), correct for Thu-Sun and wrong for
weather-delayed or Monday finishes. That mis-dating is noise and can only bias toward zero.
⚠️ wind is wind_speed_10m_max for the DAY, so a calm morning wave and a gale-blown afternoon wave
share one number.

## GM-011 — WIND x PLAYER: both readings of the charter question are dead  ❌ REJECTED

Run on the rebuilt weather, wind demeaned WITHIN EVENT so that a venue which is simply windy
cannot masquerade as a wind effect. 23,370 rows, 87 events, within-event wind sd 4.78 km/h.
Dev 2024 -> OOS 2025, prior-SEASON skill only, 2026 untouched.

LEG A -- does a measurable SKILL buy wind resistance?
    GIR x wind        d=+0.0588  t=+2.22   OOS MSE 7.6773 -> 7.6780  WORSE
    DRIVE_ACC x wind  d=+0.0307  t=+1.44   OOS MSE improves in the 4th decimal
    the other six     |t| < 1.4
    placebo on GIR (wind shuffled between event-rounds): real +2.22 vs null sd 1.02, p=0.042

GIR passes its placebo and STILL FAILS, for two reasons that both matter. It makes out-of-sample
prediction WORSE, which is the standing rule from GM-001: a coefficient that improves in-sample
and worsens OOS MSE is noise however significant. And the placebo was run on the strongest of
EIGHT skills, chosen by its own t -- under the null the best of eight clears p=0.042 about 29% of
the time. A per-test p-value applied to a hand-picked maximum is not a p-value.

LEG B -- do INDIVIDUAL players have a repeatable wind slope? This is the charter's literal
wording and it is the shape that has already produced two illusions here.
    corr(wind slope 2024, wind slope 2025) = -0.036 over 119 players
    observed slope variance 0.00298 | sampling noise 0.00348 | TRUE 0.00000
    -> 100% of the apparent spread is sampling noise

THIRD TIME FOR THIS PATTERN, and the number gets worse each time:
    streaky players  8% real     (SIG_SHRINK, pre-existing)
    Sunday players   7% real     (GM-002 leg B)
    wind players     0% real     (here)
Player-specific ability to handle a CONDITION does not exist in this data at a detectable level.
Any future hypothesis of the form some players are better at X should be costed against this.

## GM-012 — birdie skill: REAL, and par-5 is genuinely a separate axis  ⭐

birdie_rounds carries what no other table does -- holes played AND birdies made, split by par
type, at ROUND level with honest timestamps. 37,019 usable player-rounds, 1,194 players. Rates are
taken against the FIELD rate for that (event, round, par type), so course, setup and par mix are
absorbed before any skill is measured.

LEG 1 -- is birdie-making a skill at all?
    corr(birdies above field, 2024 vs 2025) = +0.518 over 171 players
    observed variance .006717 | Poisson sampling noise .003679 | TRUE .003038
    -> 45% of the spread is REAL SKILL
That is a different world from the three player-condition hypotheses (streaky 8%, Sunday 7%,
wind 0%). Birdie-making genuinely varies between players and repeats.

LEG 2 -- are par-3/4/5 rates distinct skills, or one skill in three costumes? Partial correlation
removes the players OVERALL birdie rate from both halves, which is exactly the test that killed
strokes-gained (every SG partial was ~0 once SG_TOT was known):
    par 3   raw +0.074   partial +0.025    not distinct
    par 4   raw +0.397   partial +0.082    not distinct
    par 5   raw +0.403   partial +0.215    DISTINCT
Par-5 birdie skill survives, and mechanistically it should: reaching a par 5 in two is a different
ability from scrambling a birdie on a par 4. This is the FIRST skill decomposition in this project
to pass a partial test.

## GM-013 — ...and it still does not PREDICT better  ❌ REJECTED

Distinct is not useful. Predicting a players birdie count in a round, one rate against three:
    field only (no skill)   Poisson deviance 0.76765
    A  one birdie rate                       0.76123
    B  par-type rates                        0.76209     B - A = +0.00086

FAIR ON SHRINKAGE, which matters because B estimates three rates from the rounds that gave A one,
so Bs inputs are noisier by construction. Each model was also allowed its OWN best shrinkage:
As optimum is 0.77218 at K=160, Bs is 0.77278 at K=40. A still wins.

THE MECHANISM CHECK FAILS TOO. If par-5 skill were the edge, B should win where par 5s are
plentiful. It loses there and wins only where they are scarce:
    0-2 par 5s   B -0.00100      3 par 5s   B +0.00290      4 par 5s   B +0.00063

VERDICT: splitting one birdie skill into three triples the estimation noise, and a +0.215 partial
on one of the three does not pay for it. Same conclusion as strokes-gained, reached from the
opposite direction -- there the partial was absent, here the partial is real and still unprofitable.

WORTH KEEPING: OVERALL birdie skill is clearly useful -- deviance 0.76765 -> 0.76123 against
field-only, on 18,135 held-out player-rounds. Any birdie model should carry a shrunk player factor;
it should not carry three.

## GM-006 — does the dispersion multiplier improve PROBABILITIES?  ❌ NOT INTEGRATED

The paired A/B for GM-004/005. A = one sigma (frozen), B = sigma x predicted dispersion from prior
editions. Same field, same seed, same cut rule; the CRN floor was asserted at EXACTLY
0.0000000000 before anything was read. 75 events, 9,516 player-observations, multiplier built from
2023-24 only, 2026 untouched.

    market     LL A       LL B      delta      slope A   slope B
    cut        0.62049    0.62061   +0.00012     0.753     0.751
    top20      0.43035    0.43045   +0.00010     1.070     1.061
    top10      0.28014    0.28021   +0.00007     1.045     1.034
    top5       0.17894    0.17900   +0.00006     1.024     1.011
    win        0.05226    0.05240   +0.00014     1.109     1.077
    summed     1.56219    1.56267   +0.00048

SPLIT VERDICT, reported as one. Log-loss is worse on all five. Calibration SLOPE moves TOWARD 1.0
on all four placement markets (top20 1.070->1.061, win 1.109->1.077) and marginally away on cut.
Both movements are trivial in size.

WHY SO SMALL, AND IT IS NOT THE FINDING THAT IS WRONG. The predicted multipliers have mean 0.997
and sd 0.066 -- a typical +-6.6% nudge to sigma. Rank probabilities in this simulator are driven by
the spread of player MEANS (SPREAD=1.30 exists precisely because shrunk means made fields look
homogeneous and compressed every probability toward its base rate), and sigma enters second order.
A 6.6% sigma change cannot move a rank distribution much, whatever it does to the width of one
player's score.

So GM-004 stands exactly as measured -- dispersion IS predictable, 45-50% better than the constant
the model uses, placebo 0/400 -- and the lever available to exploit it is too small to matter. The
effect is real; this intervention is not worth making.

⚠️ A GRADING BUG WAS CAUGHT AND FIXED BEFORE THIS RESULT WAS BELIEVED. The first run skipped
every player who was neither in `pos` nor `made` -- exactly the missed-cut players -- so `cut` was
scored on a sample whose outcome was always 1 (the calibration slope came back 0.002, which is the
tell) and top-N was scored only among survivors while the probabilities covered the whole field.
Corrected: every player who STARTED is graded, with ties-inclusive probabilities matched to
ties-inclusive positions. n went 5,363 -> 9,516 and the slopes went from 0.002 to 0.75-1.11.

## AUDIT — WAVE and WIND are already fitted; one of them was fitted on bad coordinates

Checked before building anything, because the charter forbids rebuilding what exists.

WAVE (charter 6) IS DONE AND IT IS REAL. `pga_wave.fit_wave()` measures the AM-vs-PM stroke gap
WITHIN each event-round, so course, field and par mix cancel by construction. Cached fit:

    n_gaps 479 over 120 events      mean gap +0.127 strokes      mean ABSOLUTE gap 0.671
    beta 0.1007 strokes per km/h of wave wind-exposure gap       r = 0.375     assumed = false

Two thirds of a stroke separates the waves in a typical event-round -- larger than most player
edges -- and `pga_ruler.simulate()` already takes `wave` and `wave_shift`, so the model can carry
it. Do not rebuild this.

WHAT IS NOT DONE: the wave gap is only usable PRE-round if the AM/PM wind difference is known in
advance, and that needs HOURLY wind. Both the old pipeline and the rebuilt pga_wx table store
DAILY values (wind_speed_10m_max), which cannot distinguish a calm morning from a blown-out
afternoon -- the two waves share one number. open-meteo's archive does serve hourly, so this is a
data build, not a modelling problem. UNBLOCKED, not attempted.

WIND (charter 5) IS FITTED BUT ON THE WRONG WEATHER. Cached `wind_factor`:

    w = -0.00515 per km/h    n = 423 over 106 events    r = -0.201    mean wind 17.6 km/h

The negative sign is CORRECT and is not a contradiction of GM-009's +0.44 strokes per 10 km/h:
this coefficient multiplies a BIRDIE expectation, so more wind means fewer birdies means higher
scores. The two agree.

The problem is the input. This was fitted through `pga_context._course_latlon`, the same lookup
that put the Masters in Augusta MAINE, the Memorial in Dublin IRELAND and the Puerto Rico Open in
BRAZIL, and it covers 106 events where the rebuilt table covers 168. A refit on corrected
coordinates is a concrete, well-scoped improvement to a LIVE production term.

⚠️ NOT REFITTED. `wind_factor` is production and the simulator is frozen. Flagged for a decision.

## AUDIT CORRECTION — FIELD STRENGTH is already inside the rating fit (charter 16)

My own audit said `pga_ruler.fit()` "reads ONE table and five columns" and left the impression that
it does nothing but average them. That is right about the INPUTS and understates what it does with
them. `fit()` runs a TWO-PASS fit:

    pass 1   the naive fit
    pass 2   subtracts each event-round's OWN field quality -- the mean pass-1 rating of everyone
             who teed off in it -- so a round's baseline is its field mean OFFSET by that field's
             quality:   fm = fm - fieldq[(event, rnd)]

The reasoning is in the source: ratings are strokes-vs-field-mean, so without this "beating a
Korn-Ferry-grade field by 2 counted the same as beating a signature field by 2, and opposite-field
regulars were systematically flattered".

CHARTER 16 IS THEREFORE ANSWERED. Field drift is corrected at the point it enters, which is the
right place -- correcting it downstream in the simulator would leave the ratings themselves biased.
`pga_context.field_strength()` is a SEPARATE implementation of the same idea and is called by
nothing; it is dead code, not a missing feature.

## METHOD NOTE — the A/B slopes are pga_sim's, NOT production's

GM-006 and GM-010 both run in `pga_sim`, deliberately: it takes explicit (mean, sigma) per player,
so a sigma multiplier or a rho change can be applied without touching the frozen `pga_ruler`. The
cost is that pga_sim carries NONE of pga_ruler's downstream corrections -- no SHAPE_SLOPE tail
recalibration, no `_recal_shape`. So the ABSOLUTE calibration slopes those experiments report:

    cut 0.753   top20 1.070   top10 1.045   top5 1.024   win 1.109

describe the RAW rank simulator and must not be read as production calibration. They are in fact
consistent with the corrections production already applies: SHAPE_SLOPE_STD carries win 1.21
precisely because raw log-odds come out too flat in the win tail, which is what a slope of 1.109
means. And pga_ruler's own make-cut slope is 1.060 after the per-event cut rule landed, against
0.753 here without it.

WHAT REMAINS VALID is the DELTA between arms, because both arms are equally uncorrected, share a
field, a seed and a cut rule, and were run against a CRN floor asserted at exactly 0.0000000000.
An A/B answers "does this change help", not "is the model calibrated" -- and only the first
question was asked.

⚠️ Do not quote these slopes as evidence about the live model.

---

# RESEARCH STATE

## VERIFIED
- **birdie-making is 45% real skill** (GM-012): corr +0.518 across halves, and a shrunk overall
  player factor beats field-only out of sample (Poisson deviance .76765 -> .76123, n=18,135).
  Par-5 birdie skill is genuinely distinct (partial +0.215) but does NOT improve prediction.
- **event scoring dispersion is predictable from prior editions** (GM-004/005): persistence
  +0.692 raw / +0.611 after field-knowledge, OOS MSE -49.8% / -45.1%, placebo 0/400. BUT the
  available lever is a +-6.6% sigma nudge, and GM-006 shows it does not improve probabilities
  (log-loss slightly worse, calibration slope slightly better). Real, and not worth acting on.
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
- par-TYPE birdie modelling (GM-013): distinct but not predictive; A beats B even at each model
  own best shrinkage, and B loses precisely where par 5s are plentiful
- wind x player, both as a skill interaction (fails OOS, and it is the best of 8) and as a
  player-specific slope (100% sampling noise, corr -0.036) -- GM-011
- wind as a driver of DISPERSION (GM-009: -0.011/km/h, t=-1.25) -- GM-004 is not a wind effect
- distance x par-5 count, and 7 other skill x par-mix pairings (GM-001)
- player-specific round tendency / "Sunday players" (GM-002 leg B)
- round-variance rise as a modelling term (GM-003, fails 2025 OOS)
- SG as a main effect; personal course history; separate recent-form term (pre-existing)

## INTEGRATED
(nothing yet -- the research model is still the frozen model)

## PROMISING (continued)
- refit `wind_factor` on the rebuilt weather: the live fit used the bad-coordinate lookup and
  106 events; corrected data covers 168. Production is frozen, so flagged not done.
- HOURLY wind would make the wave gap a PRE-round input. Daily max cannot separate the two waves.

## BLOCKED
- 128 of 297 events still have no venue: 126 fail ESPN with HTTP 403, 2 refused as ambiguous
  city names (Yokohama, Troon) by the fail-closed gate
- Top-N / 3rd-round-leader grading, until St Jude 2026 completes

---

# METHOD RULES FOR THIS PHASE
- CALIBRATE SIGNIFICANCE AGAINST A PLACEBO, NOT THE t TABLE. The empirical null t had sd 1.14.
- HOLD SELECTION FIXED BY CONSTRUCTION, then check whether the surviving pattern is the selection
  anyway. R3/R4 spread looks like a round effect and is truncation.
- PARTIAL OUT DIFFICULTY BEFORE READING A ROUND EFFECT. It reversed the sign here.
- A COEFFICIENT THAT IMPROVES IN-SAMPLE AND WORSENS OOS MSE IS NOISE, however significant.
- A PLACEBO RUN ON THE STRONGEST OF N TESTS MUST BE CORRECTED FOR N. The best of eight skills
  clears p=0.042 about 29% of the time under the null (GM-011).
- "SOME PLAYERS ARE BETTER AT X" HAS FAILED THREE TIMES: streaky 8% real, Sunday 7%, wind 0%.
  Always decompose between-player variance against sampling noise BEFORE believing the spread.
- WHEN EVERY VARIANT SHARES A SIGN, suspect one shared artifact, not many findings.
- A VERIFIED EFFECT AND A USEFUL INTERVENTION ARE DIFFERENT THINGS. Dispersion is genuinely
  predictable (45-50% MSE better) and the multiplier it implies is only +-6.6%, which a rank
  simulator barely feels. Ask how big the LEVER is, not just how real the EFFECT is.
- A CALIBRATION SLOPE NEAR ZERO MEANS THE GRADER IS BROKEN, not that the model is uninformative.
- AN A/B IN A STRIPPED-DOWN ENGINE MEASURES THE CHANGE, NOT THE MODEL. pga_sim has no tail
  recalibration, so its absolute slopes are not production's; only the between-arm delta transfers.
