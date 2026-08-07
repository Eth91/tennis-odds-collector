#!/usr/bin/env python3
"""CONSISTENCY of the apart-shift, not its magnitude.

THE DIAGNOSIS THIS COMES FROM. The apart-rate is an UNBIASED predictor of absence-game
production — 1,258 pairs, predicted 8.44 vs actual 8.40 for points, 3.53 vs 3.55 for rebounds.
So the signal is not wrong. But we only bet when the apart-rate exceeds the overall rate by
enough to clear +10% EV, i.e. we deliberately select the most extreme readings of a noisy
measure. Extreme readings of a noisy measure are mostly noise. Winner's curse.

The tell was already visible: inside the rebound bets the LOWEST EV bucket won most (76%) while
higher EV buckets fell to 52%, in BOTH seasons. Biggest apparent edge = least reliable reading.

THE FIX UNDER TEST. Pooling hides whether a 1.4x shift came from ten games or one blowout.
Compute the shift PER GAME and score consistency:

    consistency = share of apart-games where the player's rate BEAT his overall rate

A shift of 1.15 that shows up in 8 of 10 games is a role change. A shift of 1.40 from one game
is not — and today's logic prefers the second.

PREDICTION, STATED FIRST: consistency should help POINTS more than REBOUNDS, because per-minute
scoring is the noisier signal. If it helps both equally it is not doing what I claim.
"""
import sys, sqlite3, statistics as st
from collections import defaultdict

STINT = "/home/ubuntu/tennis-odds-collector/wnba_stints.sqlite"
MIN_APART_GAME = 4.0      # a game only counts if they were apart this many minutes
MIN_GAMES = 5             # need this many such games to score consistency


def per_game(stat):
    tc, pc = {"points": ("pts", "pts_with"), "rebounds": ("reb", "reb_with"),
              "assists": ("ast", "ast_with")}[stat]
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
    """-> (pooled_shift, consistency, n_games, apart_min_total) using games before `before`."""
    games = []
    tot_s = tot_v = 0.0
    for (e, p), (d, sec, v) in on.items():
        if p != player or d >= before:
            continue
        tot_s += sec; tot_v += v
        ws, wv = pair.get((player, mate), {}).get(e, (0.0, 0.0))
        aps, apv = sec - ws, v - wv
        if aps / 60.0 >= MIN_APART_GAME:
            games.append((aps / 60.0, apv))
    if tot_s <= 0 or len(games) < MIN_GAMES:
        return None
    overall = tot_v / (tot_s / 60.0)
    if overall <= 0:
        return None
    apart_s = sum(g[0] for g in games)
    apart_v = sum(g[1] for g in games)
    pooled = (apart_v / apart_s) / overall
    beat = sum(1 for m, v in games if (v / m) > overall)
    return (pooled, beat / len(games), len(games), apart_s)


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

    for stat in ("rebounds", "points"):
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
                        pooled, cons, ng, apm = pr
                        lad = lines[n].get(stat) or {}
                        two = {k: x for k, x in lad.items() if x and x[0] and x[1]}
                        if not two:
                            continue
                        line = min(two, key=lambda x: abs(two[x][0] - two[x][1]))
                        g = R.on(logs[n], day)
                        if not g or g.get(key) is None or abs(g[key] - line) < 1e-9:
                            continue
                        rows.append({"pooled": pooled, "cons": cons, "n": ng,
                                     "hit": 1 if g[key] > line else 0, "dec": two[line][0]})

        print(f"\n=== {stat.upper()} — {len(rows)} candidate spots ===")

        def show(rs, tag):
            if len(rs) < 12:
                print(f"    {tag:<30} n={len(rs)} (thin)"); return
            w = sum(r["hit"] for r in rs); n = len(rs)
            be = st.mean([1.0 / r["dec"] for r in rs])
            u = sum((r["dec"] - 1.0) if r["hit"] else -1.0 for r in rs)
            print(f"    {tag:<30} n={n:<4} {w}-{n-w}  hit {100*w/n:5.1f}%  "
                  f"edge {100*(w/n-be):+6.1f}  {u:+7.2f}u")

        print("  -- today's rule: pooled shift > 1.0, selected on MAGNITUDE --")
        show([r for r in rows if r["pooled"] > 1.0], "pooled > 1.0")
        show([r for r in rows if r["pooled"] > 1.2], "pooled > 1.2 (bigger)")
        print("  -- proposed: CONSISTENCY --")
        for lo in (0.5, 0.6, 0.7):
            show([r for r in rows if r["cons"] >= lo], f"consistency >= {lo:.0%}")
        print("  -- both --")
        show([r for r in rows if r["pooled"] > 1.0 and r["cons"] >= 0.6],
             "pooled>1.0 AND cons>=60%")
        show([r for r in rows if r["pooled"] > 1.2 and r["cons"] < 0.5],
             "big shift but INCONSISTENT")


if __name__ == "__main__":
    main()
