"""NBA cold-start tier — the projection for a beneficiary with NO WOWY prior.

When a star X sits and teammate B has fewer than 2 prior games without X, there is no
measured with/without split to lean on. The cold-start answer is to hand X's vacated
minutes to the rotation in proportion to how much each member already plays, then
project B's production at B's own per-minute rate over the minutes B inherits.

This module is the ONE definition of that projection. The real-line test
(nba_coldstart_realline.py) and the live engine (nba_flags.py) both import it, so the
backtest cannot drift from production — the same discipline as wnba_tonight.flip_p_over.

Every constant here predates real-line evidence (set 2026-07-16 on a proxy line) and is
fixed by NBA_COLDSTART_PREREG.md. Changing one restarts the evidence; do not tune them.
"""
from __future__ import annotations

ROT_LO, ROT_HI = 12.0, 32.0   # rotation band: trailing-10 avg minutes
COLD_MARGIN = 5.0             # bet the over only when proj - line >= this
MIN_WOWY = 2                  # fewer prior X-out games than this => cold-start, not WOWY
MIN_SEASON_GAMES = 5          # below this, B's rate falls back to the 400-day pool
STATS = ("pts", "reb", "ast", "fg3m", "pra")


def redistribute(base_mins, x_id, vacated):
    """{player: projected minutes} for the rotation after X's minutes are handed out.

    base_mins: {player: trailing-10 avg minutes} for prior-active teammates (X may be in it;
    X is excluded here). Only players inside [ROT_LO, ROT_HI] take a share — starters above
    32 are already near their ceiling, deep bench below 12 is not in the rotation. Each
    member's share is proportional to their own minutes, so the shares sum to `vacated`.
    Returns {} when there is no rotation to give minutes to — refuse, never guess.
    """
    rot = {p: m for p, m in base_mins.items()
           if p != x_id and m is not None and ROT_LO <= m <= ROT_HI}
    tot = sum(rot.values())
    if tot <= 0 or vacated is None or vacated <= 0:
        return {}
    return {p: m + vacated * m / tot for p, m in rot.items()}


def per_min_rate(apps, season_of, today_season):
    """{stat: per-minute rate} for B from prior appearances [(date, min, {stat: v})].

    Current-season games when there are at least MIN_SEASON_GAMES of them (a player's role
    and efficiency move season to season), otherwise every prior game in the pool window.
    Returns None when B has logged no minutes at all.
    """
    cur = [a for a in apps if season_of(a[0]) == today_season]
    use = cur if len(cur) >= MIN_SEASON_GAMES else apps
    mins = sum(a[1] for a in use)
    if mins <= 0:
        return None
    return {s: sum(a[2][s] for a in use) / mins for s in STATS}


def season_of(date_iso):
    """NBA season label for an ISO date: Aug-Dec belong to that year's season, Jan-Jul to the prior."""
    y, m = int(date_iso[:4]), int(date_iso[5:7])
    return y if m >= 8 else y - 1


if __name__ == "__main__":
    # Arithmetic self-check: shares must sum to the vacated minutes, and out-of-band
    # players (a 35-min starter, a 6-min bench guy, X himself) must get nothing.
    bm = {"X": 34.0, "star": 35.0, "a": 30.0, "b": 20.0, "c": 12.0, "deep": 6.0}
    r = redistribute(bm, "X", 34.0)
    assert set(r) == {"a", "b", "c"}, r
    assert abs(sum(r[p] - bm[p] for p in r) - 34.0) < 1e-9, r
    assert abs(r["a"] - (30 + 34 * 30 / 62)) < 1e-9, r
    assert redistribute({"X": 30.0, "star": 36.0}, "X", 30.0) == {}
    assert season_of("2025-10-21") == 2025 and season_of("2026-04-12") == 2025
    print("nba_coldstart self-check OK:", {k: round(v, 2) for k, v in r.items()})
