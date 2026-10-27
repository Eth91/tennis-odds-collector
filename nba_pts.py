#!/usr/bin/env python3
"""The user's points process, encoded (NBA_PTS_PREREG.md): volume x efficiency by shot zone x the opponent's zone
defense, as expected points (xPTS, xPTS_m), plus the raw ratios and efficiencies, at the archive's tip lines.
Solver A sweeps one threshold on xPTS_m / line; solver B learns each stat's weight beyond the line (L2 logistic),
fit on one season and tested on the other, both ways. Every feature is season to date, before the game's date.

    python3 nba_pts.py --gamelogs .projdata/nba_gamelogs.sqlite --shots .projdata/shots_hist.sqlite \
        --odds ~/nba-engine/basketball_nba_odds_hist.sqlite [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_margin_refit as MR
import nba_zones as Z

SEASONS = ("2023-24", "2024-25")
FDK = ("fanduel", "draftkings")
ZONES = Z.ZONES
VAL = {"ra": 2, "paint": 2, "mid": 2, "c3": 3, "ab3": 3}
K_ZONE, K_FT, MIN_GAMES, OPP_GAMES, MIN_MPG = 20.0, 20.0, 5, 10, 20.0
K_GRID = [round(0.90 + 0.02 * i, 2) for i in range(26)]
FEATURES = ("logit_book", "fga_r", "fg3a_r", "fta_r", "xpts_r", "xptsm_r", "fg_pct", "fg3_pct", "ft_pct", "efg", "ts",
            "fg3_share", "mpg")
EV_AT, MIN_PICK, LAMBDAS = 0.03, 150, (0.01, 0.1, 1.0, 10.0, 100.0)


def props(odds_db, name2pid):
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, pl, line, side, price, book in o.execute("SELECT game_date, player, line, side, price, book FROM props WHERE "
                                                    "market = 'player_points' AND price IS NOT NULL AND line IS NOT NULL"):
        if book in FDK:
            raw[(d, name2pid.get(MR.norm(pl)))][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    out = {}
    for k, lb in raw.items():
        best = None
        for line, bk in lb.items():
            two = {b: v for b, v in bk.items() if v[0] and v[1]}
            if two:
                gap = min(abs(v[0] - 2.0) for v in two.values())
                if best is None or gap < best[0]:
                    best = (gap, line, two)
        if best:
            _g, line, two = best
            pair = two.get("fanduel") or two.get("draftkings")
            out[k] = (line, max(v[0] for v in two.values()), (1 / pair[0]) / (1 / pair[0] + 1 / pair[1]))
    return out


def build(gamelogs_db, shots_db, odds_db):
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    lines = props(odds_db, name2pid)
    s = sqlite3.connect(f"file:{shots_db}?mode=ro", uri=True)
    shots = defaultdict(list)                            # gid -> [(pid, zone, made)]
    for gid, pid, x, y, made in s.execute("SELECT gid, pid, x, y, made FROM shots"):
        shots[gid].append((pid, Z.zone(x, y), made))
    rows = []
    for season in SEASONS:
        by_date, teams_of = defaultdict(list), defaultdict(set)
        for d, gid, team, pid, mn, fga, fgm, fg3a, fg3m, fta, ftm, pts in g.execute(
                "SELECT date, game_id, team, player_id, min, fga, fgm, fg3a, fg3m, fta, ftm, pts FROM logs_full WHERE season = ?", (season,)):
            teams_of[gid].add(team)
            if mn:
                by_date[d].append((gid, team, pid, {"min": mn, "fga": fga or 0, "fgm": fgm or 0, "fg3a": fg3a or 0, "fg3m": fg3m or 0,
                                                    "fta": fta or 0, "ftm": ftm or 0, "pts": pts or 0}))
        P = defaultdict(lambda: {"n": 0, "box": defaultdict(float), "A": defaultdict(float), "M": defaultdict(float)})
        lg = {"A": defaultdict(float), "M": defaultdict(float), "fta": 0.0, "ftm": 0.0, "zone_pts": defaultdict(float), "tg": 0}
        allowed = defaultdict(lambda: {"n": 0, "pts": defaultdict(float)})
        for d in sorted(by_date):
            for gid, team, pid, box in by_date[d]:
                ps, key = P[pid], (d, pid)
                if ps["n"] < MIN_GAMES or key not in lines:
                    continue
                line, over, q = lines[key]
                n, b = ps["n"], ps["box"]
                opp = next((t for t in teams_of[gid] if t != team), None)
                pct = {z: (ps["M"][z] + K_ZONE * (lg["M"][z] / lg["A"][z] if lg["A"][z] else 0.4)) / (ps["A"][z] + K_ZONE) for z in ZONES}
                ft = (b["ftm"] + K_FT * (lg["ftm"] / lg["fta"] if lg["fta"] else 0.78)) / (b["fta"] + K_FT)
                zone_pts = {z: ps["A"][z] / n * pct[z] * VAL[z] for z in ZONES}
                xpts = sum(zone_pts.values()) + b["fta"] / n * ft
                xptsm = None
                if opp and allowed[opp]["n"] >= OPP_GAMES and lg["tg"]:
                    al = allowed[opp]
                    allow = {z: (al["pts"][z] / al["n"]) / (lg["zone_pts"][z] / lg["tg"]) if lg["zone_pts"][z] else 1.0 for z in ZONES}
                    xptsm = sum(zone_pts[z] * allow[z] for z in ZONES) + b["fta"] / n * ft
                fga, fta = b["fga"], b["fta"]
                act = box["pts"]
                rows.append({"season": season, "date": d, "pid": pid, "line": line, "over": over, "q": q, "actual": act,
                             "u": 0.0 if act == line else (over - 1 if act > line else -1.0),
                             "mpg": b["min"] / n, "fga_r": fga / n / line, "fg3a_r": b["fg3a"] / n / line, "fta_r": fta / n / line,
                             "xpts_r": xpts / line, "xptsm_r": xptsm / line if xptsm is not None else None,
                             "fg_pct": b["fgm"] / fga if fga else 0.0, "fg3_pct": b["fg3m"] / b["fg3a"] if b["fg3a"] else 0.0,
                             "ft_pct": b["ftm"] / fta if fta else 0.0, "efg": (b["fgm"] + 0.5 * b["fg3m"]) / fga if fga else 0.0,
                             "ts": b["pts"] / (2 * (fga + 0.44 * fta)) if fga + fta else 0.0, "fg3_share": b["fg3a"] / fga if fga else 0.0,
                             "logit_book": math.log(q / (1 - q))})
            for gid in {x[0] for x in by_date[d]}:            # the date's games join the season-to-date state
                for t in teams_of[gid]:
                    allowed[t]["n"] += 1
                    lg["tg"] += 1
                team_of = {pid: team for g_, team, pid, _b in by_date[d] if g_ == gid}
                for pid, z, made in shots.get(gid, ()):
                    t = team_of.get(pid)
                    if t is None:
                        continue
                    P[pid]["A"][z] += 1
                    P[pid]["M"][z] += made
                    lg["A"][z] += 1
                    lg["M"][z] += made
                    opp = next((x for x in teams_of[gid] if x != t), None)
                    if made and opp:
                        allowed[opp]["pts"][z] += VAL[z]
                        lg["zone_pts"][z] += VAL[z]
            for gid, team, pid, box in by_date[d]:
                ps = P[pid]
                ps["n"] += 1
                for k, v in box.items():
                    ps["box"][k] += v
                lg["fta"] += box["fta"]
                lg["ftm"] += box["ftm"]
    return rows


def summ(rs):
    if not rs:
        return {"n": 0}
    np_ = [r for r in rs if r["actual"] != r["line"]]
    return {"n": len(rs), "hit": round(float(np.mean([r["actual"] > r["line"] for r in np_])), 4) if np_ else None,
            "roi": round(float(np.mean([r["u"] for r in rs])), 4)}


def solver_a(rows, key="xptsm_r"):
    base = [r for r in rows if r["mpg"] >= MIN_MPG and r[key] is not None]
    curve = {k: {s: summ([r for r in base if r["season"] == s and r[key] >= k]) for s in SEASONS} for k in K_GRID}
    out = {"curve": {str(k): v for k, v in curve.items()}, "all_overs_20min": {s: summ([r for r in base if r["season"] == s]) for s in SEASONS},
           "checks": {}}
    for fit, chk in ((SEASONS[0], SEASONS[1]), (SEASONS[1], SEASONS[0])):
        ok = [k for k in K_GRID if curve[k][fit].get("n", 0) >= MIN_PICK]
        if not ok:
            continue
        k = max(ok, key=lambda x: curve[x][fit]["roi"])
        i = K_GRID.index(k)
        nb = [K_GRID[j] for j in (i - 1, i + 1) if 0 <= j < len(K_GRID)]
        out["checks"][f"pick on {fit}"] = {"k": k, "fit": curve[k][fit], "check": curve[k][chk], "neighbours": {str(x): curve[x] for x in nb}}
    picks = list(out["checks"].values())
    out["passes"] = len(picks) == 2 and all(
        v["check"].get("n") and v["check"]["roi"] > 0 and all(n_[s].get("roi", -1) > 0 for n_ in v["neighbours"].values() for s in SEASONS)
        for v in picks)
    return out


def logistic(X, y, lam):
    """L2-penalized logistic regression by Newton's method; the intercept (column 0) is not penalized."""
    w = np.zeros(X.shape[1])
    pen = np.full(X.shape[1], lam)
    pen[0] = 0.0
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + pen * w
        H = (X * (p * (1 - p))[:, None]).T @ X + np.diag(pen)
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def design(rs, mu=None, sd=None):
    F = np.array([[r[f] for f in FEATURES] for r in rs], float)
    if mu is None:
        mu, sd = F.mean(0), F.std(0)
        sd[sd == 0] = 1.0
    return np.hstack([np.ones((len(rs), 1)), (F - mu) / sd]), mu, sd


