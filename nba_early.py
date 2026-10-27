#!/usr/bin/env python3
"""The early-season window and vacated shots (NBA_EARLY_PREREG.md), at the archive's tip lines, 2023-24 and 2024-25.

Part 1: a player's games 2-5, with last season as the prior: shot volume vs the points line (E1, E2), a volume surge
over last season (E3), potential assists and rebound chances vs their lines (E4, E5); the same rules in games 6+.
Part 2: when a rotation player is out (absence game 2-3), ROLE1 v3's projected FGA (team volume conserved, so a
low-volume replacement leaves shots for the shooters) against the points line (V1), vs plain season FGA (V0).

    python3 nba_early.py --gamelogs .projdata/nba_gamelogs.sqlite --odds ~/nba-engine/basketball_nba_odds_hist.sqlite \
        --tracking .projdata/tracking_hist.sqlite [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_margin_refit as MR
import nba_ratio as RATIO
import nba_role as ROLE

SEASONS = ("2023-24", "2024-25")
PREV = {"2023-24": "2022-23", "2024-25": "2023-24"}
FDK = ("fanduel", "draftkings")
MARKETS = {"player_points": "points", "player_assists": "assists", "player_rebounds": "rebounds"}
K_PRIOR, MIN_MPG, SURGE = 3.0, 20.0, 1.2


def lines(gamelogs_db, odds_db):
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, pl, m, line, side, price, book in o.execute(
            "SELECT game_date, player, market, line, side, price, book FROM props WHERE market IN ('player_points', "
            "'player_assists', 'player_rebounds') AND price IS NOT NULL AND line IS NOT NULL"):
        if book in FDK:
            raw[(d, name2pid.get(MR.norm(pl)), MARKETS[m])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    return {k: RATIO.main_line(lb) for k, lb in raw.items() if RATIO.main_line(lb)}


def summ(rs):
    if not rs:
        return {"n": 0}
    np_ = [r for r in rs if r["actual"] != r["line"]]
    return {"n": len(rs), "hit": round(float(np.mean([r["actual"] > r["line"] for r in np_])), 4) if np_ else None,
            "roi": round(float(np.mean([r["u"] for r in rs])), 4)}


def part1(gamelogs_db, tracking_db, L):
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    trk, fetched = {}, set()
    if tracking_db and Path(tracking_db).exists():
        t = sqlite3.connect(f"file:{tracking_db}?mode=ro", uri=True)
        trk = {(d, p): (pa or 0.0, rc or 0.0) for d, p, pa, rc in t.execute("SELECT date, player_id, potential_ast, reb_chances FROM tracking")}
        fetched = {d for (d,) in t.execute("SELECT DISTINCT date FROM fetched")}
    rows = []
    for s in SEASONS:
        last = defaultdict(lambda: [0, 0.0, 0.0])                # pid -> [games, minutes, FGA] last season
        for pid, mn, fga in g.execute("SELECT player_id, min, fga FROM logs_full WHERE season = ? AND min > 0", (PREV[s],)):
            x = last[pid]
            x[0] += 1
            x[1] += mn
            x[2] += fga or 0
        by_date = defaultdict(list)
        for d, pid, mn, fga, pts, ast, reb in g.execute("SELECT date, player_id, min, fga, pts, ast, reb FROM logs_full WHERE season = ? "
                                                        "AND min > 0", (s,)):
            by_date[d].append((pid, mn, fga or 0, pts or 0, ast or 0, reb or 0))
        acc = defaultdict(lambda: {"n": 0, "min": 0.0, "fga": 0.0, "pa": 0.0, "rc": 0.0, "nt": 0})
        for d in sorted(by_date):
            for pid, mn, fga, pts, ast, reb in by_date[d]:
                a = acc[pid]
                if a["n"] >= 1:
                    lg = last.get(pid)
                    use_prior = lg is not None and lg[0] >= 20
                    bl = (lambda this, per_game: (this + per_game * K_PRIOR) / (a["n"] + K_PRIOR)) if use_prior else (lambda this, _pg: this / a["n"])
                    base = {"season": s, "date": d, "pid": pid, "game_no": a["n"] + 1,
                            "mpg": a["min"] / a["n"], "fga": a["fga"] / a["n"],
                            "mpg_b": bl(a["min"], lg[1] / lg[0] if use_prior else 0), "fga_b": bl(a["fga"], lg[2] / lg[0] if use_prior else 0),
                            "fga_last": lg[2] / lg[0] if use_prior else None,
                            "pa": a["pa"] / a["nt"] if a["nt"] else None, "rc": a["rc"] / a["nt"] if a["nt"] else None}
                    for mk, act in (("points", pts), ("assists", ast), ("rebounds", reb)):
                        ml = L.get((d, pid, mk))
                        if ml:
                            line, price = ml
                            rows.append(dict(base, market=mk, line=line, actual=act,
                                             u=0.0 if act == line else (price - 1 if act > line else -1.0)))
            for pid, mn, fga, pts, ast, reb in by_date[d]:
                a = acc[pid]
                a["n"] += 1
                a["min"] += mn
                a["fga"] += fga
                if d in fetched:
                    pa, rc = trk.get((d, pid), (0.0, 0.0))
                    a["pa"] += pa
                    a["rc"] += rc
                    a["nt"] += 1
    rules = {
        "E1 FGA >= line, 20+ min (this season)": ("points", lambda r: r["mpg"] >= MIN_MPG and r["fga"] >= r["line"]),
        "E2 FGA >= line, 20+ min (blended with last season)": ("points", lambda r: r["mpg_b"] >= MIN_MPG and r["fga_b"] >= r["line"]),
        "E3 volume surge (FGA >= 1.2x last season, 20+ min, FGA >= 0.8x line)": (
            "points", lambda r: r["fga_last"] is not None and r["mpg"] >= MIN_MPG and r["fga"] >= SURGE * r["fga_last"]
            and r["fga"] >= 0.8 * r["line"]),
        "E4 potential assists >= 2x line": ("assists", lambda r: r["pa"] is not None and r["pa"] >= 2 * r["line"]),
        "E5 rebound chances >= 2x line": ("rebounds", lambda r: r["rc"] is not None and r["rc"] >= 2 * r["line"])}
    res = {}
    for name, (mk, f) in rules.items():
        out = {}
        for s in SEASONS:
            early = [r for r in rows if r["season"] == s and r["market"] == mk and 2 <= r["game_no"] <= 5]
            late = [r for r in rows if r["season"] == s and r["market"] == mk and r["game_no"] >= 6]
            out[s] = {"games 2-5": summ([r for r in early if f(r)]), "baseline 2-5 (all overs)": summ(early),
                      "games 6+": summ([r for r in late if f(r)]), "baseline 6+": summ(late)}
        out["passes"] = all(out[s]["games 2-5"].get("n") and out[s]["games 2-5"]["roi"] > 0
                            and out[s]["games 2-5"]["roi"] > out[s]["baseline 2-5 (all overs)"]["roi"] for s in SEASONS)
        res[name] = out
    return res


def part2(gamelogs_db, L):
    rows_by_season, groups = ROLE.load(gamelogs_db)
    res = {}
    for s in SEASONS:
        season, priors = ROLE.Season(rows_by_season[s]), ROLE.Priors(rows_by_season[ROLE.PREV[s]], groups)
        recs = []
        for team, games in season.games.items():
            for i, (d, g, box) in enumerate(games):
                if i < ROLE.X_GAMES:
                    continue
                played = {p for p, r in box.items() if r["min"]}
                last3 = season.roster(team, d)
                spots = season.absences(team, d, last3 - played)
                if not spots:
                    continue
                n = min(spots.values())
                if n > 3:
                    continue
                active = last3 & played
                proj = ROLE.project(season, priors, groups, team, d, active, set(spots), mode="v3")
                prior = season.before(team, d)
                for p in active:
                    ml = L.get((d, p, "points"))
                    hist = [b[p] for _d, _g, b in prior if p in b and b[p]["min"]]
                    if not ml or p not in proj or not hist:
                        continue
                    line, price = ml
                    mpg = sum(h["min"] for h in hist) / len(hist)
                    if mpg < MIN_MPG:
                        continue
                    act = box[p]["pts"] or 0
                    recs.append({"n": n, "line": line, "actual": act, "u": 0.0 if act == line else (price - 1 if act > line else -1.0),
                                 "fga_proj": proj[p]["fga"], "fga_season": sum(h["fga"] or 0 for h in hist) / len(hist)})
        out = {}
        for lab, keep in (("absence games 2-3", lambda r: r["n"] in (2, 3)), ("absence game 1 (hindsight caveat)", lambda r: r["n"] == 1)):
            rs = [r for r in recs if keep(r)]
            out[lab] = {"V1 projected FGA >= line": summ([r for r in rs if r["fga_proj"] >= r["line"]]),
                        "V0 season FGA >= line": summ([r for r in rs if r["fga_season"] >= r["line"]]),
                        "baseline (all overs, 20+ min)": summ(rs)}
        res[s] = out
    v = lambda s: res[s]["absence games 2-3"]
    res["V1 passes"] = all(v(s)["V1 projected FGA >= line"].get("n") and v(s)["V1 projected FGA >= line"]["roi"] > 0
                           and v(s)["V1 projected FGA >= line"]["roi"] > v(s)["baseline (all overs, 20+ min)"]["roi"] for s in SEASONS)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamelogs", required=True)
    ap.add_argument("--odds", required=True)
    ap.add_argument("--tracking")
    ap.add_argument("--json")
    a = ap.parse_args()
    L = lines(a.gamelogs, a.odds)
    res = {"part1_early": part1(a.gamelogs, a.tracking, L), "part2_vacated_shots": part2(a.gamelogs, L)}
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
