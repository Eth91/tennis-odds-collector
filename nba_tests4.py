#!/usr/bin/env python3
"""Four modeling tests (NBA_TESTS4_PREREG.md): T1 usage vs efficiency, T2 where the book is wrong, T3 low lines, T4 who
takes his shots. Fit on 2023-24; tip-line tests on 2024-25; projection errors also on 2025-26.

    python3 nba_tests4.py [--json OUT]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_boost as BOOST
import nba_lowend as LO
import nba_margin_refit as MR
import nba_minutes as M

SEASONS = ("2023-24", "2024-25", "2025-26")
BET_SEASONS = ("2023-24", "2024-25")
MARKETS = tuple(BOOST.PARTS)
EV_AT, PROJ_AT, K_SHARE = 0.05, 1.15, 5.0


def tip_lines(gamelogs_db=M.GAMELOGS, odds_db=M.ODDS):
    """{(date, pid, market): (line, best over, best under, no-vig over)} at the FanDuel/DraftKings main rung."""
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    q = ("SELECT game_date, player, market, line, side, price, book FROM props WHERE market IN (%s) AND price IS NOT NULL "
         "AND line IS NOT NULL AND book IN ('fanduel', 'draftkings')" % ",".join("?" * len(BOOST.ODDS_MARKETS)))
    for d, pl, m, line, side, price, book in o.execute(q, tuple(BOOST.ODDS_MARKETS)):
        pid = name2pid.get(MR.norm(pl))
        if pid is not None:
            raw[(d, pid, BOOST.ODDS_MARKETS[m])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    out = {}
    for k, lb in raw.items():
        best = None
        for line, bk in lb.items():
            two = {b: v for b, v in bk.items() if v[0] and v[1]}
            if two:
                gap = min(abs(v[0] - 2.0) for v in two.values())
                if best is None or gap < best[0] - 1e-9:
                    best = (gap, line, two)
        if best:
            _g, line, two = best
            pair = two.get("fanduel") or two.get("draftkings")
            out[k] = (line, max(v[0] for v in two.values()), max(v[1] for v in two.values()),
                      (1 / pair[0]) / (1 / pair[0] + 1 / pair[1]))
    return out


def player_games(season):
    """Every player who played, with ROLE1 v3 minutes x his rates, tonight's box and the night's context."""
    bd, s, out = season.bd, season.s, []
    for team, games in sorted(bd.games.items()):
        for d, gid, gs, box in games:
            if gs != s:
                continue
            played = {p for p, x in box.items() if x["min"]}
            usual = bd.usual_five(team, d)
            starters = usual or bd.starters(team, d)
            out_all = (bd.on_team_tonight(team, d) - played) & (bd.roster(team, d) | starters)
            xs = {x: n for x in starters & out_all if (n := bd.absence_n(x, team, d)) <= M.SPOT_MAX}
            five = season.five.get((d, team), frozenset())
            pg = {p: bd.per_game(p, team, d) for p in bd.on_team_tonight(team, d)}
            top_fga = max((p for p in pg if pg[p]), key=lambda p: pg[p]["fga"], default=None)
            v3 = season.v3(team, d, out_all)
            for p in sorted(played):
                rt = BOOST.rates(bd, p, d)
                if p not in v3 or not rt:
                    continue
                out.append({"season": s, "date": d, "team": team, "gid": gid, "pid": p, "min": v3[p]["min"], "rt": rt,
                            "box": box[p], "xs": xs, "x_top": bool(xs) and top_fga in xs, "n_out": len(set(out_all) & starters),
                            "new_starter": bool(usual) and p in five and p not in usual, "team_box": box})
    return out


def context(season, r):
    """T2's per-row inputs that do not depend on the market."""
    mine = season.bd.his(r["pid"], r["date"])
    last10 = [x["min"] for x in mine[-10:]]
    this = [x for x in mine if x["season"] == season.s]
    gap = (dt.date.fromisoformat(r["date"]) - dt.date.fromisoformat(mine[-1]["date"])).days if mine else 4
    r["ctx"] = {"min_change": r["min"] - (np.mean(last10) if last10 else r["min"]),
                "season_mpg": np.mean([x["min"] for x in this]) if this else np.nan,
                "rest": min(4, gap), "b2b": float(gap <= 1),
                "game_index": sum(1 for _d, _g, ss, _b in season.bd.before(r["team"], r["date"]) if ss == season.s),
                "x_out": float(bool(r["xs"])), "min_absence": min(r["xs"].values()) if r["xs"] else 9,
                "n_out": r["n_out"], "new_starter": float(r["new_starter"])}
    r["recent"] = {s_: (np.mean([x[s_] or 0 for x in mine[-5:]]) / max(1e-9, np.mean([x[s_] or 0 for x in this])) if this and mine else np.nan)
                   for s_ in ("pts", "reb", "ast", "fg3m")}


