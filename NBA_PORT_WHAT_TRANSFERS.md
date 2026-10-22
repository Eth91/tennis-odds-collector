# What the WNBA tracked model is, and what the NBA port actually ported

Research pass, 2026-10-22, day 2 of the NBA season. Companion to the real-line arbiter
(`nba_margin_refit.py`) run the same day. Every claim below is cited to code.

---

## 1. The WNBA model in one sentence

> **The gap between ELEVATED-ROLE production and a line the book anchored to the SEASON AVERAGE.**
> — `wnba_tonight.prop_edges` docstring, `wnba_tonight.py:515`

The book prices a player off who they have been. An injury makes them someone else for one
night. The model's whole claim is that the book is slow to that, and the edge is *priced*, not
*thesis-shaped* — see `project_wnba_beneficiary_drivers` (big WOWY/usage/minutes deltas are
monotone ANTI-signals). This matters enormously for the port: the thing that makes money is the
price machinery, not the beneficiary idea.

## 2. The eight mechanisms, in execution order

| # | mechanism | where | why it exists |
|---|---|---|---|
| 1 | absence → beneficiary via WOWY, needs ≥2 games without | `wnba_alert.py` (`W.wowy_multi` ~:286) | the trigger |
| 2 | minutes projection; bump must exceed 0.3 | `wnba_alert.py` | kills noise flags |
| 3 | **elevated sample**: player's own games at `min ≥ max(proj−4, ROLE_FLOOR=22)` | `wnba_tonight.py:529` | judge them in the role they're ABOUT to play, not their season |
| 4 | **minutes-honest rescaling**: each elevated game scaled to tonight's projected minutes, **cap 1.35×** (2.2× in breakout fallback) | `wnba_tonight.py:546-556` | without it the model cherry-picks a player's 26-min games to project a 19-min role |
| 5 | **credibility shrinkage toward the BOOK's implied probability, k=11** | `wnba_tonight.py:540-544`, `:645`, `:752` | raised 6→11 because the empirical hit read **64% shrunk vs 51% realized** — favourable-role games regress |
| 6 | **EV bar**: over 0.10 / under 0.04 / ladder 0.20 / volume 0.07 | `wnba_tonight.py:305-333` | asymmetric on purpose: unders on reduced roles beat baseline +6-9pts, overs on elevated roles regress |
| 7 | portfolio + veto: thin-sample guard (n<7 & jump>10, unless cold-start margin ≥5), won't post an over on a stat that DROPS without the out player, one-per-P/R/A pool, TOP-2 disjoint per team-game, `suppressed()` | `wnba_tonight.py:309-311`, `:638`, `wnba_slip.py` | stops correlated stacking and premise-break bets |
| 8 | record discipline: graded **overs** → drop tier `n1` → `current_selection` → base rung only | `wnba_headline.py:19-22` | the raw pool is NOT the record |

**The load-bearing parts are 3-6.** 1-2 find a candidate; 3-6 decide whether it is a *bet*.
Step 5 is the subtle one: the model never trusts its own hit rate. It blends it with the book's
implied probability, weighted by how much evidence it actually has.

## 3. What the NBA port implements

`nba_flags.py:175`, in full:

```python
if proj - line < MARGIN[stat]:
    continue
```

That is the entire bet decision. `MARGIN = {"pra": 5.0, "pts": 3.0, "reb": 2.0}`
(`nba_flags.py:42`), and `proj = rates[stat] * (base_min + d_min)` (`:170`).

So of the eight mechanisms, the NBA port has **1, 2, and a fragment of 8.** It is missing the
elevated sample, the minutes-honest cap, the shrinkage, the EV bar, and the portfolio layer.

### The consequence: price never enters the decision

Grep `nba_flags.py` for `price` — every hit is logging or line-selection. The best over price
across books is fetched (`:102`), used to pick the main rung (`:130`), and written into the
ledger (`:178`) — **and never consulted about whether to bet.** The engine takes a fixed
projection margin at whatever odds the book is offering.

That is the mechanical reason the real-line arbiter found nothing today: you cannot beat a
6.95% median hold with a rule that does not look at the price. The null is −6.56%
(CI [−8.76, −4.46], excludes zero) and no margin cell clears it with an interval that excludes
zero. **The NBA port never ported the model. It ported the thesis** — and the thesis is the half
that `project_wnba_beneficiary_drivers` already showed does not pay on its own.

## 4. The data gap, which is worse than it looks

`nba_gamelogs.sqlite.logs` persists **5 stat columns**: `min, pts, reb, ast, fg3m`
(`nba_beneficiary_backtest.py:45-47`).

`stats.nba.com/stats/leaguegamelog` returns **32 columns** (probed live from this Mac,
2026-10-22, season 2025-26, 26,651 rows):

```
FGM FGA FG_PCT FG3M FG3A FG3_PCT FTM FTA FT_PCT OREB DREB REB AST STL BLK TOV PF PTS PLUS_MINUS ...
```

The fetch reads the response and throws 27 of them away — including **FGA, FTA and FG3A.**

