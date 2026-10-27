#!/usr/bin/env python3
"""Why the flags win and lose (NBA_FLAGS_WL_PREREG.md). Descriptive: no rule changes here.

Every wowy projection is rate x minutes, so each result splits exactly (in stat units) into
    actual - proj = proj_rate x (min - proj_min)  +  min x (rate - proj_rate)
                    ^ the minutes effect             ^ the rate effect
(the additive form of the registered log split; it keeps games where B scored 0).

    python3 nba_flags_wl.py backtest ROWS_PKL GAMELOGS [--json OUT]   # vol4 rows, 2023-24 and 2024-25
    python3 nba_flags_wl.py live [--json OUT]                         # on the VM: shadow flags, graded
"""
import argparse
import json
import pickle
import sqlite3
import statistics as st
from collections import defaultdict

A_MIN, K_MIN = 0.980, 0.356                     # nba_flags.MIN_A, MIN_K (amendment 23)
MARGIN = {"pts": 5.0, "reb": 1.0, "pra": 6.5}   # nba_flags.MARGIN (amendment 23)
SPLIT = "2024-08-01"


def units(act, line, price):
    return (price - 1.0) if act > line else 0.0 if act == line else -1.0


def band(v, cuts, labels):
    for c, lab in zip(cuts, labels):
        if v < c:
            return lab
    return labels[-1]


def summ(rs):
    """Record, accuracy and the minutes/rate split for a list of plays."""
    if not rs:
        return {"n": 0}
    u = [r["u"] for r in rs]
    out = {"n": len(rs), "w": sum(r["u"] > 0 for r in rs), "l": sum(r["u"] < 0 for r in rs),
           "units": round(sum(u), 2), "roi": round(100 * sum(u) / len(rs), 1),
           "act_minus_proj": round(st.mean(r["act"] - r["proj"] for r in rs), 2),
           "act_minus_line": round(st.mean(r["act"] - r["line"] for r in rs), 2),
           "proj_closer_than_line": round(st.mean(abs(r["proj"] - r["act"]) < abs(r["line"] - r["act"]) for r in rs), 3)}
    sp = [r for r in rs if r.get("min") is not None]
    if sp:
        for lab, sub in (("win", [r for r in sp if r["u"] > 0]), ("loss", [r for r in sp if r["u"] < 0])):
            if sub:
                out[f"{lab}_minutes_effect"] = round(st.mean(r["m_eff"] for r in sub), 2)
                out[f"{lab}_rate_effect"] = round(st.mean(r["r_eff"] for r in sub), 2)
                out[f"{lab}_min_minus_proj_min"] = round(st.mean(r["min"] - r["pmin"] for r in sub), 2)
        ls = [r for r in sp if r["u"] < 0]
        out["losses_4plus_min_short"] = round(st.mean(r["min"] <= r["pmin"] - 4 for r in ls), 3) if ls else None
        out["rate_realized_over_projected"] = round(sum(r["act"] for r in sp) / max(1e-9, sum(r["min"] * r["prate"] for r in sp)), 3)
        out["min_realized_over_projected"] = round(sum(r["min"] for r in sp) / max(1e-9, sum(r["pmin"] for r in sp)), 3)
    return out


def split_effects(r):
    """Attach proj_min, proj_rate and the two effects (needs r['min'], r['base_min'], r['d_min'])."""
    r["pmin"] = r["base_min"] + A_MIN + K_MIN * r["d_min"]
    r["prate"] = r["proj"] / r["pmin"] if r["pmin"] > 0 else 0.0
    if r.get("min") is not None:
        rate = r["act"] / r["min"] if r["min"] > 0 else 0.0
        r["m_eff"] = r["prate"] * (r["min"] - r["pmin"])
        r["r_eff"] = r["min"] * (rate - r["prate"])
    return r


CELLS = {
    "stat": lambda r: r["stat"],
    "excess": lambda r: band(r["ex"], (1.25, 1.5, 2.0), ("1-1.25", "1.25-1.5", "1.5-2", "2+")),
    "price": lambda r: band(r["price"], (1.8, 1.9, 2.0), ("<1.80", "1.80-1.90", "1.90-2.00", "2.00+")),
    "absent star min": lambda r: band(r["xmin"], (28, 32), ("24-28", "28-32", "32+")),
    "absence game": lambda r: "1" if r["aidx"] == 1 else "2" if r["aidx"] == 2 else "3-4",
    "minutes band": lambda r: band(r["d_min"], (3, 8), ("<3", "3-8", "8+")),
    "B's base minutes": lambda r: band(r["base_min"], (20, 28), ("<20", "20-28", "28+")),
    "back to back": lambda r: "yes" if r.get("b2b") else "no",
    "stars out": lambda r: "2+" if r["n_out"] >= 2 else "1",
}