def proj(r, mk):
    return r["min"] * sum(r["rt"][s] for s in BOOST.PARTS[mk])


def grade(stat, line, price):
    return (price - 1) if stat > line else (0.0 if stat == line else -1.0)


def summ(us):
    if not us:
        return {"n": 0}
    rng = np.random.default_rng(7)
    a = np.array(us)
    bs = np.sort([rng.choice(a, len(a)).mean() for _ in range(2000)])
    return {"n": len(a), "roi": round(float(a.mean()), 4), "roi90": [round(float(bs[100]), 4), round(float(bs[1900]), 4)]}


# ── T1: usage vs efficiency ───────────────────────────────────────────────────────────────────────────────────────
def ts(pts, fga, fta):
    tsa = (fga or 0) + 0.44 * (fta or 0)
    return (pts / (2 * tsa), tsa) if tsa > 0 else (None, 0.0)


def t1(seasons, rows, lines):
    def base_ts(r):
        mine = seasons[r["season"]].bd.his(r["pid"], r["date"])
        return ts(sum(x["pts"] or 0 for x in mine), sum(x["fga"] or 0 for x in mine), sum(x["fta"] or 0 for x in mine))[0]
    cell = lambda r: (("new starter" if r["new_starter"] else "teammate") + (", X top FGA" if r["x_top"] else ", X not top")) if r["xs"] else "normal"
    deltas = {}
    for s in SEASONS:
        acc = defaultdict(lambda: [0.0, 0.0])
        for r in rows[s]:
            t, tsa = ts(r["box"]["pts"] or 0, r["box"]["fga"], r["box"]["fta"])
            b = r.setdefault("base_ts", base_ts(r))
            if t is None or b is None:
                continue
            acc[cell(r)][0] += (t - b) * tsa
            acc[cell(r)][1] += tsa
        normal = acc["normal"][0] / acc["normal"][1]
        deltas[s] = {c: {"delta": round(v[0] / v[1] - normal, 4), "tsa": round(v[1])} for c, v in acc.items() if c != "normal"}
        deltas[s]["normal (vs own baseline)"] = round(normal, 4)
    d0 = {c: v["delta"] for c, v in deltas["2023-24"].items() if isinstance(v, dict)}
    big = sorted((c for c in d0), key=lambda c: -deltas["2023-24"][c]["tsa"])[:2]
    same_sign = all(np.sign(deltas["2024-25"][c]["delta"]) == np.sign(d0[c]) for c in big)
    adj = lambda r: proj(r, "points") * (1 + d0.get(cell(r), 0.0) / r["base_ts"]) if r.get("base_ts") else proj(r, "points")
    mae = {}
    for s in ("2024-25", "2025-26"):
        rs = [r for r in rows[s] if r["xs"] and r.get("base_ts")]
        mae[s] = {"unadjusted": round(float(np.mean([abs((r["box"]["pts"] or 0) - proj(r, "points")) for r in rs])), 3),
                  "adjusted": round(float(np.mean([abs((r["box"]["pts"] or 0) - adj(r)) for r in rs])), 3), "n": len(rs)}
    bets = {}
    for s in BET_SEASONS:
        for name, f in (("unadjusted", lambda r: proj(r, "points")), ("adjusted", adj)):
            us = []
            for r in rows[s]:
                ln = lines.get((r["date"], r["pid"], "points"))
                if r["xs"] and ln and f(r) >= PROJ_AT * ln[0] and ln[1] >= BOOST.PRICE_MIN - 1e-9:
                    us.append(grade(r["box"]["pts"] or 0, ln[0], ln[1]))
            bets[f"{s} {name}"] = summ(us)
    ok = same_sign and all(mae[s]["adjusted"] < mae[s]["unadjusted"] for s in mae)
    return {"deltas": deltas, "largest cells": big, "same sign 2024-25": bool(same_sign), "points MAE": mae, "bets": bets, "pass": bool(ok)}


