#!/usr/bin/env python3
"""UNDER20 and UNDERML (NBA_UNDER_PREREG.md): the forward test of T2's under finding (NBA_TESTS4_PREREG.md).

UNDER20: at tip - 30, the under when our projection (ROLE1 v3 minutes x his rates) < 0.8 x FanDuel's main line.
UNDERML: T2's logistic model without the hindsight outs features (fit on 2023-24), either side at EV >= 5%.

    python3 nba_under.py --export      # refit UNDERML on 2023-24, write nba_under_model.py, check it (Mac only)
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path

import nba_boost as BOOST

RATIO_AT, EV_AT = 0.80, 0.05
PING_PRICE_MIN, PING_SKIP = 1 / 0.6, ("threes",)         # amendment 1: pinged when -150 or better, not threes
STRONG_AT = 0.70                                         # amendment 3: a star when the projection is under 70% of the line
MARKETS = tuple(BOOST.PARTS)
FEATURES = ("logit_q", "line", "proj/line", "min_change", "season_mpg", "recent", "rest", "b2b", "game_index") + \
    tuple(f"mk_{m}" for m in MARKETS)
MODEL_PY = Path(__file__).resolve().parent / "nba_under_model.py"
NAN = float("nan")


def projection(bd, rd, pid, team, date, out_all, market):
    """(V3 minutes, projected stat) or None."""
    v3 = BOOST.v3_minutes(bd, rd, team, date, out_all).get(pid)
    rt = BOOST.rates(bd, pid, date)
    if v3 is None or not rt:
        return None
    return v3, v3 * sum(rt[s] for s in BOOST.PARTS[market])


def under20(bd, rd, date, team, pid, market, line, under_price, out_all):
    """UNDER20: the under when the projection is under 80% of the line (no price cap, as tested)."""
    if pid in out_all or not under_price or not line:
        return None
    pr = projection(bd, rd, pid, team, date, out_all, market)
    if pr and pr[1] < RATIO_AT * line:
        return {"side": "under", "price": under_price, "proj": pr[1], "min": pr[0], "ratio": pr[1] / line}
    return None


def pings(f, market):
    """Amendment 1: an UNDER20 flag pings when the under is -150 or better and the market is not threes (UNDER20P)."""
    return f["price"] >= PING_PRICE_MIN - 1e-9 and market not in PING_SKIP


def strong(f):
    """Amendment 3: the projection is under 70% of the line (UNDER30P)."""
    return f["ratio"] < STRONG_AT


def features(bd, rd, date, team, pid, market, line, q, out_all):
    """UNDERML's inputs in FEATURES order (as nba_tests4.context and nba_tests4_checks.py build them), or None."""
    pr = projection(bd, rd, pid, team, date, out_all, market)
    if pr is None or not (0 < q < 1) or not line:
        return None
    v3, proj = pr
    mine = bd.his(pid, date)
    last10 = [x["min"] for x in mine[-10:]]
    this = [x for x in mine if x["season"] == bd.season]
    gap = (dt.date.fromisoformat(date) - dt.date.fromisoformat(mine[-1]["date"])).days if mine else 4
    mean = lambda xs: sum(xs) / len(xs)
    rec = []
    for s in BOOST.PARTS[market]:
        if s in ("pts", "reb", "ast", "fg3m") and this and mine:
            rec.append(mean([x[s] or 0 for x in mine[-5:]]) / max(1e-9, mean([x[s] or 0 for x in this])))
    x = [math.log(q / (1 - q)), line, proj / line, v3 - (mean(last10) if last10 else v3),
         mean([r["min"] for r in this]) if this else NAN, mean(rec) if rec else NAN, min(4, gap), float(gap <= 1),
         sum(1 for _d, _g, s, _b in bd.before(team, date) if s == bd.season)] + [float(market == m) for m in MARKETS]
    return x


def predict(model, x):
    """P(over) from the exported logistic model; a missing input takes its 2023-24 median."""
    z = model["intercept"]
    for v, med, mu, sd, w in zip(x, model["median"], model["mean"], model["scale"], model["coef"]):
        v = med if v != v else v
        z += w * (v - mu) / sd
    return 1 / (1 + math.exp(-z))


_MODEL = {}


