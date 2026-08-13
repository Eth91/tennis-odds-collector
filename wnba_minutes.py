"""MINUTES MODEL — the piece the stint-WOWY backtest identified as the real blocker.

WHY THIS EXISTS
The 2026-08-12 stint-WOWY prototype lost 15.6% ROI over 85 real-line bets. The error
decomposition put the blame in two places, and only one of them is the rate:

    minutes: assumed 31.3   actual 27.9   (-3.4)
    per-36:  used    12.53  achieved 11.25 (-1.29)

and, decisively, the subset where the assumed minutes DID arrive went 23-14 = 62.2%.
So the rate signal is roughly sound and the minutes assumption is what breaks it. That
assumption was a guess: `bump = out_player_mpg / 4`, capped at 8. Nothing measured it.

THE IDEA
Do not guess how minutes redistribute — read it off the floor. `pairs` records, for every
game, how long each teammate pair shared the court. Combined with each player's total
floor time that yields, for any pair (B, O):

    rate_off(B|O) = (B's minutes while O sat) / (O's total bench minutes)

i.e. the share of O's bench time that B is on the court for. If O misses a whole game,
B's expected minutes are simply `game_clock * rate_off(B|O)`. This is measured, not
assumed, and — crucially — it does NOT need a single game where O was absent. That is the
same reason stint-WOWY reached the n=0 population at all.

⚠️ THE SUBSTITUTION RATE IS NOT THE WHOLE STORY. A backup's rate during a star's rest
minutes overstates a full-game absence: rest minutes are concentrated in low-leverage
stretches, and with the star out entirely a coach redistributes toward starters, not
just the direct backup. So the raw rate is SHRUNK toward the player's own recent mpg,
with the weight set by how much off-floor sample exists. The shrink is fitted on one
season and tested on the next — never on the same data twice.

⚠️ GAME CLOCK IS DERIVED, NOT ASSUMED TO BE 40. Summing a team's on-floor seconds and
dividing by 5 recovers the true clock, so overtime games do not silently inflate every
rate by 12%.

OUTPUT IS A DISTRIBUTION, NOT A POINT. The consumer marginalises over minutes, so a point
estimate would reintroduce exactly the conditioning error this whole exercise exists to
remove. `predict()` returns a mean and a residual sd, and `sample_minutes()` turns that
into the vector the projection integrates over.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).with_name("wnba_stints.sqlite")

K_SHRINK = 300.0        # off-floor minutes at which the measured rate gets half the weight
MIN_OFF_SAMPLE = 60.0   # below this the rate is ignored entirely, recent mpg is used
CLOCK = 40.0            # a regulation game; predictions are scaled to this
CAP = 38.0


def _con(db=None):
    c = sqlite3.connect(f"file:{db or DB}?mode=ro", uri=True, timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    c.row_factory = sqlite3.Row
    return c


def recent_mpg(con, player, as_of, window=10):
    r = con.execute(
        "SELECT sec FROM onfloor WHERE player=? AND game_date < ? "
        "ORDER BY game_date DESC LIMIT ?", (player, as_of, window)).fetchall()
    v = [x["sec"] / 60.0 for x in r if x["sec"]]
    return (sum(v) / len(v)) if v else None


def substitution_rate(con, ben, out, as_of):
    """-> (rate, off_sample_minutes) — the share of `out`'s bench time that `ben` is on
    the floor for, over games BOTH played, strictly before `as_of`.

    Restricting to games both played is deliberate: it isolates WITHIN-GAME substitution.
    Games `out` missed entirely would fold a whole-absence effect into a rest-minutes
    measurement and make the estimator partly circular with what we are trying to predict.
    """
    ev = [r["event_id"] for r in con.execute(
        "SELECT DISTINCT a.event_id FROM onfloor a JOIN onfloor b USING(event_id) "
        "WHERE a.player=? AND b.player=? AND a.game_date < ?", (ben, out, as_of))]
    if not ev:
        return None, 0.0
    q = ",".join("?" * len(ev))
    # true game clock per event = team on-floor seconds / 5 (handles overtime)
    clocks = {}
    for r in con.execute(
            f"SELECT o.event_id, SUM(o.sec) s FROM onfloor o JOIN pteam t "
            f"ON t.event_id=o.event_id AND t.player=o.player "
            f"WHERE o.event_id IN ({q}) AND t.team=("
            f"  SELECT team FROM pteam WHERE event_id=o.event_id AND player=? LIMIT 1) "
            f"GROUP BY o.event_id", (*ev, out)):
        clocks[r["event_id"]] = (r["s"] or 0) / 5.0
    osec = {r["event_id"]: r["sec"] or 0 for r in con.execute(
        f"SELECT event_id, sec FROM onfloor WHERE player=? AND event_id IN ({q})", (out, *ev))}
    bsec = {r["event_id"]: r["sec"] or 0 for r in con.execute(
        f"SELECT event_id, sec FROM onfloor WHERE player=? AND event_id IN ({q})", (ben, *ev))}
    wsec = {r["event_id"]: r["sec"] or 0 for r in con.execute(
        f"SELECT event_id, sec FROM pairs WHERE player=? AND mate=? AND event_id IN ({q})",
        (ben, out, *ev))}
    off_tot = ben_off = 0.0
    for e in ev:
        c = clocks.get(e)
        if not c:
            continue
        o_off = c - osec.get(e, 0)
        b_off = bsec.get(e, 0) - wsec.get(e, 0)
        if o_off <= 0:
            continue
        off_tot += o_off
        ben_off += max(0.0, b_off)
    if off_tot <= 0:
        return None, 0.0
    return ben_off / off_tot, off_tot / 60.0


def predict(con, ben, out, as_of, shrink_k=K_SHRINK):
    """-> {"mean": minutes, "sd": residual sd, "rate": .., "base": .., "w": ..} or None.

    mean = w * (CLOCK * substitution_rate) + (1 - w) * recent_mpg,
    w = off_sample / (off_sample + shrink_k)

    The shrink target is the player's own recent mpg — NOT zero and not the league mean.
    A bench player's floor is what he already plays; the measured rate can only move him
    off that, and only in proportion to how much of it we actually observed.
    """
    base = recent_mpg(con, ben, as_of)
    if base is None:
        return None
    rate, off_min = substitution_rate(con, ben, out, as_of)
    if rate is None or off_min < MIN_OFF_SAMPLE:
        return {"mean": base, "sd": 6.0, "rate": None, "base": base, "w": 0.0,
                "off_min": off_min}
    w = off_min / (off_min + shrink_k)
    raw = min(CAP, CLOCK * rate)
    mean = w * raw + (1.0 - w) * base
    return {"mean": min(CAP, mean), "sd": 6.0, "rate": rate, "raw": raw,
            "base": base, "w": w, "off_min": off_min}


def minutes_vector(con, ben, out, as_of, n=12):
    """The distribution to marginalise over: the player's own recent minutes SHAPE,
    recentred on the predicted mean. Using his real spread rather than a fitted normal
    keeps the fat left tail (foul trouble, blowouts, DNPs) that a symmetric distribution
    would smooth away — and that tail is exactly what makes a bench over lose."""
    p = predict(con, ben, out, as_of)
    if not p:
        return []
    r = con.execute("SELECT sec FROM onfloor WHERE player=? AND game_date < ? "
                    "ORDER BY game_date DESC LIMIT ?", (ben, as_of, n)).fetchall()
    v = [x["sec"] / 60.0 for x in r if x["sec"] is not None]
    if len(v) < 5:
        return [p["mean"]]
    m = sum(v) / len(v)
    return [max(0.0, min(CAP, x - m + p["mean"])) for x in v]