# ── T2: where is the book wrong ──────────────────────────────────────────────────────────────────────────────────
def t2(rows, lines):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    data = {s: [] for s in BET_SEASONS}
    for s in BET_SEASONS:
        for r in rows[s]:
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
                x = [math.log(q / (1 - q)), line, proj(r, mk) / line, c["min_change"], c["season_mpg"],
                     float(np.nanmean(rec)) if rec else np.nan, c["n_out"], c["new_starter"], c["x_out"], c["min_absence"],
                     c["rest"], c["b2b"], c["game_index"]] + [float(mk == m) for m in MARKETS]
                data[s].append((x, int(act > line), over, under, q))
    X = {s: np.array([d[0] for d in data[s]], dtype=float) for s in BET_SEASONS}
    y = {s: np.array([d[1] for d in data[s]]) for s in BET_SEASONS}
    med = np.nanmedian(X["2023-24"], axis=0)
    Xf = {s: np.where(np.isnan(X[s]), med, X[s]) for s in BET_SEASONS}  # the logistic model needs no gaps
    sc = StandardScaler().fit(Xf["2023-24"])
    models = {"logistic": (LogisticRegression(C=1.0, max_iter=2000).fit(sc.transform(Xf["2023-24"]), y["2023-24"]), lambda s: sc.transform(Xf[s])),
              "boosted": (HistGradientBoostingClassifier(random_state=0).fit(X["2023-24"], y["2023-24"]), lambda s: X[s])}
    ll = lambda p, yy: float(-np.mean(yy * np.log(np.clip(p, 1e-6, 1 - 1e-6)) + (1 - yy) * np.log(np.clip(1 - p, 1e-6, 1 - 1e-6))))
    out = {}
    for s in BET_SEASONS:
        q = np.array([d[4] for d in data[s]])
        out[s] = {"n": len(q), "book log loss": round(ll(q, y[s]), 5)}
        for name, (m, xs) in models.items():
            p = m.predict_proba(xs(s))[:, 1]
            us = []
            for pi, yi, (_x, _y, over, under, _q) in zip(p, y[s], data[s]):
                if pi * over - 1 >= EV_AT:
                    us.append(over - 1 if yi else -1.0)
                elif (1 - pi) * under - 1 >= EV_AT:
                    us.append(under - 1 if not yi else -1.0)
            out[s][name] = {"log loss": round(ll(p, y[s]), 5), "bets": summ(us)}
    ok = {name: out["2024-25"][name]["log loss"] < out["2024-25"]["book log loss"] and out["2024-25"][name]["bets"].get("n", 0) >= 100
          and out["2024-25"][name]["bets"].get("roi", -1) > 0 for name in models}
    out["pass"] = ok
    return out


