#!/usr/bin/env python3
"""MINUTES (NBA_MINUTES_PREREG.md): the minutes of the player who steps into the starting lineup when a usual starter is
out (target A), and of the bench player who takes over his bench minutes (target B), with NBA.com's historical lineups.

Baselines L5 (his last 5 games) and V3 (ROLE1 v3, the live ROLE_OPEN model); a simple blend per target; a fitted
gradient-boosted model per target. Fit on 2023-24, tested on 2024-25 and 2025-26, under confirmed starters and under
the page's projected five. Then bets at 2024-25 tip lines (2023-24 in-sample) against the live STEP rule.

    python3 nba_minutes.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import zlib
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_boost as BOOST
import nba_role as ROLE

HERE = Path(__file__).resolve().parent
GAMELOGS = HERE / ".projdata" / "nba_gamelogs.sqlite"
RAW = HERE / ".projdata" / "nba_stats_raw.sqlite"
ODDS = Path.home() / "nba-engine" / "basketball_nba_odds_hist.sqlite"
FIT, TESTS = "2023-24", ("2024-25", "2025-26")
PREV = {"2023-24": "2022-23", "2024-25": "2023-24", "2025-26": "2024-25"}
K_BLEND, K_RATE, SPOT_MAX, MIN_SPLIT = 3.0, 150.0, 3, 3
KNOW = ("confirmed", "projected")
FEATURES = ("l5", "season_mpg", "v3", "starts_min", "n_starts", "with_s_min", "n_with_s", "x_mpg", "same_letter",
            "rest", "game_index", "rotation", "n_out")
STATS = ("min", "fga", "fta", "fg3a", "fg3m", "reb", "ast", "pts")


def lineups(raw_db=RAW):
    """{(date, team): frozenset(starters)} from NBA.com's daily lineups (the five with a position)."""
    c = sqlite3.connect(f"file:{raw_db}?mode=ro", uri=True)
    out = {}
    for key, body in c.execute("SELECT key, body FROM raw WHERE kind = 'lineups' AND status = 200"):
        try:
            j = json.loads(zlib.decompress(body))
        except (zlib.error, TypeError, ValueError):
            j = json.loads(body)
        for g in j.get("games", []):
            for side in ("homeTeam", "awayTeam"):
                t = g.get(side) or {}
                five = frozenset(int(p["personId"]) for p in t.get("players") or [] if p.get("position"))
                if t.get("teamAbbreviation") and five:
                    out[(key, t["teamAbbreviation"])] = five
    return out


def load(gamelogs_db=GAMELOGS, raw_db=RAW):
    """({season: [row]}, {pid: position}): logs_full rows with a starter flag from the lineups (None without one)."""
    five = lineups(raw_db)
    g = sqlite3.connect(f"file:{gamelogs_db}?mode=ro", uri=True)
    rows = defaultdict(list)
    for s, gid, d, tm, pid, mn, fga, fta, fg3a, fg3m, reb, ast, pts in g.execute(
            "SELECT season, game_id, date, team, player_id, min, fga, fta, fg3a, fg3m, reb, ast, pts FROM logs_full"):
        f = five.get((d, tm))
        rows[s].append({"season": s, "gid": gid, "date": d, "team": tm, "pid": pid, "min": mn or 0.0, "fga": fga, "fta": fta,
                        "fg3a": fg3a, "fg3m": fg3m, "reb": reb, "ast": ast, "pts": pts,
                        "starter": (1 if pid in f else 0) if f is not None else None})
    pos = dict(g.execute("SELECT player_id, position FROM positions"))
    return rows, pos, five


