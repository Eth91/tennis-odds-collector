#!/usr/bin/env python3
"""NFL_MODEL_PREREG.md: an NFL projection model (team volume x his share x efficiency, with the game's spread and
total, the injury report and the opponent), fit on 2023 and tested on 2024 and 2025 against the plain average and the
book. Mac only.

    NFL_CACHE=.projdata/nfl_cache python3 nfl_model.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import nfl_common as C
import nfl_stats as S
import nfl_under as U

OUT = Path(__file__).resolve().parent / ".projdata" / "nfl_model_result.json"
FIT, TESTS = 2023, (2024, 2025)
K_LAST, MIN_GAMES, POOL_GAMES, SAME_POS = 4.0, 3, 4, 2.0
SHRINK = {"targets": 40.0, "carries": 60.0, "attempts": 150.0}
OPP_PULL, EV_AT = 0.5, 0.05
STATS = ("targets", "receptions", "receiving_yards", "carries", "rushing_yards", "attempts", "completions", "passing_yards")
VOLUME = ("targets", "attempts", "carries")
RATES = {"catch": ("receptions", "targets"), "ypt": ("receiving_yards", "targets"), "ypc": ("rushing_yards", "carries"),
         "comp": ("completions", "attempts"), "ypa": ("passing_yards", "attempts")}
POS = {"FB": "RB", "HB": "RB"}
rng = np.random.default_rng(9)


class Data:
    """Weekly rows, team-game totals, the schedule's lines and the injury report, keyed for "before (season, week)"."""

    def __init__(self):
        self.sched = {g["gid"]: g for g in C.schedule(None, 7 * 86400)}
        self.rows, self.team_tot = defaultdict(list), defaultdict(lambda: defaultdict(float))
        self.team_games = defaultdict(list)                  # team -> [(season, week, gid)]
        self.by_gid = defaultdict(dict)                      # gid -> {pid: row}
        for s in (2022, 2023, 2024, 2025):
            for r in S.weekly(s, 2026):
                gid = r.get("game_id") or ""
                g = self.sched.get(gid)
                team = C.team(r.get("team"))
                if not g or not team:
                    continue
                for k in STATS:
                    try:
                        r[k] = float(r.get(k) or 0)
                    except ValueError:
                        r[k] = 0.0
                r.update(_s=g["season"], _w=g["week"], _team=team, _opp=g["away"] if team == g["home"] else g["home"],
                         _pos=POS.get(r.get("position") or "", r.get("position") or ""))
                self.rows[r["player_id"]].append(r)
                self.by_gid[gid][r["player_id"]] = r
                for k in VOLUME:
                    self.team_tot[(gid, team)][k] += r[k]
        for (gid, team) in self.team_tot:
            g = self.sched[gid]
            self.team_games[team].append((g["season"], g["week"], gid))
        for v in self.team_games.values():
            v.sort()
        for v in self.rows.values():
            v.sort(key=lambda r: (r["_s"], r["_w"]))
        self.out = defaultdict(set)                          # (season, week, team) -> listed Out or Doubtful
        for s in (2023, 2024, 2025):
            try:
                for r in C.iter_rows(f"injuries/injuries_{s}.csv", 7 * 86400):
                    if (r.get("report_status") or "").strip() in ("Out", "Doubtful"):
                        self.out[(int(r["season"]), int(r["week"]), C.team(r["team"]))].add(r["gsis_id"])
            except Exception as e:                           # a season without a report file: nobody is listed
                print(f"injuries {s}: {e}")
        self.cache = {}

    def before(self, rows, season, week):
        this = [r for r in rows if r["_s"] == season and r["_w"] < week]
        last = [r for r in rows if r["_s"] == season - 1]
        return this, last


def blend(this_num, this_den, last_num, last_den, n_last):
    """(num, den) with last season's games counted as K_LAST games."""
    f = K_LAST / n_last if n_last else 0.0
    return this_num + f * last_num, this_den + f * last_den


def team_avg(D, team, season, week, k):
    this = [gid for s, w, gid in D.team_games[team] if s == season and w < week]
    last = [gid for s, w, gid in D.team_games[team] if s == season - 1]
    if not this and not last:
        return None
    num, den = blend(sum(D.team_tot[(g, team)][k] for g in this), len(this),
                     sum(D.team_tot[(g, team)][k] for g in last), len(last), len(last))
    return num / den if den else None


