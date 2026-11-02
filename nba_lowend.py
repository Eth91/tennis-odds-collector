#!/usr/bin/env python3
"""LOWEND (NBA_LOWEND_PREREG.md): the over only when the low end of the projection clears the line.

Volume = minutes x his per-minute rate; low end = volume - k x the projection's 2023-24 error (k = 1 and 0.5); points from
the low-end FGA / 3PA / FTA at his percentages in past games of similar volume. Two populations: players stepping into
the lineup (STEP, confirmed starters) and every player with a line. 2023-24 and 2024-25 tip lines.

    python3 nba_lowend.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_boost as BOOST
import nba_minutes as M

SEASONS = ("2023-24", "2024-25")
KS = (1.0, 0.5)
MARKETS = ("points", "threes", "pts_reb", "pts_ast", "pra")
ERR_STATS = ("min", "fga", "fg3a", "fta", "reb", "ast")
MIN_GAMES, MIN_ATT = 5, 10
LEAGUE = {"p2": 0.52, "p3": 0.36, "ft": 0.78}


def load(gamelogs_db=M.GAMELOGS, raw_db=M.RAW):
    """nba_minutes.load's rows, plus FGM and FTM for the percentages."""
    rows, pos, five = M.load(gamelogs_db, raw_db)
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    extra = {(gid, pid): (fgm, ftm) for gid, pid, fgm, ftm in g.execute("SELECT game_id, player_id, fgm, ftm FROM logs_full")}
    for rs in rows.values():
        for r in rs:
            r["fgm"], r["ftm"] = extra.get((r["gid"], r["pid"]), (None, None))
    return rows, pos, five


def pct(games, lo, err, att, made, key, vol=None):
    """His percentage (made / att) over past games whose volume (vol(r), default att(r)) is within err of lo: 5+ games
    and 10+ attempts, else over all his games, else the league's."""
    vol = vol or att
    near = [r for r in games if abs(vol(r) - lo) <= err]
    a, m = sum(att(r) for r in near), sum(made(r) for r in near)
    if len(near) >= MIN_GAMES and a >= MIN_ATT:
        return m / a
    a, m = sum(att(r) for r in games), sum(made(r) for r in games)
    return m / a if a else LEAGUE[key]


def low_end(games, vol, minutes, rt, err, k):
    """{market: low-end stat} from the volume projection less k x its error (rule 4) and similar-volume efficiency."""
    fga = max(0.0, vol["fga"] - k * err["fga"])
    fg3a = min(fga, max(0.0, vol["fg3a"] - k * err["fg3a"]))
    fta = max(0.0, vol["fta"] - k * err["fta"])
    p2 = pct(games, fga, err["fga"], lambda r: (r["fga"] or 0) - (r["fg3a"] or 0),
             lambda r: (r["fgm"] or 0) - (r["fg3m"] or 0), "p2", vol=lambda r: r["fga"] or 0)   # games of similar FGA
    p3 = pct(games, fg3a, err["fg3a"], lambda r: r["fg3a"] or 0, lambda r: r["fg3m"] or 0, "p3")
    ft = pct(games, fta, err["fta"], lambda r: r["fta"] or 0, lambda r: r["ftm"] or 0, "ft")
    pts = 2 * (fga - fg3a) * p2 + 3 * fg3a * p3 + fta * ft
    m_lo = max(0.0, minutes - k * err["min"])
    reb, ast = m_lo * rt["reb"], m_lo * rt["ast"]
    return {"points": pts, "threes": fg3a * p3, "pts_reb": pts + reb, "pts_ast": pts + ast, "pra": pts + reb + ast,
            "_fga": fga, "_fg3a": fg3a, "_fta": fta}


