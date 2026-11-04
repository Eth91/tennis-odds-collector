# PRE-REGISTRATION: how the books reprice teammates after an official Out (injury flagger rebuild, Step 1)

**Written:** 2026-11-04, before any analysis. The data's schemas and poll cadence were inspected first: the request
asked for that, and no outcome was looked at.

**User:** "Write and execute a rigorous, read-only test plan for Step 1 of the NBA injury flagger rebuild." The thesis
being checked is that an injury edge, if there is one, lives in the minutes between the official report and the books
repricing teammates, and in one book lagging the other. Step 1 only measures whether that window exists. It's
descriptive and makes no bets. `nba_injury_reaction.py`, Mac only.

## Data (read-only copies; nothing on the VM changes)
- **Source:** the VM's nightly backup of 2026-11-03 09:56 UTC (`~/backups/nba/*.20261103.sqlite.gz`), copied to
  `.projdata/vm_backup_20261103/`. The SHA-256 of every gz matched the backup's manifest.
- **`nba_lines` quotes:** an append-only change log since 2026-10-22. A row is written when a rung (player, stat, line,
  side) is first seen, when its price changes, or when it's pulled (odds NULL, on a fully successful fetch only).
- **`nba_lines` cycles:** one row per book per fetch, with its status.
- **`nba_news` reports:** each official report's `published_at`, the time our poller first found the PDF, about 4 s
  after each :00/:15/:30/:45 mark.
- **`nba_news` snapshots:** every player row of every report.
- **`nba_news` news_items:** X, Bluesky and Rotowire items with `detected_at`.
- **`nba_matchup` player_games:** box scores, for minutes, team and the first game of an absence.
- **Coverage:** quotes from 2026-10-22 09:34 to 2026-11-03 03:12 UTC (93 games); reports 2026-10-22 to 2026-11-03
  (1,133).

## Definitions
- **Observation:** a book's fetch with status `ok`.
  - A `game` fetch (a refresh of chosen games) counts only for the games it wrote a quote row for.
  - `partial`, `stale` (DraftKings snapshot too old) and `no_lines` fetches are not observations.
  - The board at an observation is each rung's latest quote row at or before it; NULL odds means pulled.
- **Main line** of (book, player, stat) at an observation: among rungs with both sides offered, the one whose no-vig
  over is closest to 50%. No-vig over = (1/over) ÷ (1/over + 1/under).
- **Fresh Out:** a player listed Out for a game in report R who was not Out for that game in the previous report
  that listed his team's game.
  - His status in that previous report is his **prior status**: not listed, Available/Probable, Questionable or
    Doubtful.
- **Qualifying event:** (report, game, team) with at least one fresh Out who meets all of:
  - his team's game tips 30+ minutes after `published_at`;
  - he played (minutes > 0) in his team's most recent game this season before that date, so this is the first game
    of an absence;
  - he averaged 15+ minutes in his games this season before that date (2+ games).
  - Fresh Outs that fail these are counted and described, not analyzed.
- **Affected teammates:** players of the same team (from this season's box scores) with a two-sided main line on the
  book at the baseline.
  - Markets: points, rebounds, assists, threes, PRA, points + rebounds, points + assists, rebounds + assists.
  - The Out players themselves are excluded. One unit is (event, book, player, market).
- **Baseline:** the book's last observation at or before `published_at`, no more than 30 minutes before it (else
  missing).
- **Close:** the book's last observation before tip, no more than 30 minutes before tip (else missing).
- **State of a prop at an observation:**
  - **stale:** the main line equals the baseline main line, and its no-vig over is within 3.0 points of the
    baseline's.
  - **moved:** a two-sided main line exists, but the main line differs or the no-vig over moved by 3.0+ points.
  - **pulled:** no two-sided rung for that player and market.
  - The 3.0 points sits above FanDuel's measured price jitter (amendment 27: p95 0.066 in decimal odds, about 1.7
    points at even money).
- **Mover:** a teammate prop whose close state is moved. A prop pulled at the close is counted apart.
- **Latency** (movers and pulls): an interval [L, U].
  - U is the first observation after `published_at` that isn't stale.
  - L is the last stale observation before U, or `published_at` if none.
- **Stale at t** (t = 1, 5, 15 minutes after `published_at`), among movers:
  - **confirmed stale:** a stale observation at or after `published_at` + t;
  - **confirmed moved:** U ≤ `published_at` + t;
  - **unknown:** otherwise. All three are reported, with their counts.
- **DraftKings lags FanDuel:** for a prop with both books' baselines whose FanDuel close state is moved, a DraftKings
  observation after FanDuel's U that is still stale.
  - **Its size,** at the first such DraftKings observation s, measured against FanDuel's latest observation at or before
    s:
    - (a) FanDuel's main line minus DraftKings' main line;
    - (b) the FanDuel-fair EV of DraftKings' price on the side FanDuel moved toward. That's p from FanDuel's two-sided
      rung at DraftKings' line (no-vig), times DraftKings' odds, minus 1. It's missing when FanDuel has no such rung,
      and those are counted.
  - FanDuel lagging DraftKings is measured the same way.
