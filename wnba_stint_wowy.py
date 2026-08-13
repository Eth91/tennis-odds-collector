"""STINT-LEVEL WOWY — the fallback for when game-level WOWY has no sample (2026-08-12).

WHY THIS EXISTS
`wnba_alert.py` needs `n_without >= 2` games where the beneficiary played and the out
star did not. A star's FIRST game out therefore has n=0 and no path at all — the loop's
lowest tier is `n1 = (n_without == 1)`, which is shadow-only. On 2026-08-12 that blanked
four separate situations at once (Shepard/DAL n=0, Stokes/GS n=0, Conde/TOR n=0,
Feagin/POR n=0).

That is the worst possible time to be blind: the book has the least information on a
star's first game out too, so it is where the price is most likely to be stale.

THE INSIGHT
Game-level WOWY is starved, but the star SITS ~8 minutes every game. Those minutes are
recorded in `wnba_stints.sqlite`, so "how does this teammate produce with the star off
the floor" has hundreds of minutes of sample even when the game-level split has zero:

    Li Yueru   / Shepard off floor:  1,157 min   9.65 reb/36  (game-level n=0)
    Awak Kuier / Shepard off floor:    439 min   8.53 reb/36  (game-level n=0)

⚠️ STINTS GIVE THE RATE, NOT THE MINUTES. This is the whole difficulty, and it is exactly
the defect that killed the 2026-08-12 Sheldon flag: that flag took a rate measured on
games at `min >= 22`, then implicitly assumed 22+ minutes would happen, never multiplying
by P(minutes). De-conditioned, its 76.9% was ~42%.

So this module NEVER conditions on a single projected minutes figure. It MARGINALISES:

    P(over) = E_m [ P(stat > line | minutes = m) ]

taking m from the beneficiary's own historical minutes distribution shifted by a bump.
A rate that only clears the line in a 30-minute game is correctly penalised by how rarely
this player sees 30 minutes. This is the one design decision that matters here.

WALK-FORWARD: every aggregate is computed from `game_date < as_of` only. The backtest
depends on it, and a leak here would manufacture the entire result.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

DB = Path(__file__).with_name("wnba_stints.sqlite")

# stat -> (onfloor column, pairs "with" column)
STAT_COLS = {
    "points":   ("pts", "pts_with"),
    "rebounds": ("reb", "reb_with"),
    "assists":  ("ast", "ast_with"),
}

MIN_OFF_MINUTES = 120.0    # below this the off-floor rate is noise, not a measurement
BUMP_DIVISOR = 4.0         # V0: the out star's minutes split across ~4 rotation players
BUMP_CAP = 8.0             # no single beneficiary absorbs more than this
MINUTES_CAP = 36.0


def _con(db=None):
    c = sqlite3.connect(f"file:{db or DB}?mode=ro", uri=True, timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    c.row_factory = sqlite3.Row
    return c


def off_floor_rate(con, player, mate, stat, as_of):
    """Per-36 rate for `player`'s `stat` in the minutes `mate` was OFF the floor.

    off = total on-floor  MINUS  time shared with `mate`. Whole games `mate` missed are
    included in `off` by construction (no pairs row exists for them), which is correct —
    those minutes are also "mate not on the floor".
    """
    oc, pc = STAT_COLS[stat]
    t = con.execute(
        f"SELECT COALESCE(SUM(sec),0) s, COALESCE(SUM({oc}),0) v FROM onfloor "
        f"WHERE player=? AND game_date < ?", (player, as_of)).fetchone()
    w = con.execute(
        f"SELECT COALESCE(SUM(sec),0) s, COALESCE(SUM({pc}),0) v FROM pairs "
        f"WHERE player=? AND mate=? AND game_date < ?", (player, mate, as_of)).fetchone()
    off_sec = (t["s"] or 0) - (w["s"] or 0)
    off_val = (t["v"] or 0) - (w["v"] or 0)
    if off_sec <= 0:
        return None
    off_min = off_sec / 60.0
    return {"rate36": off_val / off_min * 36.0, "off_min": off_min,
            "on_min": (w["s"] or 0) / 60.0,
            "on_rate36": ((w["v"] or 0) / ((w["s"] or 0) / 60.0) * 36.0) if w["s"] else None}


def minutes_history(con, player, as_of, last=20):
    """The player's own recent per-game minutes — the distribution we marginalise over."""
    rows = con.execute(
        "SELECT sec FROM onfloor WHERE player=? AND game_date < ? "
        "ORDER BY game_date DESC LIMIT ?", (player, as_of, last)).fetchall()
    return [r["sec"] / 60.0 for r in rows if r["sec"]]


