#!/usr/bin/env python3
"""NBA_Q15 TEST A, slots 1-3: the existing under rules (NBA_UNDER_PREREG.md amendments 1, 4 and 9), unchanged, on the
2023-2025 postseasons, which no under test has graded.

The rules and the projection are the deployed code at 0d328161ae (nba_tests4 / nba_minutes / nba_boost / nba_under),
imported from a read-only checkout of that commit (ENGINE). The one change is the input: the postseason box scores
(nba_postseason.logs_post) are added to their season's rows, so a playoff game's inputs are every game before it.
Run first on the regular seasons, it must reproduce amendment 4's counts (the harness check).

    git worktree add --detach ~/nba-engine-ro 0d328161ae      # and link its .projdata to the data
    python3 nba_q15_under_post.py [--engine ~/nba-engine-ro] [--json OUT] [--proj FILE]

--proj replaces the engine's projection with a file from nba_q15_proj.py (--mode rot / lag: without the final-margin
leak, NBA_Q15_LOG.md E8).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
POST = HERE / "nba_postseason.sqlite"


def post_rows(five):
    """logs_post in nba_minutes.load's row format, by season label ('2022-23' is the 2023 postseason)."""
    c = sqlite3.connect(f"file:{POST}?immutable=1", uri=True)
    out = {}
    for s, gid, d, tm, pid, mn, fga, fta, fg3a, fg3m, reb, ast, pts, fgm, ftm in c.execute(
            "SELECT season, game_id, date, team, player_id, min, fga, fta, fg3a, fg3m, reb, ast, pts, fgm, ftm FROM logs_post"):
        f = five.get((d, tm))
        out.setdefault(s, []).append({"season": s, "gid": gid, "date": d, "team": tm, "pid": pid, "min": mn or 0.0,
                                      "fga": fga, "fta": fta, "fg3a": fg3a, "fg3m": fg3m, "reb": reb, "ast": ast, "pts": pts,
                                      "starter": (1 if pid in f else 0) if f is not None else None, "fgm": fgm, "ftm": ftm})
    return out


