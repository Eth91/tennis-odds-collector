"""The WNBA pricing machinery, bound to NBA inputs — the ONE definition.

The real-line test (nba_pricing_realline.py) and the live engine (nba_flags.py, tier 'priced')
both import this module, so forward shadow is priced by exactly the code the backtest measured.

It does not re-implement anything. It calls the WNBA's own frozen functions —
wnba_tonight.prop_edges (elevated sample, minutes-honest rescale, hit rate, credibility shrink
toward the book, EV bar, conviction/direction/thin-sample/play-prob guards),
wnba_alert.position_compat, and wnba_slip.current_selection — and applies the four NBA
departures pre-registered in NBA_PRICING_PREREG.md as process-local overrides. No frozen file
is edited; importing this module changes those globals for the importing PROCESS only.

VERDICT ON REAL LINES (2026-10-22, at the close): KILL — pooled −3.46% over 1,186 bets, CI
[−8.80, +1.99]; better than the margin rule (−4.85%) and the null (−6.97%), still a loser; the
model is overconfident by ~10-17 points of probability. So the live tier is SHADOW-ONLY.
"""
from __future__ import annotations

import statistics as st

import wnba_alert as A
import wnba_slip as SL
import wnba_tonight as T

# ── the four pre-registered NBA departures (NBA_PRICING_PREREG.md), process-local ──
T.ROLE_FLOOR = 26.4          # WNBA 22.0 is scaled for a 40-min game; x 48/40
T.VOL_LIVE = False           # volume layer: WNBA-calibrated FGA thresholds; its own test
SL._sel_log = lambda: {}     # never read the WNBA's sticky-selection log for NBA rows
# guard-rebound gate off (pos=None) and DvP off (opp=None) — passed at the call below

KEYS = ("min", "pts", "reb", "ast", "fga", "fta", "fg3a", "pra", "pts_reb", "pts_ast", "reb_ast")
PROP_STATS = T.PROP_STATS     # points, rebounds, assists, pra, pts_reb, pts_ast, reb_ast


def row(mn, pts, reb, ast, fga, fta, fg3a):
    """One game in the shape prop_edges reads."""
    return {"min": float(mn), "pts": pts, "reb": reb, "ast": ast, "fga": fga, "fta": fta,
            "fg3a": fg3a, "pra": pts + reb + ast, "pts_reb": pts + reb, "pts_ast": pts + ast,
            "reb_ast": reb + ast}


def wowy_block(rows):
    return {k: {"mean": st.mean([r[k] for r in rows]) if rows else 0.0,
                "vals": [r[k] for r in rows]} for k in KEYS}


def wowy(b_in, b_out):
    """The with/without split vs X in the shape prop_edges reads."""
    return {"n_with": len(b_in), "n_without": len(b_out),
            "with": wowy_block(b_in), "without": wowy_block(b_out)}


def norm_pos(p):
    """stats.nba.com 'G-F' / 'F-C' / 'C-F' -> the WNBA table's 'GF' / 'FC' / 'CF'."""
    return (p or "").replace("-", "").upper()


def price(name, log_newest_first, w, pos_b, pos_x, x_dates, ladders):
    """wnba_alert's minutes logic, then wnba_tonight.prop_edges. Returns (spots, proj_min).

    log_newest_first: B's prior games (dicts from row(), plus date/game_id/matchup), NEWEST
    first — the order wnba_alert passes. ladders: {stat: {line: (best_over, best_under)}}."""
    pw = A.position_compat(norm_pos(pos_b), [norm_pos(pos_x)])
    with_min = w["with"]["min"]["mean"]
    proj = with_min + pw * (w["without"]["min"]["mean"] - with_min)
    recent5 = [g["min"] for g in log_newest_first[:5] if g["min"] > 8]
    if recent5:
        proj = max(proj, st.median(recent5))
    if proj - with_min <= 0.3 and pw < 0.6:
        return [], proj
    T.posted_props = lambda player, _l=ladders: _l
    return (T.prop_edges(name, log_newest_first, proj, w, None, None,
                         out_logs=[x_dates], opp=None, pos=None), proj)


def base_rung_overs(spots):
    """The WNBA record's counting rule: overs, not band pilots, not one-sided ladders, and only
    the base rung (the line the model anchored on)."""
    return [s for s in spots
            if s.get("side") == "over" and not s.get("band_pilot") and not s.get("alt_ladder")
            and abs(s["line"] - (s.get("orig_line") or -99)) <= 1e-6]


def select(rows):
    """wnba_slip.current_selection: thin-sample, correlated-stack, top-2 disjoint per team-game,
    favourite-first. rows need pred_date, team, player, stat, line, side, ev, odds, d_min, n_elev."""
    return SL.current_selection(rows)
