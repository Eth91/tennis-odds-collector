#!/usr/bin/env python3
"""Stint apart-rate tested with the MODEL'S OWN selection logic — both seasons, same rules.

The earlier version bet whenever the projection beat the line. The real pipeline does far more,
and every missing step cuts bets: it shrinks a thin-sample estimate toward the book, demands a
real edge rather than any edge, and caps how many plays a single game can carry. A rate built on
~50 minutes of court time is exactly the thin sample shrinkage exists for, so leaving it out
inflated the bet count and made both the 2026 win and the 2025 collapse louder than they were.

WHAT IS NOW MATCHED TO THE MODEL
  * usage shift  : scale each prior game by (apart_rate / overall_rate) — the stint signal
  * minutes-honest: scale to tonight's projected minutes, capped 1.35x like prop_edges
  * hit rate     : share of adjusted prior games clearing the line, with its own n
  * SHRINKAGE    : p_adj = (hit*n + (1/dec)*K) / (n + K), K=11 — same as prop_edges
  * EV BAR       : +10% for overs, same as OVER_EV_MIN
  * TOP-2        : at most two plays per team-game, highest EV first
  * no over on a stat that DROPS in the apart-split

WHAT STILL DIFFERS BETWEEN SEASONS (stated, not hidden)
  * 2026 logs come from ESPN, 2025 from wnba_boxscores — ESPN has no 2025. Same fields either way.
  * positions come from the CURRENT roster map, so 2025 players since out of the league are
    skipped. Exclusion counts are printed for BOTH seasons so the gap is visible rather than
    assumed away.
"""
import sys, sqlite3, statistics as st
from collections import defaultdict

# ORDER MATTERS: two wnba_replay.py exist on this box. The repo copy shadows the harness
# one and dies on import (WA.glog), so /home/ubuntu must end up FIRST on sys.path.
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
sys.path.insert(0, "/home/ubuntu")
_a = list(sys.argv); sys.argv = ["x"]
import wnba_replay as R
import wnba_wowy as W
sys.argv = _a

SHRINK_K = 11.0
EV_BAR = 0.10
MIN_APART, STARTER_MIN, MAX_NWO = 50.0, 25.0, 2
TOP_N = 2
SAMEPOS = True
CUR = {}   # current (day, team) — lets a context hook scale the projection   # relaxable for the filter sweep
SPEC = {"rebounds": ("reb", "reb_with", "player_rebounds", "reb"),
        "assists":  ("ast", "ast_with", "player_assists",  "ast"),
        "points":   ("pts", "pts_with", "player_points",   "pts")}


def stint_tables(stat, season):
    tc, pc, _, _ = SPEC[stat]
    c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_stints.sqlite?mode=ro",
                        uri=True)
    ok = {e for (e,) in c.execute("SELECT event_id FROM games WHERE status='ok'")}
    lo, hi = ("2025-01-01", "2026-01-01") if season == 2025 else ("2026-01-01", "2027-01-01")
    on, pair = defaultdict(list), defaultdict(list)
    for e, d, p, sec, v in c.execute(f"SELECT event_id,game_date,player,sec,{tc} FROM onfloor"):
        if e in ok and v is not None and lo <= d < hi:
            on[p].append((d, sec or 0.0, v or 0.0))
    for e, d, p, m, sec, v in c.execute(
            f"SELECT event_id,game_date,player,mate,sec,{pc} FROM pairs"):
        if e in ok and v is not None and lo <= d < hi:
            pair[(p, m)].append((d, sec or 0.0, v or 0.0))
    c.close()
    return on, pair


def rates(on, pair, player, mate, before):
    """-> (apart_rate_per_min, overall_rate_per_min, minutes_apart) or None"""
    ts = tv = 0.0
    for d, sec, v in on.get(player, []):
        if d < before:
            ts += sec; tv += v
    ws = wv = 0.0
    for d, sec, v in pair.get((player, mate), []):
        if d < before:
            ws += sec; wv += v
    ap_s, ap_v = ts - ws, tv - wv
    if ap_s <= 0 or ts <= 0:
        return None
    return (ap_v / (ap_s / 60.0), tv / (ts / 60.0), ap_s / 60.0)