def underml(bd, rd, date, team, pid, market, line, over, under, out_all, model=None):
    """UNDERML: the side with p x FanDuel's price - 1 >= 5%, or None."""
    if pid in out_all or not over or not under:
        return None
    if model is None:
        if "m" not in _MODEL:
            import nba_under_model
            _MODEL["m"] = nba_under_model.MODEL
        model = _MODEL["m"]
    q = (1 / over) / (1 / over + 1 / under)
    x = features(bd, rd, date, team, pid, market, line, q, out_all)
    if x is None:
        return None
    p = predict(model, x)
    if p * over - 1 >= EV_AT:
        return {"side": "over", "price": over, "p": p, "ev": p * over - 1}
    if (1 - p) * under - 1 >= EV_AT:
        return {"side": "under", "price": under, "p": p, "ev": (1 - p) * under - 1}
    return None


def export():
    """Refit the no-hindsight logistic model on 2023-24 exactly as nba_tests4_checks.py does, write nba_under_model.py,
    and check (1) it equals scikit-learn's predictions on 2024-25 and (2) features() equals the backtest's inputs."""
    import json
    import types

    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    import nba_lowend as LO
    import nba_minutes as M
    import nba_tests4 as T
    rows_db, pos, five = LO.load()
    lines = T.tip_lines()
    data, live_x = {}, {}
    for s in ("2023-24", "2024-25"):
        season = M.Season(s, rows_db, pos, five)
        rd = types.SimpleNamespace(season=season.role, priors=season.priors, groups=season.groups)
        data[s] = []
        for r in T.player_games(season):
            T.context(season, r)
            box = season.bd.games[r["team"]]
            for mk in MARKETS:
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
                     float(np.nanmean(rec)) if rec else np.nan, c["rest"], c["b2b"], c["game_index"]] + [float(mk == m) for m in MARKETS]
                data[s].append((x, int(act > line), over, under))
                if s == "2024-25" and len(live_x) < 3000:
                    played = {p for d, _g, _s, b in box if d == r["date"] for p, v in b.items() if v["min"]}
                    usual = season.bd.usual_five(r["team"], r["date"]) or season.bd.starters(r["team"], r["date"])
                    out_all = (season.bd.on_team_tonight(r["team"], r["date"]) - played) & (season.bd.roster(r["team"], r["date"]) | usual)
                    live_x[len(live_x)] = (x, features(season.bd, rd, r["date"], r["team"], r["pid"], mk, line, q, out_all))
    X = {s: np.array([d[0] for d in data[s]], dtype=float) for s in data}
    y = {s: np.array([d[1] for d in data[s]]) for s in data}
    med = np.nanmedian(X["2023-24"], axis=0)
    Xf = {s: np.where(np.isnan(X[s]), med, X[s]) for s in X}
    sc = StandardScaler().fit(Xf["2023-24"])
    m = LogisticRegression(C=1.0, max_iter=3000).fit(sc.transform(Xf["2023-24"]), y["2023-24"])
    model = {"features": list(FEATURES), "median": med.tolist(), "mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(),
             "coef": m.coef_[0].tolist(), "intercept": float(m.intercept_[0])}
    MODEL_PY.write_text('"""Generated by `python3 nba_under.py --export` (NBA_UNDER_PREREG.md): UNDERML\'s logistic model, fit on\n'
                        '2023-24 without the hindsight outs features. Do not edit."""\nimport json\n\n'
                        "MODEL = json.loads(r'''" + json.dumps(model) + "''')\n")
    p_sk = m.predict_proba(sc.transform(Xf["2024-25"]))[:, 1]
    p_us = np.array([predict(model, list(x)) for x in X["2024-25"]])
    diff = float(np.max(np.abs(p_sk - p_us)))
    assert diff < 1e-9, f"the exported model differs from scikit-learn by {diff}"
    bad = sum(1 for a, b in live_x.values() if b is None or any(not ((u != u and v != v) or abs(u - v) < 1e-9) for u, v in zip(a, b)))
    assert bad == 0, f"features() differs from the backtest's inputs on {bad} of {len(live_x)} rows"
    us = []
    for p, (_x, yy, over, under) in zip(p_us, data["2024-25"]):
        if p * over - 1 >= EV_AT:
            us.append(over - 1 if yy else -1.0)
        elif (1 - p) * under - 1 >= EV_AT:
            us.append(under - 1 if not yy else -1.0)
    print(f"wrote {MODEL_PY.name}: matches scikit-learn (max diff {diff:.1e}); features() matches the backtest on {len(live_x)} rows; "
          f"2024-25 EV>=5% bets {len(us)}, ROI {np.mean(us):+.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    a = ap.parse_args()
    if a.export:
        export()


if __name__ == "__main__":
    main()