class Season:
    """One season's spots and targets."""

    def __init__(self, s, rows, pos, five):
        self.s, self.five = s, five
        groups = {p: BOOST.group(v) for p, v in pos.items()}
        self.bd = BOOST.BoostData(rows[PREV[s]] + rows[s], groups, s, pos)
        self.role = ROLE.Season(rows[s])
        self.priors = ROLE.Priors(rows[PREV[s]], groups)
        self.groups = groups
        mine = defaultdict(list)                         # pid -> his rows, any team, both seasons, by date
        for r in rows[PREV[s]] + rows[s]:
            if r["min"]:
                mine[r["pid"]].append(r)
        self.mine = {p: sorted(v, key=lambda r: (r["date"], r["gid"])) for p, v in mine.items()}
        self.v3_cache = {}

    def before(self, pid, date):
        rs = self.mine.get(pid, [])
        return rs[:bisect_left([r["date"] for r in rs], date)]

    def v3(self, team, date, out_all):
        k = (team, date)
        if k not in self.v3_cache:
            absent = set(self.role.absences(team, date, set(out_all)))
            active = self.role.roster(team, date) - set(out_all)
            self.v3_cache[k] = ROLE.project(self.role, self.priors, self.groups, team, date, active, absent, mode="v3")
        return self.v3_cache[k]

    def pickup(self, team, date, s_, five, out_all):
        """Target B for new starter S: the bench player whose minutes rose most in past team games S started (vs games S
        came off the bench), 3+ of each; else the bench player sharing a letter with S with the most minutes over the
        team's last 10 games. -> (pid, how, mean when S started, n) or None."""
        bd = self.bd
        prior = bd.before(team, date)
        bench = bd.roster(team, date) - set(out_all) - set(five)
        best = None
        for r in sorted(bench):
            on = [b[r]["min"] for _d, _g, _s, b in prior if s_ in b and b[s_]["min"] and b[s_].get("starter") == 1
                  and r in b and b[r]["min"]]
            off = [b[r]["min"] for _d, _g, _s, b in prior if s_ in b and b[s_]["min"] and b[s_].get("starter") == 0
                   and r in b and b[r]["min"]]
            if len(on) >= MIN_SPLIT and len(off) >= MIN_SPLIT:
                gain = sum(on) / len(on) - sum(off) / len(off)
                if best is None or gain > best[0]:
                    best = (gain, r, sum(on) / len(on), len(on))
        if best:
            return best[1], "history", best[2], best[3]
        last10 = prior[-10:]
        mins = {r: sum(b[r]["min"] for _d, _g, _s, b in last10 if r in b) for r in bench if bd.letters(r) & bd.letters(s_)}
        if not mins:
            return None
        r = max(sorted(mins), key=lambda q: mins[q])
        on = [b[r]["min"] for _d, _g, _s, b in prior if s_ in b and b[s_]["min"] and b[s_].get("starter") == 1 and r in b and b[r]["min"]]
        return r, "position", (sum(on) / len(on) if on else None), len(on)

    def features(self, p, x, team, date, out_all, with_s=None):
        bd = self.bd
        mine = self.before(p, date)
        team_g = [r for r in mine if r["team"] == team]
        l5 = team_g[-5:]
        this = [r["min"] for r in mine if r["season"] == self.s]
        last = [r["min"] for r in mine if r["season"] != self.s]
        starts = [r for r in mine if r.get("starter") == 1][-10:]
        prior = bd.before(team, date)
        rot = defaultdict(float)
        for _d, _g, _s, b in prior[-5:]:
            for q, r in b.items():
                rot[q] += r["min"] / 5
        xpg = bd.per_game(x, team, date)
        rest = None
        if mine:
            from datetime import date as D_
            rest = min(4, (D_.fromisoformat(date) - D_.fromisoformat(mine[-1]["date"])).days)
        return {"l5": sum(r["min"] for r in l5) / len(l5) if l5 else np.nan,
                "season_mpg": (sum(this) / len(this)) if this else (sum(last) / len(last) if last else np.nan),
                "starts_min": sum(r["min"] for r in starts) / len(starts) if starts else np.nan, "n_starts": len(starts),
                "with_s_min": with_s[0] if with_s and with_s[0] is not None else np.nan,
                "n_with_s": with_s[1] if with_s else 0,
                "x_mpg": xpg["min"] if xpg else np.nan, "same_letter": float(bool(bd.letters(p) & bd.letters(x))),
                "rest": rest if rest is not None else np.nan,
                "game_index": sum(1 for _d, _g, s, _b in prior if s == self.s),
                "rotation": sum(1 for v in rot.values() if v >= 10), "n_out": len(set(out_all) & (bd.usual_five(team, date) or set()))}


def spots(season):
    """Yield one target row per (team game, missing usual starter X, lineup knowledge, target)."""
    bd, s = season.bd, season.s
    for team, games in sorted(bd.games.items()):
        for d, gid, gs, box in games:
            if gs != s:
                continue
            usual = bd.usual_five(team, d)
            if not usual:
                continue
            played = {p for p, r in box.items() if r["min"]}
            on = bd.on_team_tonight(team, d)
            out_all = (on - played) & (bd.roster(team, d) | usual)
            xs = {x: bd.absence_n(x, team, d) for x in usual & out_all}
            if not xs:
                continue
            confirmed = season.five.get((d, team))
            v3 = None
            for know in KNOW:
                if know == "confirmed" and not confirmed:
                    continue
                five, pairs = bd.tonight(team, d, out_all, confirmed if know == "confirmed" else None)
                for s_, x in sorted(pairs.items()):
                    if x not in xs:
                        continue
                    v3 = v3 if v3 is not None else season.v3(team, d, out_all)
                    base = {"season": s, "date": d, "team": team, "gid": gid, "x": x, "n": xs[x], "know": know}
                    actual = lambda p: box[p]["min"] if p in box else 0.0
                    f = season.features(s_, x, team, d, out_all)
                    yield {**base, "target": "A", "pid": s_, "actual": actual(s_), "v3": v3.get(s_, {}).get("min", np.nan),
                           **f}
                    pk = season.pickup(team, d, s_, five, out_all)
                    if pk:
                        r, how, on_mean, n_on = pk
                        fb = season.features(r, x, team, d, out_all, (on_mean, n_on))
                        yield {**base, "target": "B", "pid": r, "how": how, "step_in": s_, "actual": actual(r),
                               "v3": v3.get(r, {}).get("min", np.nan), **fb}


