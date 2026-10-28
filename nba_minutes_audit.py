#!/usr/bin/env python3
"""MINUTES amendment 1: the audit. Residuals of the target-A blend (and of V3 for target B) on 2023-24 only, by bucket
of each candidate nuance (NBA_MINUTES_PREREG.md). Exploration: nothing here is a test.

    python3 nba_minutes_audit.py [--json OUT]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_minutes as M

SEASON = "2023-24"


def homes(raw_db=M.RAW):
    """{(date, team): True if home} from the lineups files."""
    c = sqlite3.connect(f"file:{raw_db}?mode=ro", uri=True)
    out = {}
    for key, body in c.execute("SELECT key, body FROM raw WHERE kind = 'lineups' AND status = 200"):
        try:
            j = json.loads(zlib.decompress(body))
        except (zlib.error, TypeError, ValueError):
            j = json.loads(body)
        for g in j.get("games", []):
            for side, home in (("homeTeam", True), ("awayTeam", False)):
                t = (g.get(side) or {}).get("teamAbbreviation")
                if t:
                    out[(key, t)] = home
    return out


def context(season, rows):
    """Extra per-row context for the audit (pre-game, except the hindsight block)."""
    bd = season.bd
    g = sqlite3.connect(f"file:{M.GAMELOGS}?mode=ro", uri=True)
    team_pts, team_min = {}, {}
    for gid, tm, pts, mn in g.execute("SELECT game_id, team, SUM(pts), SUM(min) FROM logs_full WHERE season = ? GROUP BY 1, 2", (SEASON,)):
        team_pts[(gid, tm)], team_min[(gid, tm)] = pts, mn
    by_gid = defaultdict(dict)
    for (gid, tm), v in team_pts.items():
        by_gid[gid][tm] = v
    pf = {(gid, pid): f for gid, pid, f in g.execute("SELECT game_id, player_id, pf FROM logs_full WHERE season = ?", (SEASON,))}
    home = homes()
    for r in rows:
        mine = season.before(r["pid"], r["date"])
        gap = (dt.date.fromisoformat(r["date"]) - dt.date.fromisoformat(mine[-1]["date"])).days if mine else None
        starts = [x for x in mine if x.get("starter") == 1]
        prior = bd.before(r["team"], r["date"])
        st_min = [x["min"] for _d, _g, _s, b in prior[-10:] for x in b.values() if x.get("starter") == 1]
        other = [v for t, v in by_gid[r["gid"]].items() if t != r["team"]]
        r.update({
            "gap": gap, "starts_this": sum(1 for x in starts if x["season"] == SEASON),
            "starts_for_x": bd.started_for(r["x"], r["team"], r["date"]).get(r["pid"], 0),
            "team_starter_min": sum(st_min) / len(st_min) if st_min else None,
            "home": home.get((r["date"], r["team"])),
            "month": int(r["date"][5:7]),
            "margin": (by_gid[r["gid"]].get(r["team"], 0) - other[0]) if other else None,
            "ot": team_min.get((r["gid"], r["team"]), 0) > 245,
            "fouls5": (pf.get((r["gid"], r["pid"])) or 0) >= 5,
            "x_group": season.groups.get(r["x"]), "p_group": season.groups.get(r["pid"]),
        })


BUCKETS = {
    "n_starts": lambda r: "0" if r["n_starts"] == 0 else "1-2" if r["n_starts"] <= 2 else "3-5" if r["n_starts"] <= 5 else "6-10",
    "starts this season": lambda r: "none" if r["starts_this"] == 0 else "1-4" if r["starts_this"] <= 4 else "5+",
    "started before for this X": lambda r: "yes" if r["starts_for_x"] else "no",
    "X minutes": lambda r: "unknown" if np.isnan(r["x_mpg"]) else "<28" if r["x_mpg"] < 28 else "28-32" if r["x_mpg"] < 32 else "32+",
    "same position as X": lambda r: "yes" if r["x_group"] and r["x_group"] == r["p_group"] else "no",
    "X's group": lambda r: r["x_group"] or "?",
    "starters out": lambda r: "1" if r["n_out"] <= 1 else "2+",
    "absence game": lambda r: str(r["n"]),
    "rest days": lambda r: "?" if r["gap"] is None else "b2b" if r["gap"] <= 1 else "1 day" if r["gap"] == 2 else "2+ days" if r["gap"] <= 7 else "8+ (layoff)",
    "month": lambda r: {10: "Oct-Nov", 11: "Oct-Nov", 12: "Dec-Jan", 1: "Dec-Jan", 2: "Feb-Mar", 3: "Feb-Mar", 4: "Apr"}.get(r["month"], "?"),
    "home": lambda r: "home" if r["home"] else "away" if r["home"] is False else "?",
    "team starter minutes": lambda r: "?" if r["team_starter_min"] is None else "<30" if r["team_starter_min"] < 30 else "30-32" if r["team_starter_min"] < 32 else "32+",
    "rotation size": lambda r: "<=8" if r["rotation"] <= 8 else "9" if r["rotation"] == 9 else "10+",
    "his season mpg": lambda r: "?" if np.isnan(r["season_mpg"]) else "<15" if r["season_mpg"] < 15 else "15-22" if r["season_mpg"] < 22 else "22-28" if r["season_mpg"] < 28 else "28+",
    "HINDSIGHT margin": lambda r: "?" if r["margin"] is None else "20+ blowout" if abs(r["margin"]) >= 20 else "10-19" if abs(r["margin"]) >= 10 else "<10",
    "HINDSIGHT overtime": lambda r: "OT" if r["ot"] else "regulation",
    "HINDSIGHT 5+ fouls": lambda r: "yes" if r["fouls5"] else "no",
}


def table(rows, pred):
    out = {}
    for name, f in BUCKETS.items():
        b = defaultdict(list)
        for r in rows:
            b[f(r)].append(r["actual"] - pred(r))
        out[name] = {k: {"n": len(v), "bias": round(float(np.mean(v)), 2), "mae": round(float(np.mean(np.abs(v))), 2)}
                     for k, v in sorted(b.items())}
    return out


def teams(rows, pred):
    b = defaultdict(list)
    for r in rows:
        b[r["team"]].append(r["actual"] - pred(r))
    return {t: {"n": len(v), "bias": round(float(np.mean(v)), 2)} for t, v in sorted(b.items(), key=lambda kv: np.mean(kv[1]))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    rows, pos, five = M.load()
    season = M.Season(SEASON, rows, pos, five)
    rs = [r for r in M.spots(season) if r["know"] == "confirmed" and r["n"] <= M.SPOT_MAX and not np.isnan(r["v3"]) and not np.isnan(r["l5"])]
    context(season, rs)
    A, B = [r for r in rs if r["target"] == "A"], [r for r in rs if r["target"] == "B"]
    res = {"A (blend)": {"all": {"n": len(A), "bias": round(float(np.mean([r["actual"] - M.blend(r) for r in A])), 2),
                                 "mae": round(float(np.mean([abs(r["actual"] - M.blend(r)) for r in A])), 2)},
                         "buckets": table(A, M.blend), "teams": teams(A, M.blend)},
           "B (V3)": {"all": {"n": len(B), "bias": round(float(np.mean([r["actual"] - r["v3"] for r in B])), 2),
                              "mae": round(float(np.mean([abs(r["actual"] - r["v3"]) for r in B])), 2)},
                      "buckets": table(B, lambda r: r["v3"]), "teams": teams(B, lambda r: r["v3"])}}
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
