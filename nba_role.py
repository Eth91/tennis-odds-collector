#!/usr/bin/env python3
"""ROLE1's role model (NBA_ROLE1_PREREG.md): who gets the minutes and the shots when a rotation player is out.

Minutes and team volume come from THIS season's games before the date only; per-minute rates start from last season
and this season's games take over (K pseudo-minutes / attempts). Team volume (FGA, FTA, 3PA, REB, AST) is conserved,
so an absent player's share is redistributed across the active roster in proportion to minutes x rate.

    python3 nba_role.py --test-a GAMELOGS_DB [--json OUT]       # Test A: 2025-26 and 2024-25, minutes and volume
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict

import numpy as np

STATS = ("min", "fga", "fta", "fg3a", "reb", "ast", "pts", "fg3m")
RATE_STATS = ("fga", "fta", "fg3a", "reb", "ast")
K_RATE, K_TS, K_3P = 150.0, 60.0, 40.0
HALF_LIFE, X_MIN, X_GAMES, SAME_W, CAP, ROSTER_MIN = 3.0, 17.0, 3, 3.0, 40.0, 240.0
PREV = {"2025-26": "2024-25", "2024-25": "2023-24", "2023-24": "2022-23", "2026-27": "2025-26"}
LAST_N = 5                                               # amendment 1: the simplified minutes base


def group(pos):
    return (pos or "")[:1] or None


def ewma(xs):
    """Recency-weighted mean (half-life HALF_LIFE games); xs oldest first."""
    if not xs:
        return None
    w = [0.5 ** ((len(xs) - 1 - i) / HALF_LIFE) for i in range(len(xs))]
    return sum(a * b for a, b in zip(w, xs)) / sum(w)


class Priors:
    """Last season's per-minute rates, points per true-shooting attempt and 3P% per player; league means by group."""

    def __init__(self, rows, groups):
        tot = defaultdict(lambda: defaultdict(float))
        for r in rows:
            t = tot[r["pid"]]
            for s in STATS:
                t[s] += r[s] or 0
        self.player, gsum = {}, defaultdict(lambda: defaultdict(float))
        for pid, t in tot.items():
            g = groups.get(pid)
            for s in STATS:
                gsum[g][s] += t[s]
            if t["min"] >= 100:
                self.player[pid] = self._of(t)
        self.league = {g: self._of(t) for g, t in gsum.items() if t["min"] > 0}

    @staticmethod
    def _of(t):
        tsa = t["fga"] + 0.44 * t["fta"]
        return {**{s: t[s] / t["min"] for s in RATE_STATS}, "eff": t["pts"] / tsa if tsa else 1.0,
                "p3": t["fg3m"] / t["fg3a"] if t["fg3a"] else 0.33}

    def of(self, pid, g):
        return self.player.get(pid) or self.league.get(g) or next(iter(self.league.values()))


class Season:
    """This season's team games in date order: team -> [(date, gid, {pid: row})]."""

    def __init__(self, rows):
        by = defaultdict(dict)
        for r in rows:
            by[(r["team"], r["date"], r["gid"])][r["pid"]] = r
        self.games = defaultdict(list)
        for (team, d, g), box in by.items():
            self.games[team].append((d, g, box))
        for v in self.games.values():
            v.sort(key=lambda x: (x[0], x[1]))

    def before(self, team, date):
        return [x for x in self.games.get(team, ()) if x[0] < date]

    def absences(self, team, date, out):
        """{X: absence game n} for rotation players (>= 17 min over >= 3 games this season for the team) in `out`."""
        prior = self.before(team, date)
        res = {}
        for x in out:
            mins = [b[x]["min"] for _d, _g, b in prior if x in b and b[x]["min"]]
            if len(mins) < X_GAMES or sum(mins) / len(mins) < X_MIN:
                continue
            n = 1
            for _d, _g, b in reversed(prior):
                if x in b and b[x]["min"]:
                    break
                n += 1
            res[x] = n
        return res

    def roster(self, team, date):
        """Players who played for the team in any of its last 3 games."""
        return {p for _d, _g, b in self.before(team, date)[-3:] for p, r in b.items() if r["min"]}