def blend(row):
    """The simple blend (NBA_MINUTES_PREREG.md): A from his last 10 starts, B from his games when S started, w = n/(n+3)."""
    v3 = row["v3"]
    if row["target"] == "A":
        m, n = row["starts_min"], row["n_starts"]
    else:
        m, n = row["with_s_min"], row["n_with_s"]
    if n and not np.isnan(m):
        w = n / (n + K_BLEND)
        return w * m + (1 - w) * v3
    return v3


def score(rows, pred):
    e = np.array([pred(r) - r["actual"] for r in rows])
    return {"n": len(rows), "mae": round(float(np.mean(np.abs(e))), 3), "bias": round(float(np.mean(e)), 3)}


def evaluate(all_rows):
    from sklearn.ensemble import HistGradientBoostingRegressor
    res, models = {}, {}
    usable = [r for r in all_rows if not np.isnan(r["v3"]) and not np.isnan(r["l5"])]
    for tgt in ("A", "B"):
        for know in KNOW:
            fit = [r for r in usable if r["season"] == FIT and r["target"] == tgt and r["know"] == know and r["n"] <= SPOT_MAX]
            if len(fit) < 50:
                continue
            m = HistGradientBoostingRegressor(random_state=0)
            m.fit(np.array([[r[f] for f in FEATURES] for r in fit], dtype=float),
                  np.array([r["actual"] for r in fit]))
            models[(tgt, know)] = m
            for r in usable:
                if r["target"] == tgt and r["know"] == know:
                    r["fitted"] = float(m.predict(np.array([[r[f] for f in FEATURES]], dtype=float))[0])
            out = {}
            for s in (FIT,) + TESTS:
                rs = [r for r in usable if r["season"] == s and r["target"] == tgt and r["know"] == know and r["n"] <= SPOT_MAX]
                rs_all = [r for r in usable if r["season"] == s and r["target"] == tgt and r["know"] == know]
                out[s] = {"L5": score(rs, lambda r: r["l5"]), "V3": score(rs, lambda r: r["v3"]), "blend": score(rs, blend),
                          "fitted": score(rs, lambda r: r["fitted"]),
                          "all absence games, blend": score(rs_all, blend), "actual mean": round(float(np.mean([r["actual"] for r in rs])), 2),
                          "played 0": sum(r["actual"] == 0 for r in rs)}
            ok = {name: all(out[s][name]["mae"] < min(out[s]["L5"]["mae"], out[s]["V3"]["mae"]) for s in TESTS) for name in ("blend", "fitted")}
            keep_fitted = ok["fitted"] and all(out[s]["fitted"]["mae"] <= out[s]["blend"]["mae"] - 0.25 for s in TESTS)
            out["pass"] = ok
            out["model"] = "fitted" if keep_fitted else "blend" if ok["blend"] else ("fitted" if ok["fitted"] else None)
            res[f"{tgt} {know}"] = out
    return res, usable


# ── bets ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def rate(season, p, date):
    """{stat: per minute}, this season's games before the date with last season's rate worth 150 minutes (ROLE1)."""
    mine = season.before(p, date)
    this = [r for r in mine if r["season"] == season.s]
    last = [r for r in mine if r["season"] != season.s]
    tm, lm = sum(r["min"] for r in this), sum(r["min"] for r in last)
    if tm + lm == 0:
        return None
    out = {}
    for s in ("pts", "reb", "ast", "fg3m"):
        lr = sum(r[s] or 0 for r in last) / lm if lm else None
        out[s] = (sum(r[s] or 0 for r in this) + lr * K_RATE) / (tm + K_RATE) if lr is not None else sum(r[s] or 0 for r in this) / tm
    return out