Why that specific loss is fatal: the WNBA model's per-stat decision map is

```python
STAT_DRIVER = {"points": "fga", "rebounds": "reb", "assists": "ast", "pra": "fga", ...}
# "FGA is a POINTS driver only; it's noise for reb/ast."   wnba_tonight.py:345-349
```

**FGA is the primary points driver**, and the volume layer (`PRIMARY_FGA = 13.0`,
`wnba_tonight.py:333`) is built entirely on it — it is what separates a room-to-grow role player
(who absorbs the vacated shots) from a primary option (whose shot count does not rise off an
injury, the Mabrey case that lost −38% on real lines). The NBA port cannot run either, because
the column is not in the database. Not unavailable — **discarded on ingest.**

## 5. What NBA adds that the WNBA can never have

All four probed live and working from this Mac today:

| endpoint | cols | what it gives |
|---|---|---|
| `leaguedashplayerstats&MeasureType=Usage` | 53 | **`USG_PCT`**, `PCT_AST`, `PCT_PTS` |
| `...=Advanced` | 79 | `AST_PCT`, `REB_PCT`, `OREB_PCT`, `DREB_PCT`, `OFF_RATING`, `EFG_PCT`, `POSS` |
| `...=Scoring` | 53 | `PCT_PTS_PAINT/3PT/FT`, **`PCT_UAST_FGM`** (self-created vs assisted) |
| `leaguedashptstats&PtMeasureType=Passing` | 18 | `AST_POINTS_CREATED`, potential assists |

`reference_wnba_advanced_stats` records that the WNBA has none of this and that **FGA is the best
usage signal available**. NBA measures directly what the WNBA model has to infer.

### The one that actually matters: `USAGE_RATE_ADJ`

```python
USAGE_RATE_ADJ = False     # OFF pending a proper gate (2026-08-06).   wnba_tonight.py:414
```

Read `_usage_mult`'s docstring (`wnba_tonight.py:446`). It exists because:

> The beneficiary path selects on a MINUTES bump and projects from the player's own elevated
> games — which include the games the out player PLAYED. **A player who absorbs usage without
> absorbing court time is therefore invisible.** Carleton with Barker: 30.24 min / 13.76 pts.
> Without: 31.00 min / 18.75 pts. That is +0.76 minutes and +5.0 points — a 33% jump in
> per-minute scoring, the largest on the team, and the model ranked four smaller MINUTES bumps
> above it.

It is switched **off** because the only way to estimate it in the WNBA is a rate ratio off a 3-5
game WOWY split, credibility-shrunk and capped [0.85, 1.30] — too noisy to gate properly.

**NBA has `USG_PCT` as a measured quantity.** This is the single place where the NBA does not
merely port the WNBA model but *repairs a component the WNBA had to disable.* It is the highest-
value item on this list by a distance.

## 6. Order of work (and why this order)

The temptation is to add NBA's rich stats first, because that part is fun and the data is sitting
there. That would be adding features to a margin screen — more precise projections feeding a rule
that still ignores the price.

1. **Port mechanisms 3-6** into the NBA path: elevated sample, minutes-honest cap, shrinkage
   toward the book (k=11 is a WNBA fit — re-derive, do not inherit), EV bar. This is the only
   change that could plausibly beat the hold, because it is the only one that prices the bet.
2. **Stop discarding columns.** Re-fetch with all 32 (one call per season, the fetch already
   exists) → FGA/FTA/FG3A → the points driver and the room-to-grow volume tier become runnable.
3. **Then** layer `USG_PCT` and turn on the usage adjustment the WNBA could not.
4. **Re-measure on real lines** with `nba_margin_refit.py` after each step, holdout untouched.
   The EV bar replaces `MARGIN` as the thing being fitted.

### Constraints to respect
- `stats.nba.com` is **Mac-only** (blocks CI/datacenter). Mac produces lookup tables, VM consumes.
  That hand-off has broken twice — see `reference_wnba_line_shopping`.
- Real-line odds history (`basketball_nba_odds_hist.sqlite`) runs **2023-05-04 → 2025-06-23**,
  2.0M rows, 10 markets. **The 2025-26 season has game logs but NO odds** (`reference_odds_api_key_gone`:
  no API key since 8/24), so it cannot serve as a real-line holdout. Forward paper from today is
  the only clean out-of-sample left.
- Do **not** port the WNBA guard-rebound gate (`project_nba_port`) — NBA guard-forwards genuinely
  rebound.
- `nba_injuries.json` last wrote **2026-08-14**. The trigger feed for all of this is dead; fix
  before anything downstream is meaningful.

## 7. Status of the claims here

Mechanisms and line numbers: read from code today. Endpoint columns: probed live today.
The real-line verdict: `nba_margin_refit.py` + `nba_margin_ci.py`, date-clustered bootstrap,
every positive cell's 95% CI crosses zero. **Nothing here is a validated NBA edge** — it is a
diagnosis of why the port has not been tested on its merits yet, and the order that would test it.
