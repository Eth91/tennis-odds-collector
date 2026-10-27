#!/usr/bin/env python3
"""The shot-zone matchup test (NBA_ZONES_PREREG.md): does a player who scores inside go over against a team that
gives up a lot inside? Every feature is season to date, strictly before the game's date: no hindsight.

    python3 nba_zones.py --shots .projdata/shots_hist.sqlite --data ~/nba-engine [--json OUT]
--data holds nba_matchup.sqlite (2023-25 box scores), nba_gamelogs.sqlite (names) and basketball_nba_odds_hist.sqlite.
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

ZONES = ("ra", "paint", "mid", "c3", "ab3")
INSIDE = ("ra", "paint")
FDK = {"fanduel", "draftkings"}
MIN_GAMES, MIN_FGA, MIN_TEAM_GAMES = 5, 50, 10
SPLIT = "2024-08-01"


def zone(x, y):
    """The zone of a shot at (x, y), tenths of a foot from the basket."""
    d = math.hypot(x, y)
    if d <= 40:
        return "ra"
    if abs(x) >= 220 and y <= 92.5:
        return "c3"
    if d >= 237.5:
        return "ab3"
    if abs(x) <= 80 and y <= 142.5:
        return "paint"
    return "mid"


def main_line(lines_by_book):
    """(line, best FanDuel/DraftKings over) at the rung whose over is nearest even money (two-sided)."""
    best = None
    for line, bk in lines_by_book.items():
        ov = [v[0] for b, v in bk.items() if b in FDK and v[0] and v[1]]
        if ov:
            gap = min(abs(x - 2.0) for x in ov)
            if best is None or gap < best[0] - 1e-9:
                best = (gap, line, max(ov))
    return (best[1], best[2]) if best else None


def build(shots_db, data):
    m = sqlite3.connect(f"file:{data / 'nba_matchup.sqlite'}?mode=ro", uri=True)
    games = {g: (d, s, h, a) for g, d, s, h, a in m.execute("SELECT gid, date, season, home, away FROM games WHERE season IN ('2023-24', '2024-25')")}
    shots = defaultdict(list)                            # gid -> [(pid, zone, points)]
    fga_of = defaultdict(int)                            # (gid, pid) -> field-goal attempts (every shot is one)
    s = sqlite3.connect(f"file:{shots_db}?mode=ro", uri=True)
    for g, p, x, y, made in s.execute("SELECT gid, pid, x, y, made FROM shots"):
        if g in games:
            z = zone(x, y)
            shots[g].append((p, z, (3 if z in ("c3", "ab3") else 2) if made else 0))
            fga_of[(g, p)] += 1
    box = defaultdict(dict)                              # gid -> {pid: (team, min, pts, fga)}
    for g, tm, p, mn, pts in m.execute("SELECT gid, team, pid, min, pts FROM player_games"):
        if g in games:
            box[g][p] = (tm, mn, pts, fga_of.get((g, p), 0))
    # props: the archive's points main line at the tip snapshot
    gl = sqlite3.connect(f"file:{data / 'nba_gamelogs.sqlite'}?mode=ro", uri=True)
    name2pid = {}
    for pid, nm in gl.execute("SELECT DISTINCT player_id, player FROM logs"):
        name2pid[MR.norm(nm)] = pid
    o = sqlite3.connect(f"file:{data / 'basketball_nba_odds_hist.sqlite'}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    for d, p, line, side, price, book in o.execute("SELECT game_date, player, line, side, price, book FROM props WHERE market = "
                                                   "'player_points' AND price IS NOT NULL AND line IS NOT NULL"):
        if book in FDK:
            raw[(d, MR.norm(p))][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    lines = {}
    for (d, nm), lb in raw.items():
        pid = name2pid.get(nm)
        ml = main_line(lb)
        if pid and ml:
            lines[(d, pid)] = ml
    # walk dates: features from the state before the date, then add the date's games
    by_date = defaultdict(list)
    for g, (d, season, h, a) in games.items():
        by_date[(season, d)].append(g)
    rows = []
    state = {}
    for season, d in sorted(by_date):
        if state.get("season") != season:
            state = {"season": season, "pz": defaultdict(lambda: defaultdict(float)), "pfga": defaultdict(int),
                     "pg": defaultdict(int), "ppts": defaultdict(float), "tz": defaultdict(lambda: defaultdict(float)),
                     "tg": defaultdict(int), "lz": defaultdict(float), "lg": 0}
        st = state
        lg_z = {z: st["lz"][z] / st["lg"] for z in ZONES} if st["lg"] else None
        for g in by_date[(season, d)]:
            _d, _s, h, a = games[g]
            for p, (tm, mn, pts, fga) in box[g].items():
                if not mn or (d, p) not in lines or lg_z is None:
                    continue
                opp = a if tm == h else h
                if st["pg"][p] < MIN_GAMES or st["pfga"][p] < MIN_FGA or st["tg"][opp] < MIN_TEAM_GAMES:
                    continue
                tot = sum(st["pz"][p].values())
                if tot <= 0:
                    continue
                share = {z: st["pz"][p][z] / tot for z in ZONES}
                allow = {z: (st["tz"][opp][z] / st["tg"][opp]) / lg_z[z] if lg_z[z] else 1.0 for z in ZONES}
                ins_allow = (sum(st["tz"][opp][z] for z in INSIDE) / st["tg"][opp]) / sum(lg_z[z] for z in INSIDE)
                line, price = lines[(d, p)]
                rows.append({"season": season, "date": d, "pid": p, "line": line, "price": price, "actual": pts,
                             "fga": fga, "avg_pts": st["ppts"][p] / st["pg"][p], "avg_fga": st["pfga"][p] / st["pg"][p],
                             "inside": sum(share[z] for z in INSIDE) * (ins_allow - 1.0),
                             "zone": sum(share[z] * (allow[z] - 1.0) for z in ZONES)})
        for g in by_date[(season, d)]:                    # now the date's games join the state
            _d, _s, h, a = games[g]
            team_of = {p: v[0] for p, v in box[g].items()}
            for p, z, pts in shots[g]:
                tm = team_of.get(p)
                if tm is None:
                    continue
                opp = a if tm == h else h
                st["pz"][p][z] += pts
                st["tz"][opp][z] += pts
                st["lz"][z] += pts
            for p, tm in team_of.items():
                mn, pts, fga = box[g][p][1:]
                if mn:
                    st["pg"][p] += 1
                    st["pfga"][p] += fga or 0
                    st["ppts"][p] += pts or 0
            st["tg"][h] += 1
            st["tg"][a] += 1
            st["lg"] += 2
    return rows


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def boot_spearman(rows, key, target, reps=2000, seed=7):
    by = defaultdict(list)
    for r in rows:
        by[r["date"]].append(r)
    ds = sorted(by)
    rng = np.random.default_rng(seed)
    point = spearman([r[key] for r in rows], [target(r) for r in rows])
    vals = []
    for _ in range(reps):
        pick = [r for i in rng.integers(0, len(ds), len(ds)) for r in by[ds[i]]]
        vals.append(spearman([r[key] for r in pick], [target(r) for r in pick]))
    return {"rho": round(point, 4), "lo": round(float(np.percentile(vals, 2.5)), 4), "hi": round(float(np.percentile(vals, 97.5)), 4)}


def units(r):
    return (r["price"] - 1) if r["actual"] > r["line"] else 0.0 if r["actual"] == r["line"] else -1.0


def analyze(rows, key):
    cut = np.percentile([r[key] for r in rows if r["season"] == "2023-24"], [100 / 3, 200 / 3])
    terc = lambda v: "bottom" if v <= cut[0] else "top" if v > cut[1] else "middle"
    out = {"cuts": [round(float(c), 4) for c in cut], "by_season": {}}
    for s in ("2023-24", "2024-25"):
        rs = [r for r in rows if r["season"] == s]
        t = {}
        for lab in ("bottom", "middle", "top"):
            k = [r for r in rs if terc(r[key]) == lab]
            np_ = [r for r in k if r["actual"] != r["line"]]
            t[lab] = {"n": len(k), "over_rate": round(float(np.mean([r["actual"] > r["line"] for r in np_])), 4) if np_ else None,
                      "over_roi": round(float(np.mean([units(r) for r in k])), 4) if k else None}
        t["top_minus_bottom_roi"] = round(t["top"]["over_roi"] - t["bottom"]["over_roi"], 4)
        out["by_season"][s] = t
    out["spearman_actual_minus_line"] = boot_spearman(rows, key, lambda r: r["actual"] - r["line"])
    out["volume"] = {name: round(spearman([r[key] for r in rows], [f(r) for r in rows]), 4) for name, f in (
        ("fga_minus_avg", lambda r: r["fga"] - r["avg_fga"]), ("points_minus_avg", lambda r: r["actual"] - r["avg_pts"]),
        ("line_minus_avg", lambda r: r["line"] - r["avg_pts"]))}
    out["passes"] = (all(out["by_season"][s]["top_minus_bottom_roi"] > 0 for s in ("2023-24", "2024-25"))
                     and out["spearman_actual_minus_line"]["lo"] > 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", required=True)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = build(a.shots, a.data)
    res = {"rows": len(rows), "by_season_n": {s: sum(r["season"] == s for r in rows) for s in ("2023-24", "2024-25")},
           "INSIDE (primary)": analyze(rows, "inside"), "ZONE (secondary)": analyze(rows, "zone")}
    res["verdict"] = ("PASS: add ZONE_MATCHUP to the side-by-side" if res["INSIDE (primary)"]["passes"]
                      else "FAIL: no rule")
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