- **Control (background movement):** the same report times and windows, for props of teams with a game that date and
  no fresh Out or Doubtful in that report or the previous 12 reports (3 hours).
- **News before the report:** a news item (X, Bluesky, Rotowire) about the Out player for that game date, with status
  out or doubtful, detected before `published_at`.

## What's reported (by market, Out player, event, teammate and book where samples allow)
- Events, teammates and props, with every drop counted (no baseline, no close, unknown team, too close to tip).
- Baseline → close moves: the share moved, pulled and unchanged; the direction (up or down: main line, else no-vig
  over); the size (main-line units, no-vig points).
- Latency and the stale-at-1/5/15 tables, with the unknown share.
- DraftKings vs FanDuel: how often each lags, how long, and its size.
- Splits:
  - control vs teammates;
  - news before the report vs not;
  - prior status;
  - the Out player's minutes (28+ vs 15–28);
  - game today vs tomorrow.
- Limitations and confounders, written down as found.

## Step 2 go/no-go (fixed now)
- **Fewer than 30 qualifying events:** INSUFFICIENT, whatever the numbers.
- **WINDOW GO** needs all of:
  - among teammate movers on either book, 25%+ are confirmed stale at +5 minutes;
  - the movers' median move from baseline to close is 1.0+ unit in points or PRA (the main line), or 5+ no-vig points
    when the main line didn't change;
  - teammates' moved-by-close rate is 2×+ the control's.
- **DK-LAG GO** needs both:
  - DraftKings confirmed stale after FanDuel's move in 20%+ of FanDuel movers with a DraftKings baseline;
  - the median FanDuel-fair EV at the first lagging DraftKings observation is +3%+.
- **Both NO-GO:** this data shows no window to build a stale-line flagger on, and Step 2 doesn't go ahead as designed.

## Pass/fail for any flag rule built from Step 1 (fixed now; judged forward only)
- **Data:** only after the 2026-11-03 09:56 UTC backup, which is what Step 1 used.
- **The rule:** written as an amendment here before any forward data is examined, and unchanged after.
- **Sample:** 200+ qualifying flags across 10+ dates, one per (event, player, market, book), at the price available at
  flag time.
- **Primary:** mean CLV > 0, with the 95% bootstrap interval's low end > 0, resampling games.
  - CLV is the bet price against the same book's no-vig close at the bet line, or, if that rung is gone, at the close
    ladder's nearest two-sided rung.
- **Secondary:** mean CLV beats a same-time null (random props on the same books at the same flag times) by 3.0+
  points.
- **Pass:** primary and secondary. ROI is reported. An ROI whose 95% interval sits wholly below 0 is a fail on its own.
- **No live change without the user.**

## Result (2026-11-04 02:48 UTC, commit 36f0d21afa, after the analysis; the report is `NBA_INJURY_REACTION.md`)
- **Events:** 61 qualifying (from 646 fresh Outs). 42 had lines at the report; the other 19 were next-day games not yet
  posted. 32 games, 9 dates.
- **WINDOW: NO-GO.**
  - stale at +5 among movers 47.0% (passes);
  - median points/PRA main-line move 1.0 (passes);
  - teammates' moved-by-close rate 44.5% vs control 30.3%, 1.47× (fails 2×).
- **DK-LAG: NO-GO.**
  - DraftKings stale after FanDuel's move in 38.5% (passes);
  - median FanDuel-fair EV −5.7% on 87 measurable (fails).
  - 88 lags with a line gap couldn't be valued: FanDuel almost never has a two-sided rung at DraftKings' line. That's
    a flaw in this measure, noted, and the verdict isn't changed for it.
- **Exploratory, not part of the verdict:**
  - teammates changed 18% / 32% / 48% by 5 / 15 / 60 min on FanDuel, against 1% / 4% / 14% for the control;
  - FanDuel teammate overs still stale at FanDuel's first check gained line value on FanDuel's close (points-type
    +0.24, interval +0.07 to +0.46);
  - DraftKings' stale line after FanDuel moved ended behind DraftKings' own close (+0.37, interval +0.24 to +0.47).
  - Neither is netted against the vig.
- **Next step:** a pre-registered amendment (Step 2a) that prices line value, then re-scores those two candidates, then
  the forward 200-flag test above for any survivor.

## Amendment 1: Step 2a, pricing line value and re-scoring the two candidates (written before any of it is run)
**Written:** 2026-11-04 02:55 UTC (commit 3a2ddec3cb), before the conversion is fitted and before any candidate's converted CLV is computed. Only
schemas and row counts were looked at: matched FanDuel and DraftKings main lines run about 7–15k per market per season
for 2023-24 and 2024-25, and every historical line is a half-point. `nba_injury_step2a.py`, Mac only, read-only.

