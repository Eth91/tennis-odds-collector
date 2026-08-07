#!/usr/bin/env python3
"""2025 HOLDOUT for the per-game reliability (t) signal.

PRE-REGISTERED, decided before this ran: on POINTS, `t >= 0.5` must beat the current pooled
rule (`pooled > 1.0`) in 2025 as well, and the "big shift but UNRELIABLE" cell must stay the
weaker one. Anything else and this joins the pile with the pooled, shrinkage and count versions.

2026 result being tested: pooled>1.0 56.8% (+4.6) · t>=0.5 60.9% (+8.4) · t>=1.0 63.2% (+11.6);
big-shift-AND-reliable 63.2% vs big-shift-but-UNRELIABLE 50.7% on 134 bets.

Self-contained on 2025: wnba_boxscores (results+minutes) + wnba_props_2025 (real book lines) +
wnba_stints (on/off, repaired 2026-08-07). Same filters as the 2026 run: same position, out
player a regular, walk-forward throughout.
"""
import sys, sqlite3, math, statistics as st
from collections import defaultdict

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_wowy as W

STINT = "/home/ubuntu/tennis-odds-collector/wnba_stints.sqlite"
BOX = "/home/ubuntu/tennis-odds-collector/wnba_boxscores.sqlite"
PROPS = "/home/ubuntu/tennis-odds-collector/wnba_props_2025.sqlite"
MIN_APART_GAME, MIN_GAMES = 4.0, 6
SPEC = {"points": ("pts", "pts_with", "player_points", "pts"),
        "rebounds": ("reb", "reb_with", "player_rebounds", "reb")}


def per_game(stat):
    tc, pc, _, _ = SPEC[stat]
    c = sqlite3.connect(f"file:{STINT}?mode=ro", uri=True)
    ok = {e for (e,) in c.execute("SELECT event_id FROM games WHERE status='ok'")}
    on, pair = {}, defaultdict(dict)
    for e, d, p, sec, v in c.execute(f"SELECT event_id,game_date,player,sec,{tc} FROM onfloor"):
        if e in ok and v is not None and d < "2026-01-01":
            on[(e, p)] = (d, sec or 0.0, v)
    for e, d, p, m, sec, v in c.execute(
            f"SELECT event_id,game_date,player,mate,sec,{pc} FROM pairs"):
        if e in ok and v is not None and d < "2026-01-01":
            pair[(p, m)][e] = (sec or 0.0, v)
    c.close()
    return on, pair


def profile(on, pair, player, mate, before):
    rates, tot_s, tot_v, ap_s, ap_v = [], 0.0, 0.0, 0.0, 0.0
    for (e, p), (d, sec, v) in on.items():
        if p != player or d >= before:
            continue
        tot_s += sec; tot_v += v
        ws, wv = pair.get((player, mate), {}).get(e, (0.0, 0.0))
        m = (sec - ws) / 60.0
        if m >= MIN_APART_GAME:
            rates.append((v - wv) / m); ap_s += m; ap_v += (v - wv)
    if tot_s <= 0 or len(rates) < MIN_GAMES or ap_s <= 0:
        return None
    overall = tot_v / (tot_s / 60.0)
    sd = st.pstdev(rates)
    if overall <= 0 or sd <= 0:
        return None
    return ((ap_v / ap_s) / overall,
            (st.mean(rates) - overall) / (sd / math.sqrt(len(rates))), len(rates))


def main():
    b = sqlite3.connect(f"file:{BOX}?mode=ro", uri=True)
    log, team_of, appeared, tdates = defaultdict(list), {}, defaultdict(set), defaultdict(set)
    for gid, d, tm, pl, mn, pts, reb in b.execute(
            "SELECT game_id,game_date,team,player,min,pts,reb FROM box WHERE min IS NOT NULL"):
        log[pl].append({"d": d, "gid": gid, "min": mn or 0, "pts": pts or 0, "reb": reb or 0})
        team_of[pl] = tm; tdates[tm].add(d)
        if (mn or 0) > 0:
            appeared[(d, tm)].add(pl)
    for k in log:
        log[k].sort(key=lambda x: x["d"])
    roster = defaultdict(set)
    for pl, tm in team_of.items():
        roster[tm].add(pl)
    pmap = W.players()

    for stat in ("points", "rebounds"):
        _tc, _pc, mk, key = SPEC[stat]
        p = sqlite3.connect(f"file:{PROPS}?mode=ro", uri=True)
        L = defaultdict(lambda: defaultdict(dict))
        for d, pl, ln, side, pr in p.execute(
                "SELECT game_date,player,line,side,price FROM props WHERE market=?", (mk,)):
            if side in ("over", "under") and ln is not None and pr:
                L[d][pl].setdefault(round(float(ln), 1), {})[side] = float(pr)
        p.close()
        on, pair = per_game(stat)

        rows = []
        for tm, ros in roster.items():
            for day in sorted(tdates[tm]):
                app = appeared.get((day, tm), set())
                if not app or day not in L:
                    continue
                prior = {n: [g for g in log[n] if g["d"] < day] for n in ros}
                for out_name in ros:
                    if out_name in app:
                        continue
                    ov = pmap.get(out_name)
                    if not ov or not ov.get("position"):
                        continue
                    og = [g for g in prior.get(out_name, []) if g["min"] > 0]
                    if len(og) < 5 or st.mean(g["min"] for g in og[-10:]) < 20:
                        continue
                    for n in app:
                        nv = pmap.get(n)
                        if n == out_name or not nv or nv.get("position") != ov["position"]:
                            continue
                        pr2 = profile(on, pair, n, out_name, day)
                        if not pr2:
                            continue
                        pooled, t, ng = pr2
                        lad = {k: v for k, v in L[day].get(n, {}).items()
                               if "over" in v and "under" in v}
                        if not lad:
                            continue
                        line = min(lad, key=lambda x: abs(lad[x]["over"] - lad[x]["under"]))
                        act = [g for g in log[n] if g["d"] == day and g["min"] > 0]
                        if not act or abs(act[0][key] - line) < 1e-9:
                            continue
                        rows.append({"pooled": pooled, "t": t,
                                     "hit": 1 if act[0][key] > line else 0,
                                     "dec": lad[line]["over"]})

        print(f"\n=== 2025 HOLDOUT — {stat.upper()} — {len(rows)} spots ===")

        def show(rs, tag):
            if len(rs) < 15:
                print(f"    {tag:<32} n={len(rs)} (thin)"); return
            w = sum(r["hit"] for r in rs); n = len(rs)
            be = st.mean([1.0 / r["dec"] for r in rs])
            u = sum((r["dec"] - 1.0) if r["hit"] else -1.0 for r in rs)
            print(f"    {tag:<32} n={n:<4} {w}-{n-w}  hit {100*w/n:5.1f}%  "
                  f"edge {100*(w/n-be):+6.1f}  {u:+7.2f}u")

        show(rows, "ALL candidates")
        show([r for r in rows if r["pooled"] > 1.0], "pooled > 1.0  (current rule)")
        for lo in (0.0, 0.5, 1.0):
            show([r for r in rows if r["t"] >= lo], f"t >= {lo:.1f}")
        med = st.median([r["pooled"] for r in rows]) if rows else 1.0
        show([r for r in rows if r["pooled"] > med and r["t"] >= 1.0], "big shift AND reliable")
        show([r for r in rows if r["pooled"] > med and r["t"] < 0.5], "big shift but UNRELIABLE")


if __name__ == "__main__":
    main()
