# PRE-REGISTRATION — the WNBA pricing machinery, run unchanged on NBA real lines

Written and committed **before** the data fetch and the test script exist. 2026-10-22.

## The question
`nba_flags` decides a bet with one comparison (`proj − line ≥ MARGIN`) and never looks at the
price. The WNBA engine prices every bet: elevated-role sample → minutes-honest rescale → hit rate
→ credibility shrink toward the book's implied probability → EV bar → portfolio selection. **Does
that machinery, as built, find edge on NBA lines?** To answer it rather than re-implement it, the
test **calls the WNBA's own functions** — `wnba_tonight.prop_edges`, `wnba_alert.position_compat`,
`wnba_slip.current_selection` — unmodified. NBA settings are overridden in the test process only;
the frozen files are not edited.

## Universe — the WOWY tier, identical to `nba_margin_refit.py`
Walk-forward over franchise games, 400-day pool. X = highest-minutes absent player with ≥10 prior
apps, trailing-10 ≥ 28.0 min, last app ≤ 12 days ago; absence game 1 or 2. B = in tonight's box,
≥ 5 prior apps, ≥ 2 prior games without X (since X's first app) and ≥ 3 with.
The first-occurrence `n1` tier is excluded, as it is from the WNBA's firm record.

## Inputs to the WNBA functions, built from NBA data
- `log`: B's prior apps for this franchise in the pool window — min, pts, reb, ast, pra, pts_reb,
  pts_ast, reb_ast, **fga, fta, fg3a** (refetched: the existing NBA logs dropped them, and the
  conviction gate cannot pass without `d_fga`).
- `w`: with/without-X means for those keys, plus the without-X values (the role-flip path).
- `proj_min`: exactly `wnba_alert` — `with_min + pw·(without_min − with_min)`, raised to the median
  of B's last 5 games (>8 min) if higher; skipped if the bump ≤ 0.3 and `pw < 0.6`.
  `pw = position_compat(pos_B, [pos_X])`, positions from stats.nba.com's player index.
- `out_logs`: X's appearance dates (drives `_play_prob`).
- Lines: `posted_props` returns `{stat: {line: (best_over, best_under)}}` from
  `basketball_nba_odds_hist.sqlite`, **FanDuel and DraftKings only** — the two books `nba_lines`
  collects and that can be executed. Best price across the two. Two-sided rungs only.

## The only NBA departures from the WNBA settings, each with its reason
| setting | WNBA | here | why |
|---|---|---|---|
| `ROLE_FLOOR` | 22.0 | **26.4** | the WNBA code's own comment: 22 is scaled for a 40-min game; ×48/40 |
| volume layer `VOL_LIVE` | True | **off** | its FGA thresholds are WNBA-calibrated (`PRIMARY_FGA=13` is a secondary option in the NBA); a separate mechanism needing its own test |
| guard-rebound gate | on | **off** (`pos=None`) | the WNBA code says "do NOT port to the NBA" |
| DvP nudge | on | **off** (`opp=None`) | there is no NBA DvP model |
| everything else | — | **unchanged** | k=11/14, EV bars 0.10/0.20, 1.35×/2.2× caps, conviction, direction, thin-sample, band-pilot, play-prob, mis-scrape guards, selection |

## Counting — the WNBA record definition
Overs only; band-pilot spots excluded (shadow in the WNBA too); **base rung only** (the line the
WNBA anchored on, `orig_line`); then `current_selection` (thin-sample, correlated-stack, top-2
disjoint per team-game, favourite-first). Flat 1 unit at the recorded price.

## Primary verdict — Arm T (transfer, nothing fitted)
All stats pooled. Date-clustered bootstrap 95% CI (4,000 reps, seed 7); halves split at 2024-10-29.

| verdict | condition | consequence |
|---|---|---|
| **KILL** | pooled ROI ≤ 0, or halves disagree in sign | the priced tier is shadow-only |
| **B** | pooled ROI > 0, both halves > 0, CI lower bound ≤ 0 | shadow-only; accrue forward |
| **A** | CI lower bound > 0 | may write PAPER bets |
| thin | n < 100 | treated as KILL for wiring |

**It must also beat, on the same universe and the same two books:** the always-over null (main
rung), and the shipped margin rule. Beating neither is a KILL regardless of sign.

## Secondary — information only, not decisive
Per-stat breakdown; an EV-bar sweep fitted on the first half and read on the second; a k
sensitivity (recomputing the shrink from the returned hit rate and n).

## Known limits, stated now
- Prices are tip snapshots: this measures the close, not the news window.
- Absence is inferred from the box score; live uses the injury report.
- Positions are each player's index position applied historically; a player missing from the
  index defaults to `F`, as `position_compat` already does.
- Props on a DNP void, so grading only players who played is approximately right, not exact.

---

# RESULT — appended after the run, 2026-10-22. Nothing above this line was edited.

`nba_pricing_realline.py` (controls first: a role that expands against a soft line flags at EV
+0.510, matching hand arithmetic; a flat role is refused by the conviction gate; four same-team
overs reduce to two). Universe: 19,912 WOWY-tier candidates, 6,430 with FD/DK lines → 1,967
priced base-rung overs → **1,186 after `current_selection`**.

| | n | dates | hit% | ROI | 95% CI |
|---|---|---|---|---|---|
| **Arm T, pooled** | 1,186 | 286 | 50.0% | **−3.46%** | [−8.80, +1.99] |
| before 2024-10-29 | 552 | 140 | 49.6% | −4.41% | [−12.18, +3.06] |
| from 2024-10-29 | 634 | 146 | 50.3% | −2.64% | [−10.24, +4.72] |
| always-over null, same candidates | 35,353 | 303 | 48.4% | −6.97% | [−8.85, −5.14] |
| shipped margin rule, same candidates | 1,565 | 271 | 50.1% | −4.85% | [−10.73, +1.14] |

## Verdict: **KILL** (pooled ROI ≤ 0). The priced tier is shadow-only.

The machinery is *more informative* than the margin rule (+1.4 pts) and the null (+3.5 pts) — and
still loses at the close. The core `elevated` path is **−6.33%, CI [−12.45, −0.58]**: reliably
negative, as bad as the null.

### Secondary (pre-registered, information only)
- **Overconfident by 10-17 points of probability.** EV 0.10-0.20: model 59.6% vs realized 49.4%;
  0.20-0.35: 65.6% vs 48.3%; ≥0.35: 74.5% vs 55.8%. The WNBA's own known flaw (64% vs 51%),
  larger here: elevated-role games flatter the hit rate, and EV selection adds a winner's curse.
- **No EV bar rescues it.** Every bar loses on the first half; the first half's choice (0.45)
  reads −11.07% on the second.
- **A heavier shrink does not either.** k = 11 / 20 / 40 / 80 → −3.38 / −3.61 / −4.15 / −1.44%.

### Noticed, NOT claimed (post-hoc subsets — each needs its own prereg and forward data)
`role_flip` basis +10.58% (n=195, CI [−3.69, +25.90]); assists +6.81% (n=201). Both are cuts
chosen after seeing the results.

### What this test cannot see
Prices are tip snapshots. The WNBA thesis is SPEED — bet the news before the book moves. A model
that loses at the close can still win at the news, and only forward data can show it: the priced
tier now logs to the shadow table, and `nba_lines.quotes` records every price move, so each shadow
flag can be scored against the line it beat (or didn't) by tip.
