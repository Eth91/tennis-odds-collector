#!/usr/bin/env python3
"""Per-game shift RELIABILITY (t-statistic), not a share-of-games count.

WHY THE LAST ATTEMPT FAILED. Counting "share of apart-games that beat the player's own average"
does not discriminate: a player beats his own average in roughly half his games by construction,
so >=60% is rare and the filter just cut volume — 11 and 9 bets, with the decisive
"big shift but inconsistent" cell holding 1 bet and 0. Untested, not disproven.

WHAT THIS MEASURES INSTEAD. Treat each apart-game as one observation of the player's rate and
ask whether the mean is reliably above his overall rate, given how much it bounces:

    t = (mean(apart game rates) - overall rate) / (sd / sqrt(games))

That separates the two things magnitude cannot: 1.15 across ten steady games scores HIGH,
1.40 from one outlier scores LOW. It is exactly the winner's-curse correction — the current
rule prefers the second because it only sees the pooled number.

PREDICTION, STATED FIRST: if winner's curse is the problem, high-t should beat high-magnitude,
and the low-t/high-magnitude cell should be the worst. If t adds nothing over the pooled shift,
the stint idea is done — this is the fourth measure tried on it.
"""
import sys, sqlite3, math, statistics as st
from collections import defaultdict

STINT = "/home/ubuntu/tennis-odds-collector/wnba_stints.sqlite"
MIN_APART_GAME = 4.0
MIN_GAMES = 6


def per_game(stat):
    tc, pc = {"points": ("pts", "pts_with"), "rebounds": ("reb", "reb_with")}[stat]
    c = sqlite3.connect(f"file:{STINT}?mode=ro", uri=True)
    ok = {e for (e,) in c.execute("SELECT event_id FROM games WHERE status='ok'")}
    on = {}
    for e, d, p, sec, v in c.execute(f"SELECT event_id,game_date,player,sec,{tc} FROM onfloor"):
        if e in ok and v is not None:
            on[(e, p)] = (d, sec or 0.0, v)
    pair = defaultdict(dict)
    for e, d, p, m, sec, v in c.execute(
            f"SELECT event_id,game_date,player,mate,sec,{pc} FROM pairs"):
        if e in ok and v is not None:
            pair[(p, m)][e] = (sec or 0.0, v)
    c.close()
    return on, pair


def profile(on, pair, player, mate, before):
    """-> (pooled_shift, t_stat, n_games) from games strictly before `before`."""
    rates, tot_s, tot_v = [], 0.0, 0.0
    apart_s = apart_v = 0.0
    for (e, p), (d, sec, v) in on.items():
        if p != player or d >= before:
            continue
        tot_s += sec; tot_v += v
        ws, wv = pair.get((player, mate), {}).get(e, (0.0, 0.0))
        aps, apv = sec - ws, v - wv
        m = aps / 60.0
        if m >= MIN_APART_GAME:
            rates.append(apv / m)
            apart_s += m; apart_v += apv
    if tot_s <= 0 or len(rates) < MIN_GAMES:
        return None
    overall = tot_v / (tot_s / 60.0)
    if overall <= 0 or apart_s <= 0:
        return None
    pooled = (apart_v / apart_s) / overall
    sd = st.pstdev(rates)
    if sd <= 0:
        return None
    t = (st.mean(rates) - overall) / (sd / math.sqrt(len(rates)))
    return (pooled, t, len(rates))


def main():
    sys.path.insert(0, "/home/ubuntu")
    _a = list(sys.argv); sys.argv = ["x"]
    import wnba_replay as R
    import wnba_wowy as W
    sys.argv = _a
    con = sqlite3.connect(f"file:{R.HIST}?mode=ro", uri=True)
    days = [d for (d,) in con.execute(
        "SELECT DISTINCT game_date FROM props WHERE game_date>='2026-05-10' ORDER BY 1")]
    con.close()
    players = W.players()

    for stat in ("points", "rebounds"):
        on, pair = per_game(stat)
        key = {"rebounds": "reb", "points": "pts"}[stat]
        rows = []
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
            byt = defaultdict(dict)
            for n, v in players.items():
                byt[v["team"]][n] = v
            for team, roster in byt.items():
                if not played[team]:
                    continue
                for out_name, ov in roster.items():
                    if out_name in played[team] or not ov.get("position"):
                        continue
                    ol = R.before(logs[out_name], day)
                    reg = [g for g in ol if (g.get("min") or 0) > 0]
                    if len(reg) < 5 or st.mean(g["min"] for g in reg[-10:]) < 20:
                        continue
                    for n, v in roster.items():
                        if n == out_name or n not in lines:
                            continue
                        if v.get("position") != ov["position"]:
                            continue
                        pr = profile(on, pair, n, out_name, day)
                        if not pr:
                            continue
                        pooled, t, ng = pr
                        lad = lines[n].get(stat) or {}
                        two = {k: x for k, x in lad.items() if x and x[0] and x[1]}
                        if not two:
                            continue
                        line = min(two, key=lambda x: abs(two[x][0] - two[x][1]))
                        g = R.on(logs[n], day)
                        if not g or g.get(key) is None or abs(g[key] - line) < 1e-9:
                            continue
                        rows.append({"pooled": pooled, "t": t, "n": ng,
                                     "hit": 1 if g[key] > line else 0, "dec": two[line][0]})

        print(f"\n=== {stat.upper()} — {len(rows)} candidate spots ===")

        def show(rs, tag):
            if len(rs) < 15:
                print(f"    {tag:<32} n={len(rs)} (thin)"); return
            w = sum(r["hit"] for r in rs); n = len(rs)
            be = st.mean([1.0 / r["dec"] for r in rs])
            u = sum((r["dec"] - 1.0) if r["hit"] else -1.0 for r in rs)
            print(f"    {tag:<32} n={n:<4} {w}-{n-w}  hit {100*w/n:5.1f}%  "
                  f"edge {100*(w/n-be):+6.1f}  {u:+7.2f}u")

        show(rows, "ALL candidates")
        print("  -- current rule: pooled magnitude --")
        show([r for r in rows if r["pooled"] > 1.0], "pooled > 1.0")
        print("  -- proposed: reliability (t) --")
        for lo in (0.0, 0.5, 1.0, 1.5):
            show([r for r in rows if r["t"] >= lo], f"t >= {lo:.1f}")
        print("  -- the decisive contrast --")
        med = st.median([r["pooled"] for r in rows]) if rows else 1.0
        show([r for r in rows if r["pooled"] > med and r["t"] >= 1.0],
             "big shift AND reliable")
        show([r for r in rows if r["pooled"] > med and r["t"] < 0.5],
             "big shift but UNRELIABLE")


if __name__ == "__main__":
    main()