# ── T3: low lines ────────────────────────────────────────────────────────────────────────────────────────────────
def nb_pmf_cdf(k, mu, r):
    """P(X <= k) for a negative binomial with mean mu and dispersion r."""
    p = r / (r + mu)
    tot, term = 0.0, p ** r
    for i in range(int(k) + 1):
        tot += term
        term *= (i + r) / (i + 1) * (1 - p)
    return tot


def fit_r(pairs):
    best = None
    for r in np.exp(np.linspace(np.log(0.5), np.log(200), 80)):
        ll = 0.0
        for mu, x in pairs:
            mu = max(mu, 1e-3)
            ll += (math.lgamma(x + r) - math.lgamma(r) - math.lgamma(x + 1) + r * math.log(r / (r + mu)) + x * math.log(mu / (r + mu)))
        if best is None or ll > best[0]:
            best = (ll, r)
    return float(best[1])


def t3(seasons, rows, lines):
    mk3 = ("threes", "assists", "rebounds")
    rs = {mk: fit_r([(proj(r, mk), BOOST.stat_of(r["box"], mk)) for r in rows["2023-24"]]) for mk in mk3}
    out = {"r (2023-24)": {k: round(v, 2) for k, v in rs.items()}}
    ll = lambda p, yy: float(-np.mean(yy * np.log(np.clip(p, 1e-6, 1 - 1e-6)) + (1 - yy) * np.log(np.clip(1 - p, 1e-6, 1 - 1e-6))))
    for s in BET_SEASONS:
        nb, emp, book, ys, us_nb, us_emp = [], [], [], [], [], []
        by_mk = defaultdict(list)
        for r in rows[s]:
            for mk in mk3:
                ln = lines.get((r["date"], r["pid"], mk))
                if not ln or ln[0] not in (0.5, 1.5):
                    continue
                line, over, under, q = ln
                act = BOOST.stat_of(r["box"], mk)
                p = 1 - nb_pmf_cdf(math.floor(line), max(proj(r, mk), 1e-3), rs[mk])
                last = seasons[s].bd.his(r["pid"], r["date"])[-20:]
                pe = np.mean([BOOST.stat_of(x, mk) > line for x in last]) if len(last) >= 10 else np.nan
                nb.append(p); emp.append(pe); book.append(q); ys.append(int(act > line))
                for pp, us in ((p, us_nb), (pe, us_emp)):
                    if np.isnan(pp):
                        continue
                    if pp * over - 1 >= EV_AT:
                        us.append(over - 1 if act > line else -1.0)
                        if us is us_nb:
                            by_mk[mk].append(us[-1])
                    elif (1 - pp) * under - 1 >= EV_AT:
                        us.append(under - 1 if act <= line else -1.0)
                        if us is us_nb:
                            by_mk[mk].append(us[-1])
        y = np.array(ys)
        e = np.array(emp)
        ok_e = ~np.isnan(e)
        out[s] = {"n": len(y), "book log loss": round(ll(np.array(book), y), 5), "NB log loss": round(ll(np.array(nb), y), 5),
                  "last-20 log loss (where 10+ games)": round(ll(e[ok_e], y[ok_e]), 5), "NB bets": summ(us_nb),
                  "NB bets by market": {k: summ(v) for k, v in by_mk.items()}, "last-20 bets": summ(us_emp)}
    out["pass"] = all(out[s]["NB bets"].get("n", 0) >= 100 and out[s]["NB bets"].get("roi", -1) > 0 for s in BET_SEASONS) and \
        out["2024-25"]["NB log loss"] < out["2024-25"]["book log loss"]
    return out