def logloss(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def solver_b(rows):
    base = [r for r in rows if r["mpg"] >= MIN_MPG and r["xptsm_r"] is not None]
    out = {"features": list(FEATURES), "directions": {}}
    for fit, chk in ((SEASONS[0], SEASONS[1]), (SEASONS[1], SEASONS[0])):
        fr = sorted([r for r in base if r["season"] == fit and r["actual"] != r["line"]], key=lambda r: r["date"])
        X, mu, sd = design(fr)
        y = np.array([r["actual"] > r["line"] for r in fr], float)
        folds = np.array_split(np.arange(len(fr)), 5)            # contiguous date blocks
        cv = {}
        for lam in LAMBDAS:
            ll = []
            for f in folds:
                tr = np.setdiff1d(np.arange(len(fr)), f)
                ll.append(logloss(1 / (1 + np.exp(-X[f] @ logistic(X[tr], y[tr], lam))), y[f]))
            cv[lam] = float(np.mean(ll))
        lam = min(cv, key=cv.get)
        w = logistic(X, y, lam)
        cr = [r for r in base if r["season"] == chk]
        Xc, _m, _s = design(cr, mu, sd)
        p = 1 / (1 + np.exp(-Xc @ w))
        np_ = np.array([r["actual"] != r["line"] for r in cr])
        yc = np.array([r["actual"] > r["line"] for r in cr], float)
        bets = [r for r, pp in zip(cr, p) if pp * r["over"] - 1 >= EV_AT]
        out["directions"][f"fit {fit} -> test {chk}"] = {
            "lambda": lam, "coefficients (per SD)": {f: round(float(c), 4) for f, c in zip(("intercept",) + FEATURES, w)},
            "test_logloss": {"model": round(logloss(p[np_], yc[np_]), 5),
                             "book": round(logloss(np.array([r["q"] for r in cr])[np_], yc[np_]), 5)},
            "test_bets": summ(bets)}
    d = list(out["directions"].values())
    out["passes"] = all(x["test_bets"].get("n", 0) >= MIN_PICK and x["test_bets"]["roi"] > 0
                        and x["test_logloss"]["model"] < x["test_logloss"]["book"] for x in d)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamelogs", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--odds", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = build(a.gamelogs, a.shots, a.odds)
    res = {"rows": len(rows), "solver_a_xpts_m": solver_a(rows), "solver_a_xpts (no matchup)": solver_a(rows, "xpts_r"),
           "solver_b": solver_b(rows)}
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
