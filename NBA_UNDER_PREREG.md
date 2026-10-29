# PRE-REGISTRATION: UNDER20 and UNDERML, the forward test of T2's finding (2026-10-28, about 22:20 UTC, before code)

**Where it comes from** (`NBA_TESTS4_PREREG.md`):
- T2's logistic model passed on held-out 2024-25: log loss 0.68818 against the book's 0.68878, and EV ≥ 5% bets made
  +3.5% on 11,155. It held on FanDuel-only prices and without the hindsight features.
- 92% of its bets were unders. The simple rule "under when our projection < 0.8 × the line" made +5.6% (5,940) and +4.5%
  (4,508) at tip lines. That cut was chosen after seeing T2's bets.
- So neither is proven. This is their forward test.

**User's choices:** both rules, 30 minutes before tip; the simple rule pings (SHADOW), the model is silent. Nothing
bets: `nba_flags.LIVE_TIERS` stays empty.

## Shared
- **When:** each game's first pinger run at or after tip − 30 and before tip − 5 (as RETURN_UNDER and FOUL_BIG). In the
  side-by-side it is the tip − 30 tick.
- **Board:** FanDuel's current main rung for each player prop in the 8 markets.
- **Out tonight:** the official report's Out or Doubtful for the player's team, read as of the run. Out players are
  not judged.
- **Projection:**
  - V3 minutes (`nba_boost.v3_minutes`: ROLE1 v3, every out rotation player absent, the active roster less the outs)
    × `nba_boost.rates` (last season worth 150 minutes), summed for a combo;
  - the same as T2's backtest, except that the outs come from the report and not the box score;
  - no V3 means no projection.
- **One signal per (rule, game, player, market).**

## UNDER20 (pinged)
- The under when the projection < 0.80 × the line, at FanDuel's under price. There is no price cap, as tested.
- **Ping:** "🔵 UNDER {player} {market} u{line} {price} FD · proj {proj} ({ratio} of the line), {minutes} min · shadow".

## UNDERML (silent)
- **The model:** T2's logistic model without the hindsight outs features, refit on 2023-24 exactly as in
  `nba_tests4_checks.py`'s "without the hindsight outs features" run. Exported as `nba_under_model.py` (the VM has no
  scikit-learn); its predictions must equal scikit-learn's.