def backtest(pkl, gamelogs):
    rows = pickle.load(open(pkl, "rb"))
    g = sqlite3.connect(f"file:{gamelogs}?mode=ro", uri=True)
    mins = {(gid, pid): mn for gid, pid, mn in g.execute("SELECT game_id, player_id, min FROM logs")}
    plays = []
    for r in rows:
        if not r.get("fdk"):
            continue
        line, price = r["fdk"]
        r = dict(r, line=line, price=price, season="23-24" if r["date"] < SPLIT else "24-25",
                 min=mins.get((r["gid"], r["b"])), u=units(r["act"], line, price),
                 ex=(r["proj"] - line) / MARGIN[r["stat"]])
        split_effects(r)
        plays.append(r)
    card_u = lambda r: (3 <= r["d_min"] <= 8 and r["n_out"] < 2 and r["xmin"] < 32 and r["price"] >= 1.8
                        and 1 <= r["ex"] < 2)
    universes = {"all candidates": lambda r: True, "excess >= 1": lambda r: r["ex"] >= 1, "card universe": card_u}
    rep = {}
    for un, f in universes.items():
        for s in ("23-24", "24-25"):
            rep[f"{un} | {s}"] = summ([r for r in plays if r["season"] == s and f(r)])
    cells = {}
    for cname, fn in CELLS.items():
        for un in ("excess >= 1", "card universe"):
            by = defaultdict(lambda: defaultdict(list))
            for r in plays:
                if universes[un](r):
                    by[fn(r)][r["season"]].append(r)
            cells[f"{un} | {cname}"] = {k: {s: summ(v[s]) for s in ("23-24", "24-25")} for k, v in sorted(by.items())}
    return {"summary": rep, "cells": cells, "n_plays": len(plays),
            "minutes_joined": round(st.mean(r["min"] is not None for r in plays), 3)}


def live():
    import nba_clv as V
    rows = [r for r in V.collect() if r.get("actual") is not None]
    m = sqlite3.connect(f"file:{V.HERE / 'nba_matchup.sqlite'}?mode=ro", uri=True)
    g = sqlite3.connect(f"file:{V.HERE / 'nba_gamelogs.sqlite'}?mode=ro", uri=True)
    box = {(gid, pid): mn for gid, pid, mn in m.execute("SELECT gid, pid, min FROM player_games")}
    apps = defaultdict(list)                                  # pid -> [(date, min)] across seasons, played games
    for d, pid, mn in g.execute("SELECT date, player_id, min FROM logs WHERE min > 0"):
        apps[pid].append((d, mn))
    for d, pid, mn in m.execute("SELECT g.date, p.pid, p.min FROM player_games p JOIN games g ON g.gid = p.gid WHERE p.min > 0"):
        apps[pid].append((d, mn))
    for v in apps.values():
        v.sort()
    plays = []
    for r in rows:
        last = [mn for d, mn in apps.get(r["pid"], []) if d < r["game_date"]][-10:]
        p = {"tier": r["tier"], "stat": r["stat"], "act": r["actual"], "line": r["line"], "price": r["odds"],
             "proj": r.get("proj") or r["line"], "u": units(r["actual"], r["line"], r["odds"]),
             "card": "ON" if r.get("card") == 1 else "OFF", "card_why": r.get("card_why"),
             "latency": r.get("latency_min"), "move": r.get("move"), "fd_move": r.get("fd_move"),
             "stale": (r.get("cells") or {}).get("STALE LINE"), "d_min": r.get("d_min"), "x_min": r.get("x_min"),
             "date": r["game_date"], "b": r["b"]}
        if r["tier"].startswith("wowy") and r.get("d_min") is not None and len(last) >= 3:
            p.update(base_min=sum(last) / len(last), min=box.get((r["gid"], r["pid"])))
            split_effects(p)
        plays.append(p)
    groups = {
        "all": lambda p: True,
        "tier": lambda p: p["tier"],
        "card": lambda p: p["card"],
        "stat": lambda p: {"points": "pts", "rebounds": "reb", "assists": "ast"}.get(p["stat"], p["stat"]),
        "latency": lambda p: "n/a" if p["latency"] is None else band(p["latency"], (15, 120), ("<=15 min", "15-120", "2h+")),
        "stale line": lambda p: p["stale"] or "n/a",
        "closing line vs flag (FanDuel)": lambda p: "n/a" if p["fd_move"] is None else
        band(p["fd_move"], (-1e-9, 1e-9), ("moved against", "unchanged", "moved toward")),
        "minutes band": lambda p: "n/a" if p["d_min"] is None else band(p["d_min"], (3, 8), ("<3", "3-8", "8+")),
    }
    rep = {}
    for gname, fn in groups.items():
        by = defaultdict(list)
        for p in plays:
            by[fn(p)].append(p)
        rep[gname] = {k: summ(v) for k, v in sorted(by.items(), key=lambda kv: str(kv[0]))}
    clv = [p["fd_move"] for p in plays if p["fd_move"] is not None]
    rep["clv"] = {"n": len(clv), "mean_fd_close_minus_flag": round(st.mean(clv), 3) if clv else None,
                  "beat": round(st.mean(x > 0 for x in clv), 3) if clv else None,
                  "lost": round(st.mean(x < 0 for x in clv), 3) if clv else None}
    rep["minutes_joined"] = sum(p.get("min") is not None for p in plays)
    return rep, plays


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("backtest", "live"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.mode == "backtest":
        rep = backtest(*a.args)
    else:
        rep, _ = live()
    print(json.dumps(rep, indent=1, default=str))
    if a.json:
        open(a.json, "w").write(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
