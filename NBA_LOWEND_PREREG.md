# PRE-REGISTRATION: LOWEND, flag only when the low end of the projection clears the line

Written 2026-10-28 (about 21:50 UTC), before the rule was built or run on any data. Research only; nothing changes live
without the user.

## The user's idea
"Take our players' efficiency when they shoot a range of FGA, FTA, 3PA and then times it by our low error, so like 3.1
less FGA, and then look at the projection, so all of our projections are on the low end of the range, and then see if
they would clear the line at that point."

**Shown to the user first:** a big gap between our projection and the line is often the book knowing something we do
not. ROLE1 found about 9% of the model's disagreement with the book was real. So a margin of safety must be tested,
not assumed.

## The user's choices (asked 2026-10-28)
| Choice | Answer |
|---|---|
| How low | **Both**: minus 1 full error (k = 1) and minus half (k = 0.5), reported separately |
| Efficiency | **His percentages in past games with similar volume** |
| Markets | **Points, threes, P+R, P+A, PRA** |
| Players | **Both**: players stepping into the lineup (STEP), and every player with a line |

Defaults stated to the user: overs priced −150 or better; the pass bar is the BOOST one.

## The rule
Everything reads only games before the date, for any team, this season and last.
1. **Minutes:**
   - **STEP players** (target A of `NBA_MINUTES_PREREG.md`, confirmed starters, absence games 1–3): the live STEP blend.
   - **Every player:** ROLE1 v3 with the out rotation players absent (the live ROLE_OPEN model). None means no
     projection.
2. **Volume:** projected FGA, 3PA, FTA, rebounds and assists = minutes × his per-minute rate (`nba_boost.rates`: last
   season worth 150 minutes).
3. **The errors E:** the MAE of each projection (minutes, FGA, 3PA, FTA, rebounds, assists) on 2023-24, per population
   (STEP players; every player), against the actual box score. They are fixed from 2023-24 and applied to both seasons;
   for 2023-24 that is in-sample.
4. **Low end:** FGA_lo = FGA − k × E_FGA; 3PA_lo = 3PA − k × E_3PA; FTA_lo = FTA − k × E_FTA (each floored at 0, and
   3PA_lo ≤ FGA_lo). Rebounds and assists lo = (minutes − k × E_min) × his per-minute rate.
5. **Efficiency in similar-volume games:**
   - **2P%:** his (FGM − 3PM) ÷ (FGA − 3PA) over past games with FGA within E_FGA of FGA_lo.
   - **3P%:** over games with 3PA within E_3PA of 3PA_lo.
   - **FT%:** over games with FTA within E_FTA of FTA_lo.
   - Each needs 5+ such games and at least 10 attempts in them. Otherwise it is his overall percentage over both
     seasons, and with no attempts at all, the league's 0.52 / 0.36 / 0.78.
6. **Low-end stats:**
   - points_lo = 2 × (FGA_lo − 3PA_lo) × 2P% + 3 × 3PA_lo × 3P% + FTA_lo × FT%;
   - threes_lo = 3PA_lo × 3P%;
   - P+R, P+A, PRA = points_lo plus rebounds and/or assists lo.
7. **Flag:** the over when the low-end stat > tonight's line (the FanDuel/DraftKings main tip line), priced −150 or
   better (best of the two). One flag per player, market and night.

## The test
- **Data:** `.projdata/nba_gamelogs.sqlite` logs_full (fgm, fg3m, fg3a, ftm, fta, minutes), NBA.com's lineups for the
  STEP population, and the 4-book tip-line archive. Seasons 2023-24 and 2024-25.
- **Graded:** stat > line wins at the price, < loses 1, equal is a push.
- **Reported:** each (population, k), per season:
  - flags, hit rate, the book's no-vig over, ROI with a 90% bootstrap, by market;
  - the errors E;
  - the projection-minus-line gap among flags.
- **Pass, per (population, k):** ROI > 0 in 2023-24 and in 2024-25, each with ≥ 100 flags.
- **Honest limits:**
  - tip lines are not openers;
  - "every player" uses box-score outs (hindsight);
  - E is fit on 2023-24;
  - live use would need FGM and FTM, which `nba_matchup` does not store, so it needs a data change before it could run
    live.

## Result (2026-10-28, about 22:05 UTC): FAIL at both depths, for both populations
`python3 nba_lowend.py --json .projdata/lowend_result.json` (26 s).

**Errors E (2023-24 MAE):**

| | minutes | FGA | 3PA | FTA | REB | AST |
|---|---|---|---|---|---|---|
| STEP | 5.48 | 2.90 | 1.56 | 1.63 | 2.12 | 1.49 |
| every player | 4.54 | 2.98 | 1.61 | 1.85 | 2.04 | 1.53 |

**Flags:**

| (population, k) | 2023-24 | 2024-25 |
|---|---|---|
| STEP, k = 1 | 77, hit 46.8% (no-vig 51.1%), −13.7% | 71, 43.7% (50.3%), −17.2% |
| STEP, k = 0.5 | 384, 46.9% (50.8%), −13.2% | 408, 53.4% (50.3%), +1.0% |
| every player, k = 1 | 1,983, 51.8% (50.9%), −3.4% | 1,971, 52.8% (50.6%), −0.8% |
| every player, k = 0.5 | 10,293, 51.1% (50.4%), −3.9% | 9,388, 52.3% (50.2%), −1.1% |

- No (population, k) passes. STEP at k = 1 is too rare (77 / 71) to pass anyway, and it lost.
- Every market loses or is flat in 2023-24. In 2024-25 the best are P+R (k = 0.5, +2.2%) and points (STEP k = 0.5, +5.5%,
  n 104). Within noise.

**Margin buckets** (every player, k = 0.5; information, sliced after the result):

| low end over the line | 2023-24 | 2024-25 |
|---|---|---|
| 0–10% | 6,371, −4.6% | 5,933, −1.7% |
| 10–25% | 2,799, −4.5% | 2,664, −0.3% |
| 25–50% | 866, hit 56.0% (no-vig 51.9%), +2.4% | 671, 54.4% (51.4%), +0.7% |
| 50%+ | 257, −0.3% | 120, −2.6% |

**Reading:**
- The margin does sort sides a little. The hit rate rises from about 50–52% to 54–56% at 25–50% over, but so does the
  book's own no-vig price. The book partly agrees, and the juice takes the rest.
- At 50%+ over it stops improving: the biggest gaps are where the book knows something.
- The 25–50% bucket is slightly positive in both seasons (+2.4%, +0.7%), but it was found after looking and sits inside
  noise (about ±3.5% at these counts). It is not a pass.