def bets(seasons, usable, choice, lines):
    """Flags from the chosen minutes model (confirmed starters) vs the live STEP rule on the same spots."""
    flags, step = [], []
    pick = {"blend": blend, "fitted": lambda r: r.get("fitted", np.nan)}
    seen = set()
    for r in usable:
        if r["know"] != "confirmed" or r["n"] > SPOT_MAX or r["season"] not in ("2023-24", "2024-25"):
            continue
        model = choice.get(f"{r['target']} confirmed")
        if not model:
            continue
        season = seasons[r["season"]]
        m = pick[model](r)
        rt = rate(season, r["pid"], r["date"])
        if rt is None or np.isnan(m):
            continue
        rel = season.bd.relevant(r["x"], r["team"], r["date"])
        for mk, parts in BOOST.PARTS.items():
            ln = lines.get((r["date"], r["pid"], mk))
            if not ln or (r["date"], r["pid"], mk) in seen:
                continue
            line, over, nv = ln
            if r["target"] == "A" and not any(rel[s] for s in parts):
                continue
            proj = m * sum(rt[s] for s in parts)
            if proj >= BOOST.PROJ_AT * line and over >= BOOST.PRICE_MIN - 1e-9:
                box = next(b for d, g, s, b in season.bd.games[r["team"]] if d == r["date"])
                if r["pid"] not in box or not box[r["pid"]]["min"]:
                    continue                             # did not play: void
                seen.add((r["date"], r["pid"], mk))
                act = BOOST.stat_of(box[r["pid"]], mk)
                flags.append({"season": r["season"], "target": r["target"], "date": r["date"], "pid": r["pid"], "market": mk,
                              "line": line, "price": over, "nv": nv, "proj": proj, "proj_min": m, "actual": act,
                              "u": (over - 1) if act > line else (0.0 if act == line else -1.0)})
    done = set()
    for r in usable:                                     # the live STEP rule, confirmed starters as its step-ins
        if r["know"] != "confirmed" or r["target"] != "A" or r["n"] > SPOT_MAX or r["season"] not in ("2023-24", "2024-25"):
            continue
        season, k = seasons[r["season"]], (r["date"], r["pid"])
        if k in done:
            continue
        done.add(k)
        box = next(b for d, g, s, b in season.bd.games[r["team"]] if d == r["date"])
        played = {p for p, x in box.items() if x["min"]}
        out_all = (season.bd.on_team_tonight(r["team"], r["date"]) - played) & (season.bd.roster(r["team"], r["date"]) |
                                                                                 season.bd.usual_five(r["team"], r["date"]))
        for mk in BOOST.PARTS:
            ln = lines.get((r["date"], r["pid"], mk))
            if not ln or r["pid"] not in played:
                continue
            f = BOOST.boost_eval(season.bd, r["date"], r["team"], r["pid"], mk, ln[0], ln[1], out_all, season.five.get((r["date"], r["team"])))
            if f and BOOST.kind_of(f) == "step":
                act = BOOST.stat_of(box[r["pid"]], mk)
                step.append({"season": r["season"], "date": r["date"], "pid": r["pid"], "market": mk, "line": ln[0], "price": ln[1],
                             "nv": ln[2], "actual": act, "u": (ln[1] - 1) if act > ln[0] else (0.0 if act == ln[0] else -1.0)})
    return flags, step


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    rows, pos, five = load()
    seasons, all_rows = {}, []
    for s in (FIT,) + TESTS:
        seasons[s] = Season(s, rows, pos, five)
        all_rows += list(spots(seasons[s]))
    res, usable = evaluate(all_rows)
    choice = {k: v["model"] for k, v in res.items()}
    lines = BOOST.tip_lines(GAMELOGS, ODDS)
    flags, step = bets(seasons, usable, choice, lines)
    res["bets"] = {s: {"new model, A": BOOST.summ([f for f in flags if f["season"] == s and f["target"] == "A"]),
                       "new model, B": BOOST.summ([f for f in flags if f["season"] == s and f["target"] == "B"]),
                       "new model, all": BOOST.summ([f for f in flags if f["season"] == s], boot=2000),
                       "live STEP": BOOST.summ([f for f in step if f["season"] == s], boot=2000)} for s in ("2023-24", "2024-25")}
    res["bets"]["pass"] = (res["bets"]["2024-25"]["new model, all"].get("n", 0) >= 100 and
                           res["bets"]["2024-25"]["new model, all"].get("roi", -1) > 0 and
                           res["bets"]["2024-25"]["new model, all"].get("roi", -1) > res["bets"]["2024-25"]["live STEP"].get("roi", -1))
    res["rows"] = {s: {t: sum(1 for r in all_rows if r["season"] == s and r["target"] == t and r["know"] == "confirmed") for t in "AB"}
                   for s in (FIT,) + TESTS}
    print(json.dumps(res, indent=1, default=str))
    if a.json:
        Path(a.json).write_text(json.dumps({"result": res, "flags": flags, "step": step}, indent=1, default=str))


if __name__ == "__main__":
    main()
