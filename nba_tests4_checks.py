"""NBA_TESTS4_PREREG.md, after the result: robustness checks on T2's logistic model (FanDuel-only prices, no hindsight
outs features, by side, market, half and EV band) and the bet-the-under baselines. Post-hoc: information, not a test."""
import sys, json, math, sqlite3
from collections import defaultdict
import numpy as np
sys.path.insert(0, ".")
import nba_tests4 as T, nba_lowend as LO, nba_minutes as M, nba_boost as BOOST, nba_margin_refit as MR
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
rows_db, pos, five = LO.load()
lines = T.tip_lines()
# FanDuel-only prices at the same main rung
g = sqlite3.connect(f"file:{M.GAMELOGS}?mode=ro", uri=True)
name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
o = sqlite3.connect(f"file:{M.ODDS}?mode=ro", uri=True)
fd = defaultdict(dict)
for d, pl, m, line, side, price in o.execute("SELECT game_date, player, market, line, side, price FROM props WHERE book='fanduel' AND price IS NOT NULL"):
    pid = name2pid.get(MR.norm(pl))
    if pid is not None and m in BOOST.ODDS_MARKETS:
        fd[(d, pid, BOOST.ODDS_MARKETS[m], float(line))][side] = float(price)
seasons, rows = {}, {}
for s in ("2023-24", "2024-25"):
    seasons[s] = M.Season(s, rows_db, pos, five)
    rows[s] = T.player_games(seasons[s])
    for r in rows[s]:
        T.context(seasons[s], r)
NAMES = ["logit_q", "line", "proj/line", "min_change", "season_mpg", "recent", "n_out", "new_starter", "x_out", "min_absence",
         "rest", "b2b", "game_index"] + [f"mk_{m}" for m in T.MARKETS]
data = {s: [] for s in rows}
for s in rows:
    for r in rows[s]:
        for mk in T.MARKETS:
            ln = lines.get((r["date"], r["pid"], mk))
            if not ln:
                continue
            line, over, under, q = ln
            act = BOOST.stat_of(r["box"], mk)
            if act == line:
                continue
            c = r["ctx"]
            rec = [r["recent"][p] for p in BOOST.PARTS[mk] if p in r["recent"]]
            x = [math.log(q / (1 - q)), line, T.proj(r, mk) / line, c["min_change"], c["season_mpg"],
                 float(np.nanmean(rec)) if rec else np.nan, c["n_out"], c["new_starter"], c["x_out"], c["min_absence"],
                 c["rest"], c["b2b"], c["game_index"]] + [float(mk == m) for m in T.MARKETS]
            f = fd.get((r["date"], r["pid"], mk, line), {})
            data[s].append({"x": x, "y": int(act > line), "over": over, "under": under, "q": q, "mk": mk, "date": r["date"],
                            "fd_over": f.get("over"), "fd_under": f.get("under")})
def run(drop=(), price="best", tag=""):
    keep = [i for i, n in enumerate(NAMES) if n not in drop]
    X = {s: np.array([[d["x"][i] for i in keep] for d in data[s]], dtype=float) for s in data}
    y = {s: np.array([d["y"] for d in data[s]]) for s in data}
    med = np.nanmedian(X["2023-24"], axis=0)
    Xf = {s: np.where(np.isnan(X[s]), med, X[s]) for s in X}
    sc = StandardScaler().fit(Xf["2023-24"])
    m = LogisticRegression(C=1.0, max_iter=3000).fit(sc.transform(Xf["2023-24"]), y["2023-24"])
    p = m.predict_proba(sc.transform(Xf["2024-25"]))[:, 1]
    q = np.array([d["q"] for d in data["2024-25"]])
    ll = lambda pp: float(-np.mean(y["2024-25"] * np.log(pp) + (1 - y["2024-25"]) * np.log(1 - pp)))
    bets = defaultdict(list)
    for pi, d in zip(p, data["2024-25"]):
        ov, un = (d["over"], d["under"]) if price == "best" else (d["fd_over"], d["fd_under"])
        if not ov or not un:
            continue
        if pi * ov - 1 >= 0.05:
            u = ov - 1 if d["y"] else -1.0; side = "over"
        elif (1 - pi) * un - 1 >= 0.05:
            u = un - 1 if not d["y"] else -1.0; side = "under"
        else:
            continue
        bets["all"].append(u); bets[side].append(u); bets["mk " + d["mk"]].append(u)
        bets["half " + ("1" if d["date"] < "2025-01-15" else "2")].append(u)
        ev = max(pi * ov, (1 - pi) * un) - 1
        bets["EV " + ("5-8%" if ev < 0.08 else "8-12%" if ev < 0.12 else "12%+")].append(u)
    print(f"\n== {tag}: log loss model {ll(p):.5f} vs book {ll(q):.5f}")
    for k in sorted(bets):
        v = np.array(bets[k]); print(f"   {k:16s} n {len(v):6d}  ROI {v.mean():+.4f}")
    return m, keep
m, keep = run(tag="as registered (best of FD/DK)")
print("   coefficients (standardized):", {NAMES[i]: round(float(c), 3) for i, c in zip(keep, m.coef_[0])})
run(price="fd", tag="FanDuel's own prices only")
run(drop=("n_out", "new_starter", "x_out", "min_absence"), tag="without the hindsight outs features")
run(drop=("n_out", "new_starter", "x_out", "min_absence"), price="fd", tag="no hindsight features, FanDuel only")

print("\n== baselines: is it just 'bet the under'?")
for s in ("2023-24", "2024-25"):
    ds = data[s]
    yy = np.array([d["y"] for d in ds]); qq = np.array([d["q"] for d in ds])
    print(f" {s}: over rate {yy.mean():.4f} vs book no-vig over {qq.mean():.4f} (n {len(ds)})")
    for name, sel in (("every under, best price", lambda d: True),
                      ("unders, projection < 0.9 x line", lambda d: d["x"][2] < 0.9),
                      ("unders, projection < 0.8 x line", lambda d: d["x"][2] < 0.8)):
        us = [d["under"] - 1 if not d["y"] else -1.0 for d in ds if sel(d)]
        uf = [d["fd_under"] - 1 if not d["y"] else -1.0 for d in ds if sel(d) and d["fd_under"]]
        print(f"   {name:34s} n {len(us):6d} ROI {np.mean(us):+.4f} | FanDuel price n {len(uf):6d} ROI {np.mean(uf):+.4f}")
