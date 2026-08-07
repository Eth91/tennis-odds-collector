#!/usr/bin/env python3
"""Add opponent rebounding strength and pace to the stint rebound projection, then retest.

Basketball reasons the raw apart-rate misses:
  * rebounds are a SHARED pool — how many are available depends on the opponent, not just on
    who replaced the injured big;
  * a fast game creates more misses and therefore more boards to grab.

Both are computable from data we already have. A game_id identifies a GAME, not a side, so the
two teams in a game share one — that gives the opponent for every game in BOTH seasons without
needing a name-to-abbreviation map.

  opp_factor  = (rebounds the opponent has ALLOWED per game) / (league mean), walk-forward
  pace_factor = (total rebounds in that opponent's games) / (league mean), walk-forward

proj is multiplied by both. Everything else is unchanged, so any difference is these two terms.
"""
import sys, statistics as st
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
sys.path.insert(0, "/home/ubuntu")
import wnba_stint_proper as P
import wnba_funnel_stint as F

_orig_price = P.price_it
CTX = {"opp": {}, "pace": {}, "on": True}


def build_ctx(norm, team_of):
    """-> per (date, team): rebounds that team's opponents have averaged against them, and the
    average total rebounds in their games — both from games strictly BEFORE that date."""
    gteams = defaultdict(set)
    greb = defaultdict(lambda: defaultdict(float))
    gdate = {}
    for pl, gs in norm.items():
        tm = team_of.get(pl)
        for g in gs:
            if not g.get("gid"):
                continue
            gteams[g["gid"]].add(tm)
            greb[g["gid"]][tm] += g["reb"]
            gdate[g["gid"]] = g["d"]
    allowed = defaultdict(list)   # team -> [(date, reb conceded)]
    total = defaultdict(list)     # team -> [(date, total reb in game)]
    for gid, teams in gteams.items():
        if len(teams) != 2:
            continue
        a, b = sorted(teams)
        d = gdate[gid]
        allowed[a].append((d, greb[gid][b]))
        allowed[b].append((d, greb[gid][a]))
        tot = greb[gid][a] + greb[gid][b]
        total[a].append((d, tot)); total[b].append((d, tot))
    return allowed, total, gteams, gdate


def factors(allowed, total, team, day, lg_allow, lg_total):
    a = [v for d, v in allowed.get(team, []) if d < day]
    t = [v for d, v in total.get(team, []) if d < day]
    if len(a) < 4 or len(t) < 4 or not lg_allow or not lg_total:
        return 1.0, 1.0
    return (st.mean(a) / lg_allow, st.mean(t) / lg_total)


def patched_run(season, stat):
    """Wrap P.run: compute context, then hook price_it to scale proj by opp x pace."""
    import wnba_wowy as W
    # P.run rebuilds its own norm/team_of internally; recompute the same way for context
    if season == 2026:
        import wnba_replay as R
        pmap = W.players()
        norm = {}
        for n, v in pmap.items():
            norm[n] = [{"d": str(g.get("date") or "")[:10], "gid": g.get("game_id"),
                        "min": g.get("min") or 0, "reb": g.get("reb") or 0}
                       for g in R.full_log(v["id"])]
        team_of = {n: v["team"] for n, v in pmap.items()}
    else:
        import sqlite3
        b = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_boxscores.sqlite"
                            "?mode=ro", uri=True)
        norm, team_of = defaultdict(list), {}
        for gid, d, tm, pl, mn, reb in b.execute(
                "SELECT game_id,game_date,team,player,min,reb FROM box WHERE min IS NOT NULL"):
            norm[pl].append({"d": d, "gid": gid, "min": mn or 0, "reb": reb or 0})
            team_of[pl] = tm
    allowed, total, gteams, gdate = build_ctx(norm, team_of)
    lg_allow = st.mean([v for lst in allowed.values() for _d, v in lst]) if allowed else 0
    lg_total = st.mean([v for lst in total.values() for _d, v in lst]) if total else 0
    opp_of = {}
    for gid, teams in gteams.items():
        if len(teams) == 2:
            a, b2 = sorted(teams)
            opp_of[(gdate[gid], a)] = b2
            opp_of[(gdate[gid], b2)] = a

    def hooked(prior, key, line, dec, proj_min, shift, _day=None, _team=None):
        q = _orig_price(prior, key, line, dec, proj_min, shift)
        return q
    # scale via shift: opp/pace multiply the projection exactly as usage shift does
    orig = P.price_it

    def wrapper(prior, key, line, dec, proj_min, shift):
        d = P.CUR.get("day"); tm = P.CUR.get("team")
        f = 1.0
        if CTX["on"] and d and tm:
            opp = opp_of.get((d, tm))
            if opp:
                oa, pa = factors(allowed, total, opp, d, lg_allow, lg_total)
                f = oa * pa
        return orig(prior, key, line, dec, proj_min, shift * f)

    P.price_it = wrapper
    P._CTX_HOOK = CTX
    try:
        bets, _sk = P.run(season, stat)
    finally:
        P.price_it = orig
    return bets


def summ(bets):
    if not bets:
        return "0 bets"
    w = sum(b["hit"] for b in bets); l = len(bets) - w
    u = sum((b["dec"] - 1.0) if b["hit"] else -1.0 for b in bets)
    be = st.mean([1.0 / b["dec"] for b in bets])
    return (f"{w}-{l}  hit {100*w/len(bets):5.1f}%  be {100*be:5.1f}%  "
            f"edge {100*(w/len(bets)-be):+6.1f}  {u:+7.2f}u")


if __name__ == "__main__":
    CFG = dict(samepos=True, min_apart=0.0, starter=0.0, max_nwo=8, ev_bar=0.10, top_n=2)
    print("BASELINE (no opponent / pace terms)")
    for s in (2026, 2025):
        print(f"  {s}  {summ(F.run_cfg(s, 'rebounds', **CFG))}")
    print("\nWITH opponent rebounding strength x pace")
    CTX["on"] = True
    for s in (2026, 2025):
        P.MIN_APART, P.STARTER_MIN, P.MAX_NWO = 0.0, 0.0, 8
        P.EV_BAR, P.TOP_N, P.SAMEPOS = 0.10, 2, True
        print(f"  {s}  {summ(patched_run(s, 'rebounds'))}")