- **Features:** logit(FanDuel's no-vig over at the main), the line, projection ÷ line, V3 minutes − his last-10
  minutes, his season mpg, his last-5 ÷ season mean of the market's stats, rest days (capped at 4), back-to-back, the
  team's game index, and the market (one-hot). Missing values take the 2023-24 medians.
- **The bet:** either side where p × FanDuel's price − 1 ≥ 0.05.

## Judged
- Like every rule, by the side-by-side's CLV and ROI, at ≥ 200 signals over ≥ 10 dates.
- Registered at the deploy time in `nba_sxs_rules.py`.

# AMENDMENT 1: which UNDER20 flags ping (2026-10-28, about 22:20 UTC, before deploy)
- **Dry run on tonight's FanDuel board:** 930 props, 54 UNDER20 flags. Many were threes unders at −180 to −250.
- **Backtest split (post-hoc, information):** UNDER20 under −150 or better made +7.3% / +6.9% (4,256 / 3,048); worse
  than −150, +1.1% / −0.6%. Threes made +0.5% / +0.2%. Every other market was positive in both seasons.
- **User:** ping only "−150 or better, no threes". **Everything is still recorded:**
  - UNDER20 stays as registered (all flags);
  - a second side-by-side rule, **UNDER20P**, is the pinged subset (under −150 or better, not threes), registered
    with the others.
  - The forward record shows whether the filter holds.

# AMENDMENT 2: the cut swept, information (2026-10-28, about 22:35 UTC; post-hoc)
**User:** "what if we run 25% or 30% or 35% or 40%, does the ROI increase?" (`nba_under_sweep.py`, 2023-24 tip lines;
the same rows as T2's checks.)

| unders −150 or better, no threes | 2023-24 | 2024-25 |
|---|---|---|
| 20%+ below (live) | 3,916, +7.7% | 2,819, +6.9% |
| 25%+ below | 2,127, +8.7% | 1,469, +9.8% |
| **30%+ below** | **1,181, +15.2%** (90%: +11.0%, +19.6%) | **765, +14.2%** (+9.0%, +19.3%) |
| 35%+ below | 676, +14.8% | 395, +7.3% |
| 40%+ below | 397, +15.8% | 191, +7.8% |

- All flags (threes and heavy prices included) give +9.5% / +8.1% at 30%+.
- The bands: 20–25% below, +6.4% / +3.8%; 25–30%, +0.6% / +5.1%; 30–40%, +14.9% / +16.3%.
- **Reading:**
  - ROI rises to about 30% below, then flattens while the count falls.
  - Total profit is larger at 20%+ (2024-25: about 195 units against about 109).
  - The cut was chosen after looking, from five tried, so the forward record decides. No live change without the user.

# AMENDMENT 3: a star on 30%+ (2026-10-28, about 22:40 UTC, before code)
- **User:** "mark 30%+ as strong." UNDER20's pinged flags whose projection is under 70% of the line ping as "🔵⭐ UNDER";
  the rest stay "🔵 UNDER". No flag is added or removed.
- **The side-by-side tracks UNDER30P:** UNDER20P's flags with projection < 0.70 × the line. It is registered at the
  deploy time, so the 30% cut's own forward record starts clean.

# AMENDMENT 4: ping only 30–50% below (2026-10-28, about 22:30 UTC, before code)
**User:** "only ping when it's 30%+ below ... is there an optimal range, say 30–50% below? test all ranges."
`nba_under_grid.py` (post-hoc; −150 or better, not threes; 35 ranges tried).

| % below the line | 2023-24 | 2024-25 |
|---|---|---|
| 20–25 / 25–30 | +6.4% / +0.6% | +3.8% / +5.1% |
| 30–35 / 35–40 / 40–45 / 45–50 | +15.7 / +13.3 / +15.9 / +36.7% | +21.5 / +6.7 / +2.9 / +20.5% |
| 50–60 / 60+ | +6.4% (n 101) / n < 40 | +2.2% (n 50) / n < 30 |
| **30–50** | **1,022, +16.8%** | **710, +15.0%** (90%: +9.3%, +20.9%) |
| 30–max | 1,181, +15.2% | 765, +14.2% |
| 25–50 | 1,968, +9.0% | 1,414, +10.1% |

- **Reading:** the 30% floor is what matters. The cap barely does; past 50% below is weaker and rare, likely where our
  projection is off.
- **User:** ping 30–50% below (−150 or better, not threes). Every other flag is recorded silently.
- The pings are "🔵 UNDER" (amendment 3's star is dropped, since every ping is now 30%+).
- **UNDER3050** (the pinged subset) is added to the side-by-side. UNDER20, UNDER20P and UNDER30P stay, so the forward
  record compares them.

# AMENDMENT 5: the same ranges for overs (2026-10-28, about 22:45 UTC; information)
**User:** "test the same ranges for the overs." (`nba_over_grid.py`: the over when our projection is X% above the line,
best FanDuel/DraftKings over, 2023-24 and 2024-25 tip lines; 46 ranges.)

| overs −150 or better, not threes | 2023-24 | 2024-25 |
|---|---|---|
| 0–10% above | 25,259, −8.4% | 23,794, −5.7% |
| 10–20% | −3.4% | −2.4% |
| 20–25% / 25–30% / 30–35% | −1.8 / −2.3 / +0.9% | +0.6 / −1.7 / −4.9% |
| 35–40% / 40–50% / 50–75% | −7.6 / −0.5 / +0.4% | −1.5 / −4.2 / −2.4% |
| best range by the worse season (20–35%) | 7,442, −1.5% | 6,976, −1.2% |

- With all overs (threes and heavy prices included), every range runs about −2% to −3%.
- **No over range is positive in both seasons.**
- **Reading:** the book's no-vig over runs above the actual over rate (49.2% against 47.3–48.5%), so overs carry the
  public's shading on top of the vig. A projection far above the line is more often our miss. A projection far below
  catches lines the book is slow to lower.
- No over rule is added.

# AMENDMENT 6: the only pings (2026-10-28, about 23:00 UTC)
The user made UNDER20's pinged flags (amendment 4) the only rule that pings the phone; every other rule is shadow-tracked
(`NBA_SXS_PREREG.md`, note on phone routing).

# AMENDMENT 7: the pinged unders without injury minutes bumps (2026-10-29, about 01:50 UTC, before code; information)
**User:** "what happens if you don't include those who are getting a jump in minutes due to injury, like Capela did
tonight?" (Capela: a backup center with Sengun and Adams out; our projection gave him 11 minutes. He came off the bench
and played 22.)

`nba_under_inj.py`, on amendment 4's rows: 2023-24 and 2024-25 tip lines, under −150 or better, not threes, 30–50%
below the line (the live ping set). The backtest reads tonight's outs from the box score (live: the injury report) and
the starters from NBA.com's final lineups (live: the lineup tab).

**The bump, four ways, each reported alone (a flag can be in several):**
- **B1, new starter:** he starts tonight and is not in his team's usual five.
- **B2, starter out:** one of his team's usual five (not him) is out.
- **B3, same-position teammate out:** an out teammate who averages 20+ minutes shares a position letter with him.
- **B4, our projection gives him more:** V3 minutes ≥ his last-10 mean + 3.
- **Any of B1–B3** ("an injury bump").

**Also shown, hindsight only (not usable live):** he played 5+ minutes over his last-10 mean.

**Reported:** count and ROI (90% bootstrap interval) with each excluded and with only them, per season, at the best
FanDuel/DraftKings price and at FanDuel's own. Post-hoc, so a split that looks better is a candidate for the forward
record, not a live change. No live change without the user.

**Result (2026-10-29, about 01:50 UTC).** Best FanDuel/DraftKings price, 2023-24 | 2024-25:

| 30–50% unders | excluded | only these |
|---|---|---|
| all | 1,022, +16.8% \| 710, +15.0% | |
| B1 new starter | 413, +14.3% \| 338, +11.1% | 609, +18.4% \| 372, +18.5% |
| B2 starter out | 330, +11.6% \| 221, +14.3% | 692, +19.2% \| 489, +15.3% |
| B3 same-position teammate out | 499, +12.4% \| 323, +12.3% | 523, +20.9% \| 387, +17.3% |
| B4 projection +3 min | 771, +14.1% \| 532, +15.4% | 251, +25.1% \| 178, +13.9% |
| any of B1–B3 | 229, +15.6% \| 124, +25.8% | 793, +17.1% \| 586, +12.7% |
| hindsight: played 5+ over his last-10 | 524, +35.9% \| 385, +37.8% | 498, −3.4% \| 325, −12.0% |

- At FanDuel's own price (417 | 403 flags) the picture is the same: new starters +11.9% | +13.9% against +12.3% | +13.5%
  without them; any bump +11.5% | +9.5% against +13.6% | +31.9% without (n 124 | 76).
- **Reading:**
  - Most of the ping set (78–83%) is injury-bump flags: the book raises the line when a teammate sits, and our
    projection does not follow it all the way.
  - Those flags won about as well as the rest. New starters (Capela's case) and same-position fill-ins did *better* in
    both seasons. Only "any of B1–B3" differs by season, and it flips (+1.5 points one year, −13 the other). Every
    interval overlaps.
  - The real risk is the jump actually happening (5+ minutes over his norm: −3% | −12%), but none of the tip-time
    signals picks those nights out.
  - Dropping the bumps would cut the pings about 80% without a consistent gain. No live change; the user decides.

**Check after the result (2026-10-29, about 02:10 UTC; post-hoc).** The user asked why so few flags have no bump.
- **Base rates, all players with a line:** a usual starter out on his team 42% | 49%; any of B1–B3 51% | 57%; a new
  starter 10% | 11%. In the ping set those are 68% | 69%, 78% | 83% and 60% | 52%. A teammate sitting raises the line
  more than our projection rises, which puts the player 30–50% below. Spot checks of 24 flags read correctly
  (Valanciunas with Sabonis out, Bitadze with Carter out, Eubanks with Nurkić out).
- **"Any bump" was loose:** B2 counts any usual starter, even one who doesn't touch his stat. That left a small, noisy
  no-bump group (229 | 124).
- **B5, Capela-type** (a new starter, or a usual starter sharing his position letter is out; defined after the result):
  with B5 +18.3% | +16.8% (703 | 467); without B5 +13.5% | +11.5% (319 | 243). B5 is better in both seasons.
- **A research-only gap:** before a player plays for his new team, he can show as out for his old one (Hartenstein for
  the Knicks on 2024-10-25). It touches only teams' first 3 games: 28 | 48 flags. Live outs come from the injury report.

# AMENDMENT 8: why the unders lose, a search for missing context (2026-10-29, about 06:15 UTC, before code)
**User:** "test all other things to get it better ... figure out why we're losing the bets in the backtest."

**Design:** look for losing patterns on 2023-24, then test the few best on 2024-25 only. `nba_under_losses.py`.
- **Discovery set:** 2023-24 UNDER20 flags 20%+ below the line, under −150 or better, not threes (3,916 bets,
  +7.7%). It is wider than the ping set, for power.
- **Held-out:** 2024-25, both the ping set (30–50% below, 710 bets) and the 20%+ set (2,819).
- **Prices and outcomes:** as amendment 4 (best FanDuel/DraftKings under at tip).

**Information first:**
- For each bet: the minutes miss (actual − V3) and the rate miss (actual per minute ÷ our rate).
- The share of losses where he played 5+ minutes over V3, against the share where his per-minute production beat our
  rate by 25%+.

**Features (known at tip − 30; the starter flag comes from NBA.com's final five, the lineup tab live):**
- **A, minutes and role:**
  - A1 V3 − his last-10 mean minutes; A2 his last game's minutes − V3; A3 his last-3 mean − V3;
  - A4 the spread (sd) of his last-10 minutes; A5 his games this season; A6 he starts tonight; A7 a Capela-type bump
    (amendment 7's B5).
- **B, rates and form:**
  - B1 this season's share of his rate (this-season minutes ÷ (that + 150));
  - B2 his last-5 production per minute in the market's stats ÷ our rate;
  - B3 the line ÷ his season average of the stat (this season with 3+ games, else last season);
  - B4 the line ÷ his last-5 average; B5 his under rate at this line over his last 10 games.
- **C, market:**
  - C1 the under price; C2 the book's no-vig over (FanDuel, else DraftKings);
  - C3 BetMGM's and Caesars' main line (the rung with prices nearest even) − ours, their mean;
  - C4 the % below the line; C5 the line; C6 the market (points, rebounds, assists, the combos).
- **D, game:**
  - D1 his team's implied points (the sum of its players' points lines at tip); D2 the implied spread (his team's
    sum − the opponent's); D3 its size;
  - D4 rest days and back-to-back; D5 the team's game index.
- **E, opponent:**
  - E1 what the opponent allowed per game in the market's stats to his position group this season before tonight
    (5+ games), ÷ the league's average;
  - E2 both teams' shot volume per game (FGA + 0.44 FTA, this season before tonight).

**Choosing candidates (2023-24 only):**
- Each numeric feature is cut at its terciles; binary and categorical features by value.
- A bin is a candidate when its ROI is 8+ points below the rest's and the bootstrap (1,000) puts that gap above 0 in
  95%+ of draws.
- The 5 largest gaps go to the held-out test.
- **Plus one combined model:** a logistic regression of "the under wins" on every feature (standardized, median-filled,
  C = 1) fit on the discovery set. It drops the bets in its lowest predicted third, with the cut point taken from
  2023-24.

**Held-out test (2024-25):** a candidate passes when dropping its bin
1. on the ping set leaves the kept bets 2+ points above all bets, and the dropped bets 8+ points below the kept; and
2. on the 20%+ set leaves the dropped bets 4+ points below the kept.

**After:** a pass is reported with bootstrap intervals, to be shadow-tracked first. The live pings change only if the
user says so.

**Result (2026-10-29, about 06:30 UTC).** Discovery: 3,916 bets, +7.7%. Held-out 2024-25: 2,819, +6.9%; ping set
710, +15.0%.
- **Why they lose (information):** about 2 in 3 losses fit each of the first two patterns, and about a third fit both.
  - Losses: he played 6–7 minutes over V3 (5+ over in 65% | 58%), and his per-minute production beat our rate by a
    median 38% (25%+ over in 66% | 70%).
  - Wins: +2 minutes over V3 and 0.81× our rate.
  - Even the winners outplayed V3's minutes. A projection far below the line selects players whose V3 minutes run low.
- **Candidates (2023-24):**
  - Line ÷ last-5 average, 1.06–1.42: −1.4% against +12.2%.
  - % below the line, 23–29%: +0.7%. The ping set's 30% floor already drops it, so it fails rule 1.
  - Team game index > 56: +2.1%.
  - The combined model's top weights: line ÷ last-5 +0.33, this season's share of the rate +0.25, V3 − last-10 +0.20.
- **Held-out (2024-25), dropping the bin:**

| | ping set kept | ping set dropped | 20%+ kept | 20%+ dropped | |
|---|---|---|---|---|---|
| line ÷ last-5 avg 1.06–1.42 | 498, +20.2% | 212, +2.7% | +10.0% | 982, +1.1% | **PASS** |
| % below 23–29% | 710, +15.0% | 0 | +8.8% | 997, +3.4% | FAIL (rule 1) |
| team game index > 56 | 441, +20.1% | 269, +6.6% | +10.5% | 1,115, +1.4% | **PASS** |
| combined model, lowest third | 354, +18.8% | 356, +11.3% | +9.6% | 1,387, +4.1% | FAIL |

- **Shapes (after the result, both seasons, ping set):**
  - **Line ÷ last-5 average:**
    - The steady losing zone is 1.2–1.42 (the line 20–42% above his last 5): −11.9% | −7.2%, and the 20%+ set
      +1.2% | −1.4%.
    - 1.06–1.2 flips (−5.2% | +20.1%).
    - At or below his last 5 the unders win (+13–29%); 1.7+ wins most (+36% | +22%).
  - **Game index:**
    - The losses sit in the last stretch, games 67+: ping set +5.4% | +1.0%, 20%+ set −3.4% | +2.6%.
    - Games 57–66 were fine in the ping sets (+16.9% | +16.4%).
- **Both filters together:** the ping set keeps 527, +24.0% | 306, +22.6%. The dropped bets still made +9.1% | +9.2%,
  so profit falls (+171 → +126 units | +107 → +69).
- **Nothing else separated wins from losses:**
  - game script (implied total and spread), the opponent's defense against his position, rest, starting, a bump;
  - the market (points +2.8% and assists +4.6% trail rebounds and PRA, about +12%, below the 8-point cut);
  - low-pace games (+2.4% against +10%, just under the cut);
  - other books above our line (−9.1%, but only 69 bets).
- 26 features and about 80 bins were screened, so the two passes are candidates, not proof. They go to the forward
  record first; the live pings change only if the user says so.

# AMENDMENT 9: the line filter goes live (2026-10-29, about 06:40 UTC, before code)
**User:** "make it live" (amendment 8's line filter, as tested).

- **The pings:** amendment 4's set (30–50% below, −150 or better, not threes), less every flag whose line ÷ his
  last-5 average is in (1.0564788482047636, 1.4166666666666667].
  - Those are the 2023-24 tercile edges from amendment 8, unrounded.
  - His last 5 are his last 5 games played, any team, this season and last (`nba_boost.BoostData.his`), summed over
    the market's stats.
  - With no games or a zero average, the flag is not skipped (as in the test, where a missing value was never dropped).
- **Recorded:** every UNDER20 flag, as now. Its note gains "l5 R" (the ratio, 6 decimals) so the Pickz board can apply
  the same rule.
- **Side-by-side:**
  - UNDER3050 stays as registered: the unfiltered pings, now shadow.
  - **UNDER3050L**, the new pings, is registered at the deploy time.
  - The two forward records compare the filter.
- **Expected, from the backtest (2024-25):** 64.6% hits and +20% on 500 bets, against 62.0% and +15% on 710.

# AMENDMENT 10: flagging earlier than tip − 30 (2026-10-29, about 21:40 UTC, before code)
**User:** "have we tested the accuracy of flagging plays an hour or 2 or 3 or 4 or 5 hours ahead of tip?" No:
2023-25's odds were captured once per game, at about tip − 30. "Yes run the replay and set up the tracking."

**Rules: UNDER3050L_E60, _E120, _E180, _E240, _E300.**
- Each is UNDER3050L's ping set (amendment 9), judged at FanDuel's first observation (a full or targeted poll) at or
  after tip − k minutes and before tip − k + 30. With no observation in that window, none.
- Each uses FanDuel's board and the official report as of that moment, as UNDER20 does at its tick.
- They are side-by-side rules that fire on observations, so `nba_replay.TICKS` and every registered fingerprint stay
  as they are.
- Silent: nothing pings.

**Development replay (information):**
- 2026-10-22 to 2026-10-28, from the logged quotes and reports, every early rule plus UNDER3050L at tip − 30, run on
  the Mac from copies of the VM's stores.
- **Reported per rule:**
  - flags, and their overlap with tip − 30's;
  - CLV at FanDuel's close (the closing no-vig × our price − 1);
  - the share whose line closed lower or whose under got pricier, against higher or cheaper;
  - wins and ROI.
- It is about 57 games, so the hit rates are anecdotes and CLV is the measure.

**Forward:**
- Registered at the deploy time and replayed nightly with every rule. Judged like every rule (CLV and ROI, 200+
  signals over 10+ dates) against UNDER3050L.
- No change to the live pings without the user.