def project(season, priors, groups, team, date, active, absent, mode="v2"):
    """{pid: {stat: projection}} for the active roster, with `absent` (rotation players out tonight) redistributed.
    mode "v1": the registered model (base over games X played + empirical bump); "v2" (amendment 1): base = last 5
    games, bump = X's minutes x the share of those 5 games X played."""
    prior = season.before(team, date)
    if not prior or not active:
        return {}
    with_g = [b for _d, _g, b in prior if all(x in b and b[x]["min"] for x in absent)]
    without_g = [b for _d, _g, b in prior if absent and not any(x in b and b[x]["min"] for x in absent)]
    base, emp = {}, {}
    for p in active:
        wm = [b[p]["min"] for b in with_g if p in b and b[p]["min"]]
        allm = [b[p]["min"] for _d, _g, b in prior if p in b and b[p]["min"]]
        base[p] = ewma(wm if len(wm) >= 2 else allm) or 0.0
        wo = [b[p]["min"] for b in without_g if p in b and b[p]["min"]]
        emp[p] = (sum(wo) / len(wo) - base[p], len(wo)) if wo else (0.0, 0)
    x_min = {x: ewma([b[x]["min"] for _d, _g, b in prior if x in b and b[x]["min"]]) or 0.0 for x in absent}
    share = {(p, x): 1.0 for p in active for x in absent}
    if mode == "v2":
        for p in active:
            last = [b for _d, _g, b in prior if p in b and b[p]["min"]][-LAST_N:]
            base[p] = sum(b[p]["min"] for b in last) / len(last) if last else 0.0
            for x in absent:
                share[(p, x)] = sum(1 for b in last if x in b and b[x]["min"]) / len(last) if last else 1.0
    bump = defaultdict(float)
    for x, mx in x_min.items():
        w = {p: base[p] * (SAME_W if groups.get(p) and groups.get(p) == groups.get(x) else 1.0) for p in active}
        tw = sum(w.values())
        for p in active:
            bump[p] += (mx * w[p] / tw if tw else 0.0) * share[(p, x)]
    mins = {}
    for p in active:
        if mode == "v2":
            mins[p] = min(CAP, max(0.0, base[p] + bump[p]))
            continue
        d, n = emp[p]
        a = n / (n + 2.0)
        mins[p] = min(CAP, max(0.0, base[p] + a * d + (1 - a) * bump[p]))
    tot = sum(mins.values())
    if tot > 0:
        mins = {p: m * ROSTER_MIN / tot for p, m in mins.items()}
    # this season's sums per player (all games before the date) for the blended rates
    seas = defaultdict(lambda: defaultdict(float))
    for _d, _g, b in prior:
        for p, r in b.items():
            for s in STATS:
                seas[p][s] += r[s] or 0
    ref = with_g if len(with_g) >= 2 else [b for _d, _g, b in prior]
    team_tot = {s: sum(sum(r[s] or 0 for r in b.values()) for b in ref) / len(ref) for s in RATE_STATS}
    raw = {s: {} for s in RATE_STATS}
    rates = {}
    for p in active:
        pr, t = priors.of(p, groups.get(p)), seas[p]
        rates[p] = {s: (t[s] + pr[s] * K_RATE) / (t["min"] + K_RATE) for s in RATE_STATS}
        rates[p]["eff"] = (t["pts"] + pr["eff"] * K_TS) / (t["fga"] + 0.44 * t["fta"] + K_TS)
        rates[p]["p3"] = (t["fg3m"] + pr["p3"] * K_3P) / (t["fg3a"] + K_3P)
        for s in RATE_STATS:
            raw[s][p] = mins[p] * rates[p][s]
    out = {}
    scale = {s: (team_tot[s] / sum(raw[s].values())) if sum(raw[s].values()) > 0 else 1.0 for s in RATE_STATS}
    for p in active:
        v = {"min": mins[p], **{s: raw[s][p] * scale[s] for s in RATE_STATS}}
        v["pts"] = (v["fga"] + 0.44 * v["fta"]) * rates[p]["eff"]
        v["fg3m"] = v["fg3a"] * rates[p]["p3"]
        v["base_min"] = base[p]
        out[p] = v
    return out


def load(gamelogs_db):
    import sqlite3
    c = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    groups = {pid: group(pos) for pid, pos in c.execute("SELECT player_id, position FROM positions")}
    rows = defaultdict(list)
    for s, g, d, tm, pid, mn, fga, fta, fg3a, fg3m, reb, ast, pts in c.execute(
            "SELECT season, game_id, date, team, player_id, min, fga, fta, fg3a, fg3m, reb, ast, pts FROM logs_full"):
        rows[s].append({"gid": g, "date": d, "team": tm, "pid": pid, "min": mn or 0.0, "fga": fga, "fta": fta, "fg3a": fg3a,
                        "fg3m": fg3m, "reb": reb, "ast": ast, "pts": pts})
    return rows, groups