# Dispersion (var/mean) measured on PRE-2026 games only, so the test season never informs
# the distribution. Points at 3.12 is not a rounding detail -- Poisson forces var == mean,
# so below the mean (where EVERY +EV over bet sits, by construction) it overstates P(over).
# In the backtest the stat with phi 3.12 returned -33% while the phi ~1.2-1.4 stats
# returned +33%. The distribution was the bug, not the level.
PHI = {'points': 3.135, 'rebounds': 1.442, 'assists': 1.228}


def _p_over(lam, line, phi=1.0):
    """P(X > line). Negative binomial when overdispersed, Poisson when phi <= 1."""
    if lam <= 0:
        return 0.0
    k = int(math.floor(line)) + 1
    if phi <= 1.0:
        cum, term = 0.0, math.exp(-lam)
        for i in range(k):
            if i:
                term *= lam / i
            cum += term
        return max(0.0, min(1.0, 1.0 - cum))
    r = lam / (phi - 1.0)                 # var = lam * phi
    p = r / (r + lam)
    cum, term = 0.0, p ** r
    for i in range(k):
        if i:
            term *= (r + i - 1) / i * (1 - p)
        cum += term
    return max(0.0, min(1.0, 1.0 - cum))


def _p_over_poisson(lam, line):
    return _p_over(lam, line, 1.0)


def project(con, player, mate, stat, line, as_of, mate_mpg, dispersion=1.0,
            p_market=None, k_cred=11.0):
    """-> {p_over, proj, rate36, off_min, n_min, bump} or None if unmeasurable.

    ⚠️ MARGINALISES OVER MINUTES. p_over is the AVERAGE of P(over | m) across the player's
    own minutes history (each shifted by the bump), NOT P(over | mean minutes). Those two
    differ most for exactly the players this channel targets — low-minute bench players
    with a fat left tail — and the conditional version is the error that inflated the
    Sheldon flag from ~42% to 76.9%.
    """
    r = off_floor_rate(con, player, mate, stat, as_of)
    if not r or r["off_min"] < MIN_OFF_MINUTES:
        return None
    # ── MINUTES NOW COME FROM THE MEASURED MODEL, NOT A GUESS (2026-08-12) ──────
    # The original `bump = mate_mpg / 4` over-predicted minutes by +4.93 on 2026 and
    # +4.36 on 2025 (n=7,896 beneficiary-games). That single bias is what turned this
    # channel into -15.6% ROI: the rate was roughly right, the minutes were not.
    # wnba_minutes.minutes_vector() returns the player's OWN recent minutes shape
    # recentred on a substitution-rate estimate, so the fat left tail survives.
    import wnba_minutes as _MM
    mins = _MM.minutes_vector(con, player, mate, as_of)
    if len(mins) < 5:
        return None
    bump = 0.0
    ps, projs = [], []
    for m in mins:
        mm = min(MINUTES_CAP, m)
        lam = r["rate36"] * mm / 36.0 * dispersion
        projs.append(lam)
        ps.append(_p_over(lam, line, PHI.get(stat, 1.0)))
    # ── CREDIBILITY SHRINK TOWARD THE MARKET (2026-08-12) ──────────────────────
    # Betting only where the model most disagrees with the price SELECTS for cases where
    # the MODEL is wrong -- winner's curse. That is the most likely source of the residual
    # +0.134 calibration gap that survived the minutes fix, the starter filter and the
    # negative binomial: each of those removed a bias, none of them touched the selection
    # effect. The live WNBA engine already does this (proj_hit shrunk to the book at k=11);
    # this prototype did not shrink at all, which is the one structural difference left.
    # Effective sample = off-floor minutes expressed in game-equivalents, so a 200-minute
    # rate is trusted far less than a 1,100-minute one.
    _p = sum(ps) / len(ps)
    if p_market is not None:
        _n = r["off_min"] / 36.0
        _p = (_n * _p + k_cred * p_market) / (_n + k_cred)
    return {"p_over": _p, "p_raw": sum(ps) / len(ps), "proj": sum(projs) / len(projs),
            "rate36": r["rate36"], "on_rate36": r["on_rate36"], "off_min": r["off_min"],
            "n_min": len(mins), "bump": bump,
            "mean_min": sum(mins) / len(mins) + bump}


def game_level_n_without(con, player, mate, as_of):
    """How many prior games the player appeared in and the mate did not — the number
    `wnba_alert` gates on. This channel is only meant to fire when it is < 2."""
    pg = {r["event_id"] for r in con.execute(
        "SELECT event_id FROM onfloor WHERE player=? AND game_date < ?", (player, as_of))}
    mg = {r["event_id"] for r in con.execute(
        "SELECT event_id FROM onfloor WHERE player=? AND game_date < ?", (mate, as_of))}
    tg = {r["event_id"] for r in con.execute(
        "SELECT DISTINCT event_id FROM onfloor WHERE game_date < ? AND event_id IN "
        "(SELECT event_id FROM onfloor WHERE player=?)", (as_of, mate))}
    return len(pg - mg), len(pg & mg), len(tg)