def fd_unders(T, BOOST, M):
    """{(date, pid, market, line): FanDuel's under price}, for the FanDuel-only report."""
    import nba_margin_refit as MR
    g = sqlite3.connect(f"file:{M.GAMELOGS}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    o = sqlite3.connect(f"file:{M.ODDS}?mode=ro", uri=True)
    q = ("SELECT game_date, player, market, line, price FROM props WHERE book = 'fanduel' AND side = 'under' AND price IS NOT NULL "
         "AND line IS NOT NULL AND market IN (%s)" % ",".join("?" * len(BOOST.ODDS_MARKETS)))
    return {(d, name2pid[MR.norm(pl)], BOOST.ODDS_MARKETS[m], float(line)): float(pr)
            for d, pl, m, line, pr in o.execute(q, tuple(BOOST.ODDS_MARKETS)) if MR.norm(pl) in name2pid}


def flags(T, BOOST, U, season, lines, dates, proj=None):
    """Every UNDER20 flag on the given dates: (date, pid, market, line, under price, ratio, l5, actual)."""
    out = []
    for r in T.player_games(season):
        if r["date"] not in dates:
            continue
        for mk in T.MARKETS:
            ln = lines.get((r["date"], r["pid"], mk))
            if not ln:
                continue
            line, over, under, q = ln
            if proj is not None:
                pm = proj.get((r["date"], int(r["pid"]), mk))
                if pm is None:
                    continue
                r = dict(r, min=pm[1])
            ratio = (pm[0] if proj is not None else T.proj(r, mk)) / line
            if ratio >= U.RATIO_AT:
                continue
            l5 = U.last5_ratio(season.bd, r["pid"], r["date"], mk, line)
            out.append({"date": r["date"], "pid": r["pid"], "market": mk, "line": line, "under": under, "q": q,
                        "ratio": ratio, "l5": l5, "min": r["min"], "actual": BOOST.stat_of(r["box"], mk)})
    return out


def rules(f, U):
    elig = f["under"] >= U.PING_PRICE_MIN - 1e-9 and f["market"] not in U.PING_SKIP
    band = elig and U.PING_FLOOR <= f["ratio"] < U.STRONG_AT
    l5 = f["l5"]
    skip = l5 is not None and l5 == l5 and U.L5_ZONE[0] < l5 <= U.L5_ZONE[1]
    return {"UNDER20P": elig, "UNDER3050": band, "UNDER3050L": band and not skip}


def summ(fs, boot=4000, seed=7):
    if not fs:
        return {"n": 0}
    u = np.array([(f["under"] - 1) if f["actual"] < f["line"] else (0.0 if f["actual"] == f["line"] else -1.0) for f in fs])
    win = [f["actual"] < f["line"] for f in fs if f["actual"] != f["line"]]
    keys = np.array([f["date"] + str(f["pid"]) for f in fs])
    cl = {}
    for k, x in zip(keys, u):
        cl.setdefault(k, []).append(x)
    cs = list(cl.values())
    cum = np.cumsum(u)
    out = {"n": len(u), "roi": round(float(u.mean()), 4), "units": round(float(u.sum()), 1),
           "win": round(float(np.mean(win)), 4), "breakeven": round(float(np.mean([1 / f["under"] for f in fs])), 4),
           "max_dd": round(float(np.max(np.maximum.accumulate(np.concatenate([[0], cum]))[1:] - cum)), 1)}
    if boot:
        rng = np.random.default_rng(seed)
        sums, sizes = np.array([sum(c) for c in cs]), np.array([len(c) for c in cs])
        idx = rng.integers(0, len(cs), size=(boot, len(cs)))
        r = sums[idx].sum(1) / sizes[idx].sum(1)
        out["ci90"] = [round(float(np.quantile(r, .05)), 4), round(float(np.quantile(r, .95)), 4)]
        out["ci95"] = [round(float(np.quantile(r, .025)), 4), round(float(np.quantile(r, .975)), 4)]
        out["lb_bonf"] = round(float(np.quantile(r, 0.01)), 4)          # one-sided, alpha 0.05 / 5
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--engine", default=str(Path.home() / "nba-engine-ro"))
    ap.add_argument("--json")
    ap.add_argument("--proj")
    a = ap.parse_args()
    proj = None
    if a.proj:
        import pickle
        with open(a.proj, "rb") as f:
            proj = pickle.load(f)
    sys.path.insert(0, a.engine)
    import nba_boost as BOOST
    import nba_lowend as LO
    import nba_minutes as M
    import nba_tests4 as T
    import nba_under as U
    for P in (BOOST.PREV, getattr(M, "PREV", BOOST.PREV)):
        P.setdefault("2022-23", "2021-22")
    rows, pos, five = LO.load()
    rows.setdefault("2021-22", [])
    post = post_rows(five)
    post_dates = {s: {r["date"] for r in rs} for s, rs in post.items()}
    lines = T.tip_lines()
    fd = fd_unders(T, BOOST, M)
    res = {}
    # the harness check: the regular seasons, as amendment 4 graded them (1,022 / 710 bets, +16.8% / +15.0%)
    for s in ("2023-24", "2024-25"):
        season = M.Season(s, rows, pos, five)
        dates = {r["date"] for r in rows[s]}
        fs = flags(T, BOOST, U, season, lines, dates, proj)
        mid = sorted(dates)[len(dates) // 2]
        res["RS " + s] = {k: summ([f for f in fs if rules(f, U)[k]], boot=0) for k in ("UNDER20P", "UNDER3050", "UNDER3050L")}
        for k in ("UNDER20P", "UNDER3050", "UNDER3050L"):
            sel = [f for f in fs if rules(f, U)[k]]
            res["RS " + s][k]["halves"] = [summ([f for f in sel if f["date"] < mid], boot=0).get("roi"),
                                           summ([f for f in sel if f["date"] >= mid], boot=0).get("roi")]
        print("RS", s, json.dumps(res["RS " + s]), flush=True)
    # TEST A: each postseason, its rows appended to its season
    allf = []
    for s in ("2022-23", "2023-24", "2024-25"):
        rs = dict(rows)
        rs[s] = sorted(rows.get(s, []) + post[s], key=lambda r: (r["date"], r["gid"]))
        season = M.Season(s, rs, pos, five)
        fs = flags(T, BOOST, U, season, lines, post_dates[s], proj)
        for f in fs:
            f["post"] = s
        allf += fs
        print("POST", s, len(fs), "UNDER20 flags", flush=True)
    for k in ("UNDER20P", "UNDER3050", "UNDER3050L"):
        sel = [f for f in allf if rules(f, U)[k]]
        res["TEST_A " + k] = {"all": summ(sel), "by_post": {s: summ([f for f in sel if f["post"] == s], boot=0)
                                                            for s in ("2022-23", "2023-24", "2024-25")},
                              "min12": summ([f for f in sel if f["min"] >= 12]),
                              "fanduel": summ([dict(f, under=fd[k_]) for f in sel
                                               if (k_ := (f["date"], f["pid"], f["market"], f["line"])) in fd]),
                              "by_market": {m: summ([f for f in sel if f["market"] == m], boot=0) for m in T.MARKETS}}
    print(json.dumps({k: v for k, v in res.items() if k.startswith("TEST_A")}, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