def test_a(gamelogs_db, seasons=("2025-26", "2024-25"), mode="v1"):
    rows, groups = load(gamelogs_db)
    res, disp = {"mode": mode}, {}
    for s in seasons:
        season, priors = Season(rows[s]), Priors(rows[PREV[s]], groups)
        recs = []
        for team, games in season.games.items():
            for i, (d, g, box) in enumerate(games):
                if i < X_GAMES:
                    continue
                played = {p for p, r in box.items() if r["min"]}
                last3 = season.roster(team, d)
                spots = season.absences(team, d, last3 - played)
                if not spots or min(spots.values()) > 3:
                    continue
                active = last3 & played                          # the prereg's roster: in the last 3 games, and not out tonight
                proj = project(season, priors, groups, team, d, active, set(spots), mode=mode)
                prior = season.before(team, d)
                for p in active:
                    hist = [b[p] for _d, _g, b in prior if p in b and b[p]["min"]]
                    if not hist or p not in proj:
                        continue
                    act = box[p]
                    rec = {"date": d, "n": min(spots.values()), "actual": {k: act[k] or 0 for k in STATS},
                           "model": {k: proj[p][k] for k in STATS}, "base_min": proj[p]["base_min"],
                           "season_avg": {k: sum(h[k] or 0 for h in hist) / len(hist) for k in STATS},
                           "last5": {k: sum(h[k] or 0 for h in hist[-5:]) / len(hist[-5:]) for k in STATS}}
                    recs.append(rec)
        out = {"player_games": len(recs), "spots_by_n": {n: sum(r["n"] == n for r in recs) for n in (1, 2, 3)}, "mae": {}, "bias": {}}
        for k in STATS:
            for m in ("model", "season_avg", "last5"):
                out["mae"].setdefault(k, {})[m] = round(float(np.mean([abs(r[m][k] - r["actual"][k]) for r in recs])), 3)
                out["bias"].setdefault(k, {})[m] = round(float(np.mean([r[m][k] - r["actual"][k] for r in recs])), 3)
        pc = [r["model"]["min"] - r["base_min"] for r in recs]
        ac = [r["actual"]["min"] - r["base_min"] for r in recs]
        out["minutes_change_corr"] = round(float(np.corrcoef(pc, ac)[0, 1]), 3)
        out["passes"] = all(out["mae"][k]["model"] < min(out["mae"][k]["season_avg"], out["mae"][k]["last5"]) for k in ("min", "fga"))
        res[s] = out
        if s == "2025-26":                                         # negative-binomial dispersion per market (method of moments)
            for k, mk in (("pts", "points"), ("reb", "rebounds"), ("ast", "assists"), ("fg3m", "threes")):
                mu = np.array([max(0.1, r["model"][k]) for r in recs])
                y = np.array([r["actual"][k] for r in recs])
                inv_r = max(1e-6, float(np.sum((y - mu) ** 2 - mu) / np.sum(mu ** 2)))
                disp[mk] = round(1.0 / inv_r, 3)
    res["nb_r"] = disp
    res["verdict"] = "PASS" if all(res[s]["passes"] for s in seasons) else "FAIL"
    return res


# ── pricing ─────────────────────────────────────────────────────────────────────────────────────────────────────
NB_R = {"points": 7.211, "rebounds": 11.747, "assists": 13.092, "threes": 10.157}   # amendment 1: v2 on 2025-26
MARKET_STAT = {"points": "pts", "rebounds": "reb", "assists": "ast", "threes": "fg3m"}


def p_over(mu, r, line):
    """P(X > line) for a negative binomial with mean mu and size r (no push at a .5 line; at a whole line, P(X > line))."""
    mu = max(mu, 1e-6)
    q = r / (r + mu)
    cdf, k = 0.0, 0
    while k <= math.floor(line):
        cdf += math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1) + r * math.log(q) + k * math.log(1 - q))
        k += 1
    return max(0.0, 1.0 - cdf)


def p_side(mu, market, line, side):
    """P(side wins | no push), from the market's negative binomial."""
    r = NB_R[market]
    po = p_over(mu, r, line)
    if line == math.floor(line):                         # a whole line can push
        pu = 1.0 - p_over(mu, r, line - 1)
        tot = po + pu
        po, pu = (po / tot, pu / tot) if tot else (0.5, 0.5)
        return po if side == "over" else pu
    return po if side == "over" else 1.0 - po