def team_features(D, team, gid):
    g = D.sched[gid]
    spread = (g["spread"] or 0.0) * (1 if team == g["home"] else -1)
    return {k: (team_avg(D, team, g["season"], g["week"], k), spread, g["total"] or 44.0) for k in VOLUME}


def share(D, pid, season, week, k):
    """His share of his team's k over his games (this season before the week, last season as K_LAST games), with the
    games counted; None without games."""
    key = ("share", pid, season, week, k)
    if key not in D.cache:
        this, last = D.before(D.rows[pid], season, week)
        tot = lambda rs: (sum(r[k] for r in rs), sum(D.team_tot[(r["game_id"], r["_team"])][k] for r in rs))
        (hn, hd), (ln_, ld) = tot(this), tot(last)
        num, den = blend(hn, hd, ln_, ld, len(last))
        D.cache[key] = (num / den if den else 0.0, len(this) + len(last))
    return D.cache[key]


def rate(D, pid, season, week, name, prior):
    num_k, den_k = RATES[name]
    this, last = D.before(D.rows[pid], season, week)
    num, den = blend(sum(r[num_k] for r in this), sum(r[den_k] for r in this),
                     sum(r[num_k] for r in last), sum(r[den_k] for r in last), len(last))
    k = SHRINK[den_k]
    return (num + k * prior) / (den + k)


def opp_factor(D, opp, season, week, pos, name, league):
    """The defense's allowed rate to the position (this season before the week, last season as K_LAST games) over the
    league's, pulled OPP_PULL of the way to 1."""
    key = ("opp", opp, season, week, pos, name)
    if key not in D.cache:
        num_k, den_k = RATES[name]
        acc = {"this": [0.0, 0.0, set()], "last": [0.0, 0.0, set()]}
        for s, w, gid in D.team_games[opp]:
            part = "this" if (s == season and w < week) else "last" if s == season - 1 else None
            if part is None:
                continue
            for r in D.by_gid[gid].values():
                if r["_team"] != opp and r["_pos"] == pos:
                    acc[part][0] += r[num_k]
                    acc[part][1] += r[den_k]
                    acc[part][2].add(gid)
        num, den = blend(acc["this"][0], acc["this"][1], acc["last"][0], acc["last"][1], len(acc["last"][2]))
        f = (num / den) / league if den and league else 1.0
        D.cache[key] = 1 + OPP_PULL * (f - 1)
    return D.cache[key]


def pool(D, team, season, week):
    """Players who played for the team in its last POOL_GAMES games before the week (this season, else last season's)."""
    gs = [gid for s, w, gid in D.team_games[team] if s == season and w < week][-POOL_GAMES:]
    if not gs:
        gs = [gid for s, w, gid in D.team_games[team] if s == season - 1][-POOL_GAMES:]
    return {p for g in gs for p, r in D.by_gid[g].items() if r["_team"] == team}


def adjusted_share(D, pid, team, season, week, k, pos_of):
    """His share of k after the injury report: each listed teammate's share goes to the active pool in proportion to
    share x (SAME_POS for his position, else 1)."""
    own, n = share(D, pid, season, week, k)
    out = D.out.get((season, week, team), set()) & pool(D, team, season, week)
    out.discard(pid)
    if not out or own <= 0:
        return own, n
    active = pool(D, team, season, week) - out
    active.add(pid)
    s_ = {p: share(D, p, season, week, k)[0] for p in active}
    for x in out:
        sx = share(D, x, season, week, k)[0]
        if sx <= 0:
            continue
        w = {p: s_[p] * (SAME_POS if pos_of(p) == pos_of(x) else 1.0) for p in active}
        tw = sum(w.values())
        if tw > 0:
            own += sx * w[pid] / tw
    return own, n


