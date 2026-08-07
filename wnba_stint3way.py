#!/usr/bin/env python3
"""Stint apart-rate as a substitute for missing without-games — POINTS, REBOUNDS, ASSISTS.

The user's thesis: rebounds and assists redistribute BY POSITION (a big's boards go to another
big, a guard's assists to another guard) while points flow to whoever can score regardless of
position. So same-position is the right filter for reb/ast and the wrong one for points -- which
is why the points-only test kept failing.

Only testable now: the stint DB carried points alone until the 2026-08-06 clock/final-stint
repair backfilled rebounds and assists (and fixed pts/sec, which were wrong by up to 30% per
player).

Filters, user's cut: starters only, >=50 min apart, same position, n_without <= 2.
"""
import sys, sqlite3, statistics as st
from collections import defaultdict

sys.path.insert(0, "/home/ubuntu")
_a = list(sys.argv); sys.argv = ["x"]
import wnba_replay as R
import wnba_wowy as W
sys.argv = _a

STINT = "/home/ubuntu/tennis-odds-collector/wnba_stints.sqlite"
MIN_APART = 50.0
STARTER_MIN = 25.0
MAX_NWO = 2

# stat -> (onfloor col, pairs col, hist market, espn log key)
SPEC = {"points":   ("pts", "pts_with", "player_points",   "pts"),
        "rebounds": ("reb", "reb_with", "player_rebounds", "reb"),
        "assists":  ("ast", "ast_with", "player_assists",  "ast")}


def load(stat):
    tc, pc, _mk, _k = SPEC[stat]
    c = sqlite3.connect(f"file:{STINT}?mode=ro", uri=True)
    ok = {e for (e,) in c.execute("SELECT event_id FROM games WHERE status='ok'")}
    on = defaultdict(list)
    for e, d, p, sec, v in c.execute(
            f"SELECT event_id,game_date,player,sec,{tc} FROM onfloor"):
        if e in ok and v is not None:
            on[p].append((d, sec or 0.0, v or 0.0))
    pair = defaultdict(list)
    for e, d, p, m, sec, v in c.execute(
            f"SELECT event_id,game_date,player,mate,sec,{pc} FROM pairs"):
        if e in ok and v is not None:
            pair[(p, m)].append((d, sec or 0.0, v or 0.0))
    c.close()
    return on, pair


def apart(on, pair, player, mate, before):
    ts = tv = 0.0
    for d, sec, v in on.get(player, []):
        if d < before:
            ts += sec; tv += v
    ws = wv = 0.0
    for d, sec, v in pair.get((player, mate), []):
        if d < before:
            ws += sec; wv += v
    s = ts - ws
    if s <= 0:
        return None
    return ((tv - wv) / (s / 60.0), s / 60.0)


def run(stat, days, players, samepos=True):
    on, pair = load(stat)
    _tc, _pc, mk, key = SPEC[stat]
    cand = []
    for day in days:
        R._ASOF["day"] = day
        lines = R._load_date(day)
        if not lines:
            continue
        logs, played = {}, defaultdict(set)
        for n, v in players.items():
            lg = R.full_log(v["id"]); logs[n] = lg
            if R.on(lg, day):
                played[v["team"]].add(n)
        by_team = defaultdict(dict)
        for n, v in players.items():
            by_team[v["team"]][n] = v
        for team, roster in by_team.items():
            if not played[team]:
                continue
            for out_name, ov in roster.items():
                if out_name in played[team]:
                    continue
                olog = R.before(logs[out_name], day)
                reg = [g for g in olog if (g.get("min") or 0) > 0]
                if len(reg) < 5 or st.mean(g["min"] for g in reg[-10:]) < 20:
                    continue
                opos = ov.get("position") or ""
                for n, v in roster.items():
                    if n == out_name or n not in played[team] or n not in lines:
                        continue
                    if samepos and ((v.get("position") or "") != opos or not opos):
                        continue
                    blog = R.before(logs[n], day)
                    if len(blog) < 6:
                        continue
                    try:
                        w = W.wowy_multi(blog, [olog])
                    except Exception:
                        continue
                    if w["n_without"] > MAX_NWO:
                        continue
                    if w["with"]["min"]["mean"] < STARTER_MIN:
                        continue
                    ar = apart(on, pair, n, out_name, day)
                    if not ar:
                        continue
                    rate, mins = ar
                    if mins < MIN_APART:
                        continue
                    r5 = [g["min"] for g in blog[:5] if g["min"] > 8]
                    pm = st.median(r5) if r5 else w["with"]["min"]["mean"]
                    proj = rate * pm
                    lad = lines[n].get(stat) or {}
                    two = {k2: v2 for k2, v2 in lad.items() if v2 and v2[0] and v2[1]}
                    if not two:
                        continue
                    line = min(two, key=lambda x: abs(two[x][0] - two[x][1]))
                    price = two[line][0]
                    g = R.on(logs[n], day)
                    if not g or g.get(key) is None or abs(g[key] - line) < 1e-9:
                        continue
                    cand.append({"proj": proj, "line": line, "price": price,
                                 "hit": 1 if g[key] > line else 0, "player": n,
                                 "out": out_name, "date": day, "nwo": w["n_without"]})
    return cand


def report(stat, cand, margins=(0.0, 0.5, 1.0)):
    print(f"\n=== {stat.upper()} ===  {len(cand)} candidates")
    if not cand:
        print("   none passed the filters")
        return
    for m in margins:
        sel = [c for c in cand if c["proj"] - c["line"] >= m]
        if len(sel) < 6:
            print(f"   margin {m:<4} n={len(sel):<4} (too thin)")
            continue
        w_ = sum(c["hit"] for c in sel); l_ = len(sel) - w_
        u = sum((c["price"] - 1.0) if c["hit"] else -1.0 for c in sel)
        be = st.mean([1.0 / c["price"] for c in sel])
        hit = w_ / len(sel)
        print(f"   margin {m:<4} n={len(sel):<4} {w_}-{l_}  hit {100*hit:5.1f}%  "
              f"be {100*be:5.1f}%  edge {100*(hit-be):+6.1f}  {u:+7.2f}u")
    top = sorted(cand, key=lambda x: -(x["proj"] - x["line"]))[:5]
    for c in top:
        print(f"     {c['date']} {c['player']:<21} w/o {c['out']:<19} "
              f"proj {c['proj']:.1f} line {c['line']:g} "
              f"{'WIN' if c['hit'] else 'loss'}")


if __name__ == "__main__":
    con = sqlite3.connect(f"file:{R.HIST}?mode=ro", uri=True)
    days = [d for (d,) in con.execute(
        "SELECT DISTINCT game_date FROM props WHERE game_date>='2026-05-10' ORDER BY 1")]
    con.close()
    players = W.players()
    print(f"{len(days)} slates | starters, >=50min apart, same position, n_without<=2")
    for s_ in ("rebounds", "assists", "points"):
        report(s_, run(s_, days, players, samepos=True))
    print("\n--- points WITHOUT the same-position filter (user's hypothesis: wrong filter) ---")
    report("points", run("points", days, players, samepos=False))