def projections(season, lines):
    """[{pop, season, date, team, pid, min, vol, rt, box}] for both populations; the box is tonight's (grading only)."""
    out, bd, s = [], season.bd, season.s
    has_line = {(d, p) for (d, p, mk) in lines if mk in MARKETS}
    for r in M.spots(season):                            # STEP: confirmed new starters, absence games 1-3
        if r["know"] != "confirmed" or r["target"] != "A" or r["n"] > M.SPOT_MAX or np.isnan(r["v3"]):
            continue
        if (r["date"], r["pid"]) in has_line:
            out.append({"pop": "STEP", "date": r["date"], "team": r["team"], "pid": r["pid"], "min": M.blend(r)})
    for team, games in sorted(bd.games.items()):         # every player with a line: ROLE1 v3's minutes
        for d, gid, gs, box in games:
            if gs != s:
                continue
            played = {p for p, x in box.items() if x["min"]}
            usual = bd.usual_five(team, d) or bd.starters(team, d)
            out_all = (bd.on_team_tonight(team, d) - played) & (bd.roster(team, d) | usual)
            todo = [p for p in played if (d, p) in has_line]
            if not todo:
                continue
            v3 = season.v3(team, d, out_all)
            for p in todo:
                if p in v3:
                    out.append({"pop": "ALL", "date": d, "team": team, "pid": p, "min": v3[p]["min"]})
    boxes = {(d, p): x for team, games in bd.games.items() for d, gid, gs, b in games if gs == s for p, x in b.items()}
    keep = []
    for x in out:
        b = boxes.get((x["date"], x["pid"]))
        rt = BOOST.rates(bd, x["pid"], x["date"])
        if not b or not b["min"] or not rt:
            continue                                     # did not play (void) or no history
        x.update(season=s, box=b, rt=rt, vol={st: x["min"] * rt[st] for st in ("fga", "fg3a", "fta", "reb", "ast")})
        keep.append(x)
    return keep


def errors(rows):
    """{pop: {stat: MAE}} on the given rows (2023-24): minutes and minutes x rate against tonight's box."""
    out = {}
    for pop in ("STEP", "ALL"):
        rs = [r for r in rows if r["pop"] == pop]
        e = {"min": np.mean([abs(r["box"]["min"] - r["min"]) for r in rs])}
        for st in ("fga", "fg3a", "fta", "reb", "ast"):
            e[st] = np.mean([abs((r["box"][st] or 0) - r["vol"][st]) for r in rs])
        out[pop] = {k: round(float(v), 3) for k, v in e.items()}
    return out


def flags(rows, season_of_rows, err, lines):
    out = []
    for r in rows:
        games = season_of_rows[r["season"]].bd.his(r["pid"], r["date"])
        for k in KS:
            lo = low_end(games, r["vol"], r["min"], r["rt"], err[r["pop"]], k)
            for mk in MARKETS:
                ln = lines.get((r["date"], r["pid"], mk))
                if not ln:
                    continue
                line, over, nv = ln
                if lo[mk] > line and over >= BOOST.PRICE_MIN - 1e-9:
                    act = BOOST.stat_of(r["box"], mk)
                    out.append({"pop": r["pop"], "k": k, "season": r["season"], "date": r["date"], "pid": r["pid"], "market": mk,
                                "line": line, "price": over, "nv": nv, "lo": lo[mk], "actual": act,
                                "u": (over - 1) if act > line else (0.0 if act == line else -1.0)})
    return out


def report(fl, err):
    res = {"errors (2023-24)": err}
    for pop in ("STEP", "ALL"):
        for k in KS:
            key = f"{pop} k={k:g}"
            res[key] = {}
            for s in SEASONS:
                fs = [f for f in fl if f["pop"] == pop and f["k"] == k and f["season"] == s]
                res[key][s] = {"all": BOOST.summ(fs, boot=2000),
                               "gap (low end - line)": round(float(np.mean([f["lo"] - f["line"] for f in fs])), 2) if fs else None,
                               "market": {m: BOOST.summ([f for f in fs if f["market"] == m]) for m in MARKETS}}
            res[key]["pass"] = all(res[key][s]["all"].get("n", 0) >= 100 and res[key][s]["all"].get("roi", -1) > 0 for s in SEASONS)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    rows, pos, five = load()
    lines = BOOST.tip_lines(M.GAMELOGS, M.ODDS)
    seasons, proj = {}, []
    for s in SEASONS:
        seasons[s] = M.Season(s, rows, pos, five)
        proj += projections(seasons[s], lines)
    err = errors([r for r in proj if r["season"] == "2023-24"])
    fl = flags(proj, seasons, err, lines)
    res = report(fl, err)
    res["rows"] = {f"{p} {s}": sum(1 for r in proj if r["pop"] == p and r["season"] == s) for p in ("STEP", "ALL") for s in SEASONS}
    print(json.dumps(res, indent=1, default=str))
    if a.json:
        Path(a.json).write_text(json.dumps({"result": res, "flags": fl}, indent=1, default=str))


if __name__ == "__main__":
    main()