class Model:
    """The fitted parts (from 2023): team-volume OLS, position priors, league allowed rates."""

    def __init__(self, D):
        self.D = D
        X, y = defaultdict(list), defaultdict(list)
        for team, gs in D.team_games.items():
            for s, w, gid in gs:
                if s != FIT:
                    continue
                f = team_features(D, team, gid)
                for k in VOLUME:
                    if f[k][0] is not None:
                        X[k].append([1.0, *f[k]])
                        y[k].append(D.team_tot[(gid, team)][k])
        self.beta = {k: np.linalg.lstsq(np.array(X[k]), np.array(y[k]), rcond=None)[0] for k in VOLUME}
        tot = defaultdict(lambda: [0.0, 0.0])
        for rows in D.rows.values():
            for r in rows:
                if r["_s"] == FIT:
                    for name, (nk, dk) in RATES.items():
                        tot[(r["_pos"], name)][0] += r[nk]
                        tot[(r["_pos"], name)][1] += r[dk]
        self.prior = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in tot.items()}

    def pos_of(self, pid):
        rs = self.D.rows.get(pid)
        return rs[-1]["_pos"] if rs else ""

    def project(self, pid, gid):
        """{market: projection} for him in the game (his row's team and opponent), or None."""
        D = self.D
        r = D.by_gid[gid].get(pid)
        if r is None:
            return None
        season, week, team, opp, pos = r["_s"], r["_w"], r["_team"], r["_opp"], r["_pos"]
        f = team_features(D, team, gid)
        vol = {k: float(np.dot(self.beta[k], [1.0, *f[k]])) for k in VOLUME if f[k][0] is not None}
        if len(vol) < 3:
            return None
        sh = {k: adjusted_share(D, pid, team, season, week, k, self.pos_of) for k in VOLUME}
        if max(n for _s, n in sh.values()) < MIN_GAMES:
            return None
        rt = {}
        for name in RATES:
            prior = self.prior.get((pos, name), 0.0)
            rt[name] = rate(D, pid, season, week, name, prior) * opp_factor(D, opp, season, week, pos, name, prior)
        tg, ca, at = vol["targets"] * sh["targets"][0], vol["carries"] * sh["carries"][0], vol["attempts"] * sh["attempts"][0]
        p = {"player_receptions": tg * rt["catch"], "player_reception_yds": tg * rt["ypt"], "player_rush_attempts": ca,
             "player_rush_yds": ca * rt["ypc"], "player_pass_attempts": at, "player_pass_completions": at * rt["comp"],
             "player_pass_yds": at * rt["ypa"]}
        p["player_rush_reception_yds"] = p["player_rush_yds"] + p["player_reception_yds"]
        return p


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def main():
    D = Data()
    M = Model(D)
    print("team volume OLS (1, team avg, spread, total):", {k: [round(float(x), 3) for x in v] for k, v in M.beta.items()})
    by_game, mine, games = U.load_stats()
    tip, rungs = U.bets("tip", by_game, mine, games)
    ev_gid = U.event_games(rungs, games)
    rows = []
    for b in tip:
        if b["mk"] not in U.HEADLINE:
            continue
        gid = ev_gid.get(b["ev"])
        row = by_game.get(gid, {}).get(b["pk"]) if gid else None
        if row is None:
            continue
        pr = M.project(row["player_id"], gid)
        if not pr:
            continue
        ladder = rungs[(b["ev"], b["pk"], b["mk"])][7].get(b["line"], {})
        over = max((v[0] for v in ladder.values()), default=None)
        act = sum(row[p] for p in U.HEADLINE[b["mk"]])
        rows.append(dict(b, proj=pr[b["mk"]], avg=(b["ratio"] * b["line"]) if b["ratio"] is not None else None, act=act, over=over))
    print(f"props with a model projection: {len(rows)}")
    # error distributions and calibration from 2023
    edges, ratios = {}, {}
    for mk in U.HEADLINE:
        fit = [r for r in rows if r["season"] == FIT and r["mk"] == mk and r["proj"] > 0]
        e = np.quantile([r["proj"] for r in fit], [1 / 3, 2 / 3])
        edges[mk] = e
        for t in range(3):
            sel = [r["act"] / r["proj"] for r in fit if np.searchsorted(e, r["proj"]) == t]
            ratios[(mk, t)] = np.sort(sel)
    for r in rows:
        if r["proj"] <= 0:
            r["p_model"] = 1.0
            continue
        a = ratios[(r["mk"], int(np.searchsorted(edges[r["mk"]], r["proj"])))]
        r["p_model"] = float(np.searchsorted(a, r["line"] / r["proj"], side="left") / len(a))
    from sklearn.linear_model import LogisticRegression
    fit = [r for r in rows if r["season"] == FIT]
    Xf = np.array([[logit(r["p_model"]), logit(1 - r["q"])] for r in fit])
    lr = LogisticRegression(C=1e6, max_iter=2000).fit(Xf, [int(r["win"]) for r in fit])
    print(f"calibration (b0, b1 model, b2 book): {lr.intercept_[0]:+.3f}, {lr.coef_[0][0]:+.3f}, {lr.coef_[0][1]:+.3f}")
    for r in rows:
        r["p"] = float(lr.predict_proba([[logit(r["p_model"]), logit(1 - r["q"])]])[0, 1])
    res = {"beta": {k: v.tolist() for k, v in M.beta.items()}, "calib": [float(lr.intercept_[0]), *map(float, lr.coef_[0])]}

    print("\n== A: accuracy, MAE (model | plain average | the line)")
    res["A"] = {}
    for s in (FIT,) + TESTS:
        wins, line = 0, []
        for mk in U.HEADLINE:
            rs = [r for r in rows if r["season"] == s and r["mk"] == mk and r["avg"] is not None]
            m_, a_, l_ = (np.mean([abs(r[k] - r["act"]) for r in rs]) for k in ("proj", "avg", "line"))
            wins += m_ < a_
            line.append(f"{mk.replace('player_', '')} {m_:.1f}|{a_:.1f}|{l_:.1f}")
        rs = [r for r in rows if r["season"] == s and r["avg"] is not None]
        pm, pa, pl = (np.mean([abs(r[k] - r["act"]) for r in rs]) for k in ("proj", "avg", "line"))
        res["A"][s] = {"model": pm, "avg": pa, "line": pl, "markets_won": int(wins)}
        print(f"  {s}{' (fit)' if s == FIT else ''}: pooled {pm:.2f} | {pa:.2f} | {pl:.2f}; model beats the average in {wins} of 8")
        print("     " + "  ".join(line))
    passA = all(res["A"][s]["model"] < res["A"][s]["avg"] and res["A"][s]["markets_won"] >= 6 for s in TESTS)
    print(f"  -> A {'PASS' if passA else 'FAIL'}")

    print("\n== B: log loss on every headline prop (recalibrated model | the book's no-vig)")
    res["B"] = {}
    for s in (FIT,) + TESTS:
        rs = [r for r in rows if r["season"] == s]
        ll = lambda key: float(-np.mean([math.log(r[key] if r["win"] else 1 - r[key]) for r in rs]))
        for r in rs:
            r["qu"] = min(max(1 - r["q"], 1e-6), 1 - 1e-6)
            r["p"] = min(max(r["p"], 1e-6), 1 - 1e-6)
        res["B"][s] = (ll("p"), ll("qu"))
        print(f"  {s}{' (fit)' if s == FIT else ''}: {res['B'][s][0]:.5f} | {res['B'][s][1]:.5f}  (n {len(rs)})")
    passB = all(res["B"][s][0] < res["B"][s][1] for s in TESTS)
    print(f"  -> B {'PASS' if passB else 'FAIL'}")

    print("\n== C: bets at EV >= 5% (best FanDuel/DraftKings price)")
    res["C"] = {}
    allbets = []
    for s in TESTS:
        bs = []
        for r in (x for x in rows if x["season"] == s):
            if r["p"] * r["under"] - 1 >= EV_AT:
                bs.append(("under", r["mk"], r["under"] - 1 if r["win"] else -1.0))
            elif r["over"] and (1 - r["p"]) * r["over"] - 1 >= EV_AT:
                bs.append(("over", r["mk"], r["over"] - 1 if not r["win"] else -1.0))
        allbets += bs
        res["C"][s] = (len(bs), float(np.mean([u for *_x, u in bs])) if bs else None)
        print(f"  {s}: {U.boot([u for *_x, u in bs])}  (unders {sum(1 for x in bs if x[0] == 'under')}, overs {sum(1 for x in bs if x[0] == 'over')})")
    v = np.array([u for *_x, u in allbets])
    lo = float(np.sort([rng.choice(v, len(v)).mean() for _ in range(2000)])[100]) if len(v) else math.nan
    passC = bool(len(v) and v.mean() > 0 and lo > 0 and all(res["C"][s][1] and res["C"][s][1] > 0 for s in TESTS))
    print(f"  pooled: {U.boot(list(v))}  -> C {'PASS' if passC else 'FAIL'}")
    for side in ("under", "over"):
        print(f"    {side}s: {U.boot([u for sd, _m, u in allbets if sd == side])}")
    for mk in U.HEADLINE:
        print(f"    {mk:28s} {U.boot([u for _sd, m, u in allbets if m == mk])}")

    print("\n== information: the under rule's ping set with the model's projection (30-50% below, -150 or better)")
    for s in (FIT,) + TESTS:
        ping = [r for r in rows if r["season"] == s and r["under"] >= U.PRICE_MIN - 1e-9 and r["proj"] > 0
                and U.PING_LO <= r["proj"] / r["line"] < U.PING_HI]
        print(f"  {s}: {U.boot([r['u'] for r in ping])}")
    res.update(passA=passA, passB=passB, passC=passC)
    OUT.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