**User:** "Step 2a is the right next step, with one important safeguard: pre-register the amendment before examining
the converted results."

### The conversion: what one line point is worth
- **Data:**
  - `basketball_nba_odds_hist.sqlite` (the about −29 min snapshot), FanDuel and DraftKings two-sided main lines,
    matched to box scores by `nba_proj_data.load_hist_lines`;
  - regular seasons only;
  - 8 markets: points, rebounds, assists, threes, PRA, P+R, P+A, R+A.
- **Model:**
  - **The shape:** the stat X is negative binomial with mean μ and size k, where log k = a_m + b_m · log μ. That's two
    parameters per market m.
  - **The mean:** for a prop with main line L and no-vig over p, μ solves P(X > L) = p.
  - **Whole-number lines:** P(over) = P(X > L) / (1 − P(X = L)), so a push is excluded.
- **Fit:** a_m and b_m by maximum likelihood of the actual outcomes, on 2023-24 only. They're then frozen and recorded
  in the result.
- **Validation gate:** on 2024-25, per market, for line offsets d = −1 and +1:
  - **Predicted step:** the mean of P(X > L + d) − p.
  - **Realized step:** the share with X > L + d, minus the share with X > L.
  - **Usable:** the two steps agree within 1.5 points.
  - **Failure:** a market that fails either offset is **not evaluable**, and its bets are excluded and counted. A
    candidate with more than half its bets in failed markets is not evaluable at all.
  - **Reported, not gated:** d = ±2, and the conversion compared with the books' own no-vig prices where the
    2026-27 change log has a second two-sided rung.
- **Full CLV of a bet** (book, line Lb, side, decimal odds o), against the same book's close:
  - μ comes from the close main line and its no-vig over (Step 1's close);
  - CLV = P_conv(side at Lb) × o − 1. On the same line this is the close's own no-vig price;
  - **excluded and counted:** bets on props pulled at the close, and bets with no close.
  - This replaces the base pre-registration's "nearest two-sided rung" fallback for every CLV below and in any forward
    test of these candidates.

### The two candidates (decision-time rules; Step 1's events, teammates, checks, baselines and stale/moved definitions)
- **C, the primary: DraftKings stale after FanDuel moved its line.**
  - **Setup:** for a teammate prop with both books' baselines, tF is FanDuel's first check after the report whose
    two-sided main line differs from FanDuel's baseline main line.
  - **Flag:** DraftKings' first check after tF (before tip) is stale against DraftKings' baseline.
  - **The bet:** DraftKings at that check, at its main line and price. Over if FanDuel's line at tF is above
    FanDuel's baseline line, under if below.
  - **One flag per (event, player, market).** FanDuel's close is never used to pick the bet.
- **B, the secondary: FanDuel teammate overs, still stale.**
  - **Setup:** a teammate prop in points, PRA, P+R or P+A with a FanDuel baseline.
  - **Flag:** FanDuel's first check after the report comes within 15 min of it, and the prop is stale there.
  - **The bet:** FanDuel's over at that check's main line and over price. One flag per (event, player, market).

### Nulls (same times, control props as Step 1 defines them)
- **For B:**
  - control props in the same 4 markets;
  - stale at FanDuel's first check after the same report, if that check comes within 15 min;
  - the over at that check.
- **For C:**
  - control DraftKings props stale at each check time where C flagged;
  - each prop counts the mean of its over and under.

### Survival (in-sample, so it can only rule a candidate out)
- **Survives only if both:**
  - its mean full CLV > 0;
  - its mean full CLV is at least its null's + 3.0 points.
- **Reported for each:** a 95% game-clustered bootstrap interval (4,000 resamples, seed 7).
- **A dropped candidate stays dropped.** No variant of it is scored on this backup.
- **Reported as information only, not eligible to survive:**
  - C split by the size of FanDuel's line move (1 vs 2+);
  - C with FanDuel price-only moves (same line, 3+ no-vig points, side by the no-vig direction);
  - B split by news before the report.
- **A survivor goes to the forward test** under the base pre-registration's pass/fail:
  - data after the 2026-11-03 09:56 UTC backup only;
  - 200+ flags over 10+ dates;
  - the rule exactly as written here;
  - CLV as defined here, with the frozen conversion;
  - the null as defined here.
  - Shadow only; nothing live without the user.

### Amendment 1 result (2026-11-04 03:03 UTC, commit 7da9e0597e, after the run; the report is `NBA_INJURY_STEP2A.md`)
- **Conversion gate:** every market passed. The ±1 predicted and realized steps on 2024-25 agree within 0.65 points.
- **C: dropped.**
  - 179 flags scored, mean full CLV −5.4%, interval [−6.8, −4.1];
  - the null is −6.4%, so C is +1.0 points over it.
- **B: dropped.**
  - 564 flags scored, mean −4.0%, interval [−5.7, −2.1];
  - the null is −6.3%, so B is +2.3 points over it.
- **Neither goes to a forward test,** and no variant is re-scored on this backup.