def price_it(prior, key, line, dec, proj_min, shift):
    """The model's own arithmetic: minutes-honest + usage-shifted values -> hit rate ->
    credibility shrink toward the book -> EV."""
    vals = []
    for g in prior:
        m = g["min"]
        if m <= 0:
            continue
        vals.append(g[key] * min(proj_min / m, 1.35) * shift)
    if len(vals) < 4:
        return None
    hit = sum(1 for v in vals if v > line) / len(vals)
    n = len(vals)
    p_adj = (hit * n + (1.0 / dec) * SHRINK_K) / (n + SHRINK_K)
    return {"ev": p_adj * dec - 1.0, "hit": hit, "n": n,
            "proj": st.mean(vals)}


def run(season, stat, verbose=False):
    tc, pc, mk, key = SPEC[stat]
    on, pair = stint_tables(stat, season)
    pmap = W.players()
    skipped_pos = set()

    if season == 2026:
        con = sqlite3.connect(f"file:{R.HIST}?mode=ro", uri=True)
        days = [d for (d,) in con.execute(
            "SELECT DISTINCT game_date FROM props WHERE game_date>='2026-05-10' ORDER BY 1")]
        con.close()
        logs = {n: R.full_log(v["id"]) for n, v in pmap.items()}
        norm = {n: [{"d": str(g.get("date") or "")[:10], "gid": g.get("game_id"),
                     "min": g.get("min") or 0, "pts": g.get("pts") or 0,
                     "reb": g.get("reb") or 0, "ast": g.get("ast") or 0}
                    for g in lg] for n, lg in logs.items()}
        for n in norm:
            norm[n].sort(key=lambda x: x["d"])
        team_of = {n: v["team"] for n, v in pmap.items()}
        lines_for = lambda day: R._load_date(day)
        two_of = lambda lad: {k: v for k, v in lad.items() if v and v[0] and v[1]}
        price_of = lambda v: v[0]
    else:
        b = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_boxscores.sqlite"
                            "?mode=ro", uri=True)
        norm, team_of = defaultdict(list), {}
        for gid, d, tm, pl, mn, pts, reb, ast in b.execute(
                "SELECT game_id,game_date,team,player,min,pts,reb,ast FROM box "
                "WHERE min IS NOT NULL"):
            norm[pl].append({"d": d, "gid": gid, "min": mn or 0, "pts": pts or 0,
                             "reb": reb or 0, "ast": ast or 0})
            team_of[pl] = tm
        for n in norm:
            norm[n].sort(key=lambda x: x["d"])
        p = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_props_2025.sqlite"
                            "?mode=ro", uri=True)
        L = defaultdict(lambda: defaultdict(dict))
        for d, pl, m, ln, side, pr in p.execute(
                "SELECT game_date,player,market,line,side,price FROM props WHERE market=?",
                (mk,)):
            if side in ("over", "under") and ln is not None and pr:
                L[d][pl][round(float(ln), 1)] = L[d][pl].get(round(float(ln), 1), {})
                L[d][pl][round(float(ln), 1)][side] = float(pr)
        days = sorted(L)
        lines_for = lambda day: {pl: {stat: lad} for pl, lad in L[day].items()}
        two_of = lambda lad: {k: v for k, v in lad.items() if "over" in v and "under" in v}
        price_of = lambda v: v["over"]

    played_on = defaultdict(set)
    for n, gs in norm.items():
        for g in gs:
            if g["min"] > 0:
                played_on[(g["d"], team_of.get(n))].add(n)

    roster = defaultdict(set)
    for n, tm in team_of.items():
        roster[tm].add(n)

    bets = []
    for day in days:
        todays = lines_for(day)
        if not todays:
            continue
        pergame = defaultdict(list)
        for tm, ros in roster.items():
            app = played_on.get((day, tm), set())
            if not app:
                continue
            prior_all = {n: [g for g in norm.get(n, []) if g["d"] < day] for n in ros}
            for out_name in ros:
                if out_name in app:
                    continue
                og = [g for g in prior_all.get(out_name, []) if g["min"] > 0]
                if len(og) < 5 or st.mean(g["min"] for g in og[-10:]) < 20:
                    continue
                ov = pmap.get(out_name)
                if not ov or not ov.get("position"):
                    skipped_pos.add(out_name); continue
                out_gids = {g["gid"] for g in og}
                for n in app:
                    if n == out_name or n not in todays:
                        continue
                    nv = pmap.get(n)
                    if not nv:
                        skipped_pos.add(n); continue
                    if SAMEPOS and nv.get("position") != ov["position"]:
                        continue
                    g = [x for x in prior_all.get(n, []) if x["min"] > 0]
                    if len(g) < 6:
                        continue
                    wi = [x for x in g if x["gid"] in out_gids]
                    wo = [x for x in g if x["gid"] not in out_gids]
                    if len(wi) < 2 or len(wo) > MAX_NWO:
                        continue
                    if st.mean(x["min"] for x in wi) < STARTER_MIN:
                        continue
                    rr = rates(on, pair, n, out_name, day)
                    if not rr:
                        continue
                    ap, ov_r, mins = rr
                    if mins < MIN_APART or ov_r <= 0:
                        continue
                    shift = ap / ov_r
                    if shift <= 1.0:
                        continue                      # stat DROPS apart -> never an over
                    r5 = [x["min"] for x in g[-5:] if x["min"] > 8]
                    pm = st.median(r5) if r5 else st.mean(x["min"] for x in wi)
                    lad = two_of((todays[n].get(stat) or {}))
                    if not lad:
                        continue
                    line = min(lad, key=lambda x: abs(
                        (price_of(lad[x]) - (lad[x]["under"] if isinstance(lad[x], dict)
                                             else lad[x][1]))))
                    dec = price_of(lad[line])
                    CUR["day"], CUR["team"] = day, tm
                    q = price_it(g, key, line, dec, pm, shift)
                    if not q or q["ev"] < EV_BAR:
                        continue
                    act = [x for x in norm.get(n, []) if x["d"] == day and x["min"] > 0]
                    if not act or abs(act[0][key] - line) < 1e-9:
                        continue
                    pergame[(day, tm)].append(
                        {"ev": q["ev"], "player": n, "out": out_name, "line": line,
                         "dec": dec, "hit": 1 if act[0][key] > line else 0,
                         "date": day, "n": q["n"], "shift": shift})
        for k, v in pergame.items():
            # DEDUPE THE SAME WAGER (2026-08-07). A beneficiary can qualify under two different
            # injured teammates on the same night and generate the identical (player, line) bet
            # twice -- live that is a double stake on one position, and in a backtest it double
            # counts. Found on 2026-07-05 Marina Mabrey rebounds 3.5. Keep the highest-EV copy.
            best = {}
            for x in v:
                kk = (x["player"], x["line"])
                if kk not in best or x["ev"] > best[kk]["ev"]:
                    best[kk] = x
            bets += sorted(best.values(), key=lambda x: -x["ev"])[:TOP_N]

    return bets, skipped_pos


def report(tag, bets):
    if not bets:
        print(f"  {tag:<26} 0 bets")
        return
    w = sum(b["hit"] for b in bets); l = len(bets) - w
    u = sum((b["dec"] - 1.0) if b["hit"] else -1.0 for b in bets)
    be = st.mean([1.0 / b["dec"] for b in bets])
    hit = w / len(bets)
    print(f"  {tag:<26} {w}-{l}  hit {100*hit:5.1f}%  be {100*be:5.1f}%  "
          f"edge {100*(hit-be):+6.1f}  {u:+7.2f}u   "
          f"({len(set(b['player'] for b in bets))} players)")


if __name__ == "__main__":
    print("MODEL-MATCHED stint test: shrinkage K=11, EV bar +10%, TOP-2 per game,\n"
          "same-position, starters, >=50min apart, n_without<=2, no over on a dropping stat\n")
    for stat in ("rebounds", "assists", "points"):
        print(f"=== {stat.upper()} ===")
        for season in (2026, 2025):
            bets, skipped = run(season, stat)
            report(f"{season}", bets)
            print(f"    ({len(skipped)} players skipped: no position in current roster map)")
        print()
