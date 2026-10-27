#!/usr/bin/env python3
"""The user's volume-to-line ratios (NBA_RATIO_PREREG.md), backtested at the archive's tip lines.

  FGA  over in points   when season-to-date FGA per game            >= the points line
  PA   over in assists  when season-to-date potential assists/game  >= 2 x the assists line
  RC   over in rebounds when season-to-date rebound chances/game    >= 2 x the rebounds line (2.5x also reported)
Season to date = his games this season before the date (minutes > 0), at least 3. No hindsight: all known pre-game.

    python3 nba_ratio.py --gamelogs .projdata/nba_gamelogs.sqlite --odds ~/nba-engine/basketball_nba_odds_hist.sqlite \
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

SEASONS = ("2023-24", "2024-25")
MIN_GAMES, EARLY = 3, 10
FDK = ("fanduel", "draftkings")
MARKETS = {"player_points": "points", "player_assists": "assists", "player_rebounds": "rebounds"}
RULES = {"FGA": ("points", "fga", 1.0), "PA": ("assists", "pa", 2.0), "RC": ("rebounds", "rc", 2.0), "RC2.5": ("rebounds", "rc", 2.5)}
BANDS = {"FGA": (1.1, 1.25), "PA": (2.25, 2.5), "RC": (2.25, 2.5), "RC2.5": (2.75, 3.0)}
ACTUAL = {"points": "pts", "assists": "ast", "rebounds": "reb"}


def main_line(lb):
    """(line, best FanDuel/DraftKings over) at the two-sided rung whose over is nearest even money."""
    best = None
    for line, bk in lb.items():
        ov = [v[0] for b, v in bk.items() if b in FDK and v[0] and v[1]]
        if ov:
            gap = min(abs(x - 2.0) for x in ov)
            if best is None or gap < best[0] - 1e-9:
                best = (gap, line, max(ov))
    return (best[1], best[2]) if best else None


def build(gamelogs_db, odds_db, tracking_db=None):
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    trk = {}
    if tracking_db and Path(tracking_db).exists():
        t = sqlite3.connect(f"file:{tracking_db}?mode=ro", uri=True)
        trk = {(d, p): (pa or 0.0, rc or 0.0) for d, p, pa, rc in t.execute("SELECT date, player_id, potential_ast, reb_chances FROM tracking")}
        tracked_dates = {d for (d, _m) in t.execute("SELECT date, measure FROM fetched")}
    o = sqlite3.connect(f"file:{odds_db}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, pl, m, line, side, price, book in o.execute(
            "SELECT game_date, player, market, line, side, price, book FROM props WHERE market IN ('player_points', "
            "'player_assists', 'player_rebounds') AND price IS NOT NULL AND line IS NOT NULL"):
        if book in FDK:
            raw[(d, name2pid.get(MR.norm(pl)), MARKETS[m])][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    rows = []
    for s in SEASONS:
        by_date = defaultdict(list)
        for d, pid, mn, fga, pts, ast, reb in g.execute("SELECT date, player_id, min, fga, pts, ast, reb FROM logs_full WHERE season = ?", (s,)):
            if mn:
                by_date[d].append((pid, fga or 0, pts or 0, ast or 0, reb or 0, mn))
        acc = defaultdict(lambda: {"n": 0, "min": 0.0, "fga": 0.0, "pa": 0.0, "rc": 0.0, "n_trk": 0})
        for d in sorted(by_date):
            for pid, fga, pts, ast, reb, _mn in by_date[d]:
                a = acc[pid]
                if a["n"] >= MIN_GAMES:
                    for mk in ("points", "assists", "rebounds"):
                        lb = raw.get((d, pid, mk))
                        ml = main_line(lb) if lb else None
                        if not ml:
                            continue
                        line, price = ml
                        act = {"points": pts, "assists": ast, "rebounds": reb}[mk]
                        rows.append({"season": s, "date": d, "pid": pid, "market": mk, "line": line, "price": price,
                                     "games": a["n"], "mpg": a["min"] / a["n"], "fga": a["fga"] / a["n"],
                                     "pa": a["pa"] / a["n_trk"] if a["n_trk"] else None,
                                     "rc": a["rc"] / a["n_trk"] if a["n_trk"] else None, "actual": act,
                                     "u": (price - 1) if act > line else 0.0 if act == line else -1.0})
            for pid, fga, pts, ast, reb, mn in by_date[d]:      # the date's games join the season-to-date totals
                a = acc[pid]
                a["n"] += 1
                a["min"] += mn
                a["fga"] += fga
                if trk and d in tracked_dates:                    # a missing row on a fetched date is 0 (the feeds omit zeros)
                    pa, rc = trk.get((d, pid), (0.0, 0.0))
                    a["pa"] += pa
                    a["rc"] += rc
                    a["n_trk"] += 1
    return rows


def summ(rs):
    if not rs:
        return {"n": 0}
    np_ = [r for r in rs if r["actual"] != r["line"]]
    return {"n": len(rs), "hit": round(float(np.mean([r["actual"] > r["line"] for r in np_])), 4) if np_ else None,
            "roi": round(float(np.mean([r["u"] for r in rs])), 4)}


def report(rows):
    res = {}
    for rule, (mk, key, k) in RULES.items():
        out = {}
        for s in SEASONS:
            base = [r for r in rows if r["season"] == s and r["market"] == mk and r[key] is not None]
            hit = [r for r in base if r[key] >= k * r["line"]]
            lo, hi = BANDS[rule]
            band = lambda r: "low" if r[key] < lo * r["line"] else "high" if r[key] >= hi * r["line"] else "mid"
            out[s] = {"rule": summ(hit), "all_overs": summ(base), "share_of_props": round(len(hit) / len(base), 4) if base else None,
                      "bands": {b: summ([r for r in hit if band(r) == b]) for b in ("low", "mid", "high")},
                      "early (<= 10 games)": summ([r for r in hit if r["games"] <= EARLY]),
                      "later": summ([r for r in hit if r["games"] > EARLY])}
        out["passes"] = all(out[s]["rule"].get("n") and out[s]["rule"]["roi"] > 0 and out[s]["rule"]["roi"] > out[s]["all_overs"]["roi"]
                            for s in SEASONS)
        res[rule] = out
    return res


# ── amendment 1: the solver ───────────────────────────────────────────────────────────────────────────────────
GRID = {"FGA": [round(0.80 + 0.05 * i, 2) for i in range(25)], "PA": [round(1.0 + 0.1 * i, 1) for i in range(31)],
        "RC": [round(1.0 + 0.1 * i, 1) for i in range(31)]}
MIN_PICK = 150


def solve(rows, rule):
    """ROI by threshold in each season; the best k (n >= MIN_PICK) on one season, checked on the other, both ways."""
    mk, key, _k = RULES[rule]
    curve = {}
    for k in GRID[rule]:
        curve[k] = {s: summ([r for r in rows if r["season"] == s and r["market"] == mk and r[key] is not None
                             and r[key] >= k * r["line"]]) for s in SEASONS}
    out = {"curve": {str(k): v for k, v in curve.items()}, "checks": {}}
    for fit, chk in ((SEASONS[0], SEASONS[1]), (SEASONS[1], SEASONS[0])):
        ok = [k for k in GRID[rule] if curve[k][fit].get("n", 0) >= MIN_PICK]
        if not ok:
            out["checks"][f"pick on {fit}"] = None
            continue
        k = max(ok, key=lambda x: curve[x][fit]["roi"])
        i = GRID[rule].index(k)
        nb = [GRID[rule][j] for j in (i - 1, i + 1) if 0 <= j < len(GRID[rule])]
        out["checks"][f"pick on {fit}"] = {"k": k, "fit": curve[k][fit], "check": curve[k][chk],
                                           "neighbours": {str(x): curve[x] for x in nb}}
    picks = [v for v in out["checks"].values() if v]
    out["profitable"] = bool(picks) and all(
        v["check"].get("n") and v["check"]["roi"] > 0 and all(n_[s]["roi"] > 0 for n_ in v["neighbours"].values() for s in SEASONS if n_[s].get("n"))
        for v in picks)
    return out


# ── amendment 2: minutes first ────────────────────────────────────────────────────────────────────────────────
MIN_MPG = 20.0


def minutes_first(rows):
    """Each rule at 20+ season minutes (FGA at k = 1.0, 1.1, 1.2), its baseline, and the solver within 20+ minutes."""
    r20 = [r for r in rows if r["mpg"] >= MIN_MPG]
    res = {}
    for rule, ks in (("FGA", (1.0, 1.1, 1.2)), ("PA", (2.0,)), ("RC", (2.0, 2.5))):
        mk, key, _k = RULES[rule]
        out = {}
        for s in SEASONS:
            base = [r for r in r20 if r["season"] == s and r["market"] == mk and r[key] is not None]
            out[s] = {"all_overs_20min": summ(base),
                      **{f"k={k}": summ([r for r in base if r[key] >= k * r["line"]]) for k in ks}}
        prim = f"k={ks[0]}"
        out["passes"] = all(out[s][prim].get("n") and out[s][prim]["roi"] > 0 and out[s][prim]["roi"] > out[s]["all_overs_20min"]["roi"]
                            for s in SEASONS)
        out["solver"] = solve(r20, rule)
        res[rule] = out
    return res


# ── forward (NBA_RATIO_PREREG.md): this season's volume as of a date, for the side-by-side at the opener ──────────
FORWARD = {"RATIO_FGA": ("points", "fga", 1.0), "RATIO_PA": ("assists", "pa", 2.0), "RATIO_RC": ("rebounds", "rc", 2.0)}


class RatioData:
    """This season's per-game volume before a date: FGA from nba_matchup's box scores; potential assists and rebound
    chances from nba_tracking (a missing row on a fetched date is 0: the feeds omit zeros)."""

    def __init__(self, matchup_db, tracking_db, season):
        def ro(path):
            return sqlite3.connect(f"file:{path}?mode=ro", uri=True) if Path(path).exists() else None
        m, t = ro(matchup_db), ro(tracking_db)
        self.games = defaultdict(list)                   # pid -> [(date, fga)]
        if m is not None:
            for d, pid, fga in m.execute("SELECT gm.date, p.pid, p.fga FROM player_games p JOIN games gm ON gm.gid = p.gid "
                                         "WHERE gm.season = ? AND p.min > 0", (season,)):
                self.games[pid].append((d, fga or 0.0))
        self.trk, self.fetched = {}, set()
        if t is not None:
            self.fetched = {d for d, ms in t.execute("SELECT date, COUNT(DISTINCT measure) FROM fetched GROUP BY date") if ms >= 2}
            self.trk = {(d, p): (pa or 0.0, rc or 0.0) for d, p, pa, rc in t.execute("SELECT date, player_id, potential_ast, reb_chances FROM tracking")}

    def volume(self, pid, date):
        """{n, fga, pa, rc} per game over his games this season before the date (pa / rc over tracked dates), or None."""
        g = [(d, f) for d, f in self.games.get(pid, ()) if d < date]
        if len(g) < MIN_GAMES:
            return None
        tr = [self.trk.get((d, pid), (0.0, 0.0)) for d, _f in g if d in self.fetched]
        return {"n": len(g), "fga": sum(f for _d, f in g) / len(g),
                "pa": sum(x[0] for x in tr) / len(tr) if tr else None, "rc": sum(x[1] for x in tr) / len(tr) if tr else None}


def ratio_eval(rd, rule, pid, date, market, line):
    """True when the rule's volume clears its multiple of the line."""
    mk, key, k = FORWARD[rule]
    v = rd.volume(pid, date) if mk == market else None
    return bool(v and v[key] is not None and v[key] >= k * line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamelogs", required=True)
    ap.add_argument("--odds", required=True)
    ap.add_argument("--tracking")
    ap.add_argument("--solve", nargs="*", metavar="RULE")
    ap.add_argument("--minutes-first", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.minutes_first:
        res = minutes_first(build(a.gamelogs, a.odds, a.tracking))
        print(json.dumps(res, indent=1))
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=1))
        return
    if a.solve is not None:
        rows = build(a.gamelogs, a.odds, a.tracking)
        res = {r: solve(rows, r) for r in (a.solve or ["FGA", "PA", "RC"])}
        print(json.dumps(res, indent=1))
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=1))
        return
    res = report(build(a.gamelogs, a.odds, a.tracking))
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
