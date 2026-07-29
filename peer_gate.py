"""STAT-LEVEL PEER GATE — suppress beneficiary overs whose edge dies when a peer plays.

The existing peer_regime_scan measures BORROWED MINUTES and is display-only. It returned
None for every CON beneficiary on 7/28 and never saw the trap, because Nelson-Ododa's minutes
are normal (22 on 7/23) -- Morrow cannibalises her BOARDS, not her playing time. Two fat-EV
traps in two nights had the same shape:

  ONO reb o6.5   Morrow OUT 6/9 (67%)  |  Morrow IN 3/14 (21%)   breakeven 49.5%
  Stewart reb+ast o12.5  comps all had Laney-Hamilton + Maley out; season 46% vs 48.1% BE

So the honest test is on the STAT at the LINE, split by whether a specific teammate played,
restricted to teammates who play TONIGHT. If the beneficiary's over-rate WITH that peer is
below breakeven while it is far higher without them, the elevated sample is borrowed from a
lineup that is not happening.

Deliberately narrow, so it kills traps without eating real flags:
  * peer must be PLAYING TONIGHT (an out peer is part of the premise, not contamination)
  * both splits need real support (MIN_WITH / MIN_WITHOUT)
  * the WITH-peer rate must actually LOSE at the offered price
  * and the gap must be large (MIN_GAP)
"""
MIN_WITH = 5          # games with the peer on the floor
MIN_WITHOUT = 3       # games without them
MIN_GAP = 0.20        # over-rate difference that counts as cannibalisation
PEER_MIN_MPG = 12.0   # a peer must be a real rotation body. A 5-mpg deep-bench name cannot
                      # cannibalise anyone; against Horston, Taylor Thierry (5.4 mpg) produced
                      # a spurious 5-game split that would have killed a good bet.
MINUTES_CAP = 1.35    # same cap prop_edges uses when it scales a game to tonight's minutes


def peer_stat_gate(blog, valfn, line, dec, team_logs, plays_tonight, exclude=(),
                   proj_min=None, mpg_of=None):
    """-> dict describing the worst contaminating peer, or None if the bet is clean.

    blog        : beneficiary game log (newest first)
    valfn       : game -> the bet's stat value (handles combos like reb+ast)
    line, dec   : the rung being bet and its decimal price
    team_logs   : {teammate_name: their game log}
    plays_tonight: callable(name) -> bool
    exclude     : names to skip (the out players -- they ARE the premise)
    proj_min    : tonight's projected minutes. The bet is priced MINUTES-HONEST, so the gate
                  must be too -- judging an elevated role on raw historical totals understates
                  it and fails a fine bet (DiLeo at a projected 27 min).
    mpg_of      : callable(name) -> season mpg, used to ignore deep-bench peers
    """
    try:
        be = 1.0 / float(dec)
    except (TypeError, ZeroDivisionError):
        return None
    mine = {}
    for g in blog:
        try:
            v = valfn(g)
        except Exception:
            continue
        if v is None:
            continue
        if proj_min:                      # scale to tonight's role, exactly like prop_edges
            v = v * min(proj_min / max(g.get("min") or 1.0, 1.0), MINUTES_CAP)
        mine[g["date"][:10]] = v
    if len(mine) < (MIN_WITH + MIN_WITHOUT):
        return None
    worst = None
    for peer, plog in (team_logs or {}).items():
        if peer in set(exclude) or not plog:
            continue
        if not plays_tonight(peer):
            continue                      # an absent peer is the premise, not contamination
        if mpg_of is not None and (mpg_of(peer) or 0) < PEER_MIN_MPG:
            continue                      # deep-bench body: cannot plausibly cannibalise
        on = {g["date"][:10] for g in plog if (g.get("min") or 0) > 0}
        w = [v for d, v in mine.items() if d in on]
        wo = [v for d, v in mine.items() if d not in on]
        if len(w) < MIN_WITH or len(wo) < MIN_WITHOUT:
            continue
        r_w = sum(1 for v in w if v > line) / len(w)
        r_wo = sum(1 for v in wo if v > line) / len(wo)
        if r_w >= be:
            continue                      # still profitable with the peer on the floor -> fine
        if (r_wo - r_w) < MIN_GAP:
            continue                      # no real cannibalisation, just a thin sample
        cand = {"peer": peer, "rate_with": round(r_w, 3), "rate_without": round(r_wo, 3),
                "n_with": len(w), "n_without": len(wo), "breakeven": round(be, 3),
                "gap": round(r_wo - r_w, 3)}
        if worst is None or cand["gap"] > worst["gap"]:
            worst = cand
    return worst