# ── T4: who takes his shots ───────────────────────────────────────────────────────────────────────────────────────
def t4(seasons, rows, lines):
    out = {}
    for s in SEASONS:
        season = seasons[s]
        bd = season.bd
        err_s, err_b, flags = [], [], defaultdict(list)
        for r in rows[s]:
            if not r["xs"]:
                continue
            x = max(r["xs"], key=lambda q: (bd.per_game(q, r["team"], r["date"]) or {"fga": 0})["fga"])
            prior = bd.before(r["team"], r["date"])
            with_, without = [], []
            for d, _g, ss, b in prior:
                if r["pid"] not in b or not b[r["pid"]]["min"]:
                    continue
                tf = sum(v["fga"] or 0 for v in b.values())
                t3a = sum(v["fg3a"] or 0 for v in b.values())
                if not tf:
                    continue
                rec = ((b[r["pid"]]["fga"] or 0) / tf, (b[r["pid"]]["fg3a"] or 0) / t3a if t3a else 0.0)
                if x in b and b[x]["min"]:
                    with_.append(rec)
                elif bd.on_team_at(x, r["team"], d, r["date"]):
                    without.append(rec)
            if not with_:
                continue
            this = [b for d, _g, ss, b in prior if ss == s]
            use = this if len(this) >= 3 else [b for d, _g, ss, b in prior if ss != s]
            if not use:
                continue
            team_fga = np.mean([sum(v["fga"] or 0 for v in b.values()) for b in use])
            team_3pa = np.mean([sum(v["fg3a"] or 0 for v in b.values()) for b in use])
            w = len(without) / (len(without) + K_SHARE)
            sw = np.mean([a for a, _b in with_]), np.mean([b_ for _a, b_ in with_])
            so = (np.mean([a for a, _b in without]), np.mean([b_ for _a, b_ in without])) if without else sw
            fga_s = team_fga * (sw[0] + w * (so[0] - sw[0]))
            fg3a_s = team_3pa * (sw[1] + w * (so[1] - sw[1]))
            mine = bd.his(r["pid"], r["date"])
            f_tot = sum(q["fga"] or 0 for q in mine)
            a3 = sum(q["fg3a"] or 0 for q in mine)
            ppf = sum(q["pts"] or 0 for q in mine) / f_tot if f_tot else None
            p3 = sum(q["fg3m"] or 0 for q in mine) / a3 if a3 else 0.36
            act = r["box"]["fga"] or 0
            err_s.append(abs(act - fga_s))
            err_b.append(abs(act - r["min"] * r["rt"]["fga"]))
            if s in BET_SEASONS and ppf:
                for mk, pr in (("points", fga_s * ppf), ("threes", fg3a_s * p3)):
                    ln = lines.get((r["date"], r["pid"], mk))
                    if ln and pr >= PROJ_AT * ln[0] and ln[1] >= BOOST.PRICE_MIN - 1e-9:
                        flags[mk].append(grade(BOOST.stat_of(r["box"], mk), ln[0], ln[1]))
        out[s] = {"n": len(err_s), "FGA MAE share": round(float(np.mean(err_s)), 3), "FGA MAE baseline": round(float(np.mean(err_b)), 3)}
        if s in BET_SEASONS:
            out[s]["bets"] = {mk: summ(v) for mk, v in flags.items()}
            out[s]["bets all"] = summ([u for v in flags.values() for u in v])
    out["pass"] = all(out[s]["FGA MAE share"] < out[s]["FGA MAE baseline"] for s in ("2024-25", "2025-26")) and \
        out["2024-25"]["bets all"].get("n", 0) >= 100 and out["2024-25"]["bets all"].get("roi", -1) > 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    rows_db, pos, five = LO.load()
    lines = tip_lines()
    seasons, rows = {}, {}
    for s in SEASONS:
        seasons[s] = M.Season(s, rows_db, pos, five)
        rows[s] = player_games(seasons[s])
        for r in rows[s]:
            context(seasons[s], r)
    res = {"rows": {s: len(v) for s, v in rows.items()}}
    res["T1 usage vs efficiency"] = t1(seasons, rows, lines)
    res["T2 where is the book wrong"] = t2(rows, lines)
    res["T3 low lines"] = t3(seasons, rows, lines)
    res["T4 who takes his shots"] = t4(seasons, rows, lines)
    print(json.dumps(res, indent=1, default=str))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