def test_b(gamelogs_db, odds_db, seasons=("2023-24", "2024-25"), ev_at=0.05):
    """Information only: spots with n = 2-3 at the archive's tip line (FanDuel/DraftKings main), v2 model."""
    import sqlite3
    import nba_margin_refit as MR
    rows, groups = load(gamelogs_db)
    c = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in c.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    mk_of = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists", "player_threes": "threes"}
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, pl, m, line, side, price, book in o.execute(
            "SELECT game_date, player, market, line, side, price, book FROM props WHERE market IN ('player_points', "
            "'player_rebounds', 'player_assists', 'player_threes') AND price IS NOT NULL AND line IS NOT NULL"):
        if book in ("fanduel", "draftkings"):
            raw[(d, name2pid.get(MR.norm(pl)), mk_of[m])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    bets = []
    for s in seasons:
        season, priors = Season(rows[s]), Priors(rows[PREV[s]], groups)
        for team, games in season.games.items():
            for i, (d, g, box) in enumerate(games):
                if i < X_GAMES:
                    continue
                played = {p for p, r in box.items() if r["min"]}
                last3 = season.roster(team, d)
                spots = season.absences(team, d, last3 - played)
                spots = {x: n for x, n in spots.items() if n in (2, 3)}
                if not spots:
                    continue
                active = last3 & played
                proj = project(season, priors, groups, team, d, active, set(spots), mode="v2")
                for p in active:
                    for mk, st in MARKET_STAT.items():
                        lb = raw.get((d, p, mk))
                        if not lb or p not in proj:
                            continue
                        best = None                            # FanDuel/DraftKings main: two-sided, over nearest even money
                        for line, bk in lb.items():
                            two = [(b, v) for b, v in bk.items() if v[0] and v[1]]
                            if two:
                                gap = min(abs(v[0] - 2.0) for _b, v in two)
                                if best is None or gap < best[0]:
                                    best = (gap, line, max(v[0] for _b, v in two), max(v[1] for _b, v in two))
                        if not best:
                            continue
                        _g, line, ov, un = best
                        a = box[p][st] or 0
                        for side, price in (("over", ov), ("under", un)):
                            ev = p_side(proj[p][st], mk, line, side) * price - 1
                            u = 0.0 if a == line else ((price - 1) if (a > line) == (side == "over") else -1.0)
                            bets.append({"season": s, "date": d, "market": mk, "side": side, "ev": ev, "u": u})
    out = {}
    for s in seasons:
        b = [x for x in bets if x["season"] == s]
        out[s] = {lab: (lambda k: {"n": len(k), "roi": round(float(np.mean([x["u"] for x in k])), 4) if k else None})(
            [x for x in b if lo <= x["ev"] < hi]) for lab, lo, hi in (("ev<0", -9, 0), ("0-5%", 0, 0.05), ("5-10%", 0.05, 0.10), ("10%+", 0.10, 9))}
        k = [x for x in b if x["ev"] >= ev_at]
        out[s]["flagged"] = {"n": len(k), "roi": round(float(np.mean([x["u"] for x in k])), 4) if k else None,
                             "by_side": {sd: round(float(np.mean([x["u"] for x in k if x["side"] == sd])), 4)
                                         for sd in ("over", "under") if any(x["side"] == sd for x in k)},
                             "by_market": {m: (sum(1 for x in k if x["market"] == m), round(float(np.mean([x["u"] for x in k if x["market"] == m])), 4))
                                           for m in MARKET_STAT if any(x["market"] == m for x in k)}}
    return out


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def calibrated(p_model, q_book, beta):
    """Amendment 2: the book's no-vig probability moved toward the model's by the share beta of their disagreement."""
    return 1.0 / (1.0 + math.exp(-(logit(q_book) + beta * (logit(p_model) - logit(q_book)))))


def tip_props(gamelogs_db, odds_db, seasons):
    """One row per prop in absence games 2-3 at the archive's tip line: the book's no-vig over (FanDuel's pair, else
    DraftKings'), the model's P(over), the best over/under prices and the result."""
    import sqlite3
    import nba_margin_refit as MR
    rows, groups = load(gamelogs_db)
    c = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in c.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    mk_of = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists", "player_threes": "threes"}
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, pl, m, line, side, price, book in o.execute(
            "SELECT game_date, player, market, line, side, price, book FROM props WHERE market IN ('player_points', "
            "'player_rebounds', 'player_assists', 'player_threes') AND price IS NOT NULL AND line IS NOT NULL"):
        if book in ("fanduel", "draftkings"):
            raw[(d, name2pid.get(MR.norm(pl)), mk_of[m])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    out = []
    for s in seasons:
        season, priors = Season(rows[s]), Priors(rows[PREV[s]], groups)
        for team, games in season.games.items():
            for i, (d, g, box) in enumerate(games):
                if i < X_GAMES:
                    continue
                played = {p for p, r in box.items() if r["min"]}
                last3 = season.roster(team, d)
                spots = {x: n for x, n in season.absences(team, d, last3 - played).items() if n in (2, 3)}
                if not spots:
                    continue
                active = last3 & played
                proj = project(season, priors, groups, team, d, active, set(spots), mode="v2")
                for p in active:
                    for mk, st in MARKET_STAT.items():
                        lb = raw.get((d, p, mk))
                        if not lb or p not in proj:
                            continue
                        best = None
                        for line, bk in lb.items():
                            two = {b: v for b, v in bk.items() if v[0] and v[1]}
                            if two:
                                gap = min(abs(v[0] - 2.0) for v in two.values())
                                if best is None or gap < best[0]:
                                    best = (gap, line, two)
                        if not best:
                            continue
                        _g, line, two = best
                        pair = two.get("fanduel") or two.get("draftkings")
                        a = box[p][st] or 0
                        out.append({"season": s, "date": d, "market": mk, "line": line, "actual": a,
                                    "q_book": (1 / pair[0]) / (1 / pair[0] + 1 / pair[1]),
                                    "p_model": p_side(proj[p][st], mk, line, "over"),
                                    "over": max(v[0] for v in two.values()), "under": max(v[1] for v in two.values())})
    return out


def calibrate(gamelogs_db, odds_db):
    """Amendment 2: beta by maximum likelihood on 2023-24; checked on 2024-25 (information)."""
    props = tip_props(gamelogs_db, odds_db, ("2023-24", "2024-25"))
    fit = [r for r in props if r["season"] == "2023-24" and r["actual"] != r["line"]]
    ll = lambda b, rs: -float(np.mean([math.log(max(1e-9, calibrated(r["p_model"], r["q_book"], b) if r["actual"] > r["line"]
                                                     else 1 - calibrated(r["p_model"], r["q_book"], b))) for r in rs]))
    grid = [i / 100 for i in range(0, 151)]
    beta = min(grid, key=lambda b: ll(b, fit))
    chk = [r for r in props if r["season"] == "2024-25" and r["actual"] != r["line"]]
    bets = []
    for r in [x for x in props if x["season"] == "2024-25"]:
        po = calibrated(r["p_model"], r["q_book"], beta)
        for side, pr, price in (("over", po, r["over"]), ("under", 1 - po, r["under"])):
            if pr * price - 1 >= 0.05:
                u = 0.0 if r["actual"] == r["line"] else ((price - 1) if (r["actual"] > r["line"]) == (side == "over") else -1.0)
                bets.append({"side": side, "market": r["market"], "u": u})
    return {"beta": beta, "fit_props": len(fit), "logloss_2023_24": {"book": round(ll(0.0, fit), 5), "calibrated": round(ll(beta, fit), 5),
                                                                       "model": round(ll(1.0, fit), 5)},
            "check_2024_25": {"props": len(chk), "logloss_book": round(ll(0.0, chk), 5), "logloss_calibrated": round(ll(beta, chk), 5),
                              "logloss_model": round(ll(1.0, chk), 5), "flags_ev5": len(bets),
                              "flag_rate": round(len(bets) / max(1, 2 * len([x for x in props if x["season"] == "2024-25"])), 4),
                              "roi": round(float(np.mean([b["u"] for b in bets])), 4) if bets else None,
                              "by_side": {sd: (sum(b["side"] == sd for b in bets), round(float(np.mean([b["u"] for b in bets if b["side"] == sd])), 4))
                                          for sd in ("over", "under") if any(b["side"] == sd for b in bets)}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-a")
    ap.add_argument("--seasons", default="2025-26,2024-25")
    ap.add_argument("--mode", default="v1", choices=("v1", "v2"))
    ap.add_argument("--test-b", nargs=2, metavar=("GAMELOGS_DB", "ODDS_DB"))
    ap.add_argument("--calibrate", nargs=2, metavar=("GAMELOGS_DB", "ODDS_DB"))
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.calibrate:
        res = calibrate(*a.calibrate)
        print(json.dumps(res, indent=1))
        if a.json:
            open(a.json, "w").write(json.dumps(res, indent=1))
    if a.test_b:
        res = test_b(*a.test_b)
        print(json.dumps(res, indent=1))
        if a.json:
            open(a.json, "w").write(json.dumps(res, indent=1))
    if a.test_a:
        res = test_a(a.test_a, tuple(a.seasons.split(",")), a.mode)
        print(json.dumps(res, indent=1))
        if a.json:
            open(a.json, "w").write(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
