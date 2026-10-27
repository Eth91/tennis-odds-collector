#!/usr/bin/env python3
"""ML1 (NBA_ML1_PREREG.md): a flagging model learned from the point-in-time logs.

The Tracker rides the replay (nba_replay.run_day): at each checkpoint it computes, for every prop and book, the
registered features from what was known then. Built once into a dataset with the target (EV at FanDuel's close,
the side-by-side's CLV) and the result; fit by ridge, validated leave-one-day-out. The same Tracker scores live
rows if ML1 is registered, so training and forward features cannot drift apart.

    python3 nba_ml1.py --build OUT.json.gz --from 2026-10-22 --to 2026-10-26   # on the VM (the logs live there)
    python3 nba_ml1.py --validate DATA.json.gz [--json OUT]
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
from collections import defaultdict

import numpy as np

import nba_proj_data as PD
import nba_proj_eval as E
import nba_replay as RP

CHECKPOINTS = (360, 180, 120, 60, 30)                    # minutes before tip
NEWS_WINDOW, NEWS_CAP = 10, 1440.0
ALPHAS = (1.0, 10.0, 100.0, 1000.0, 10000.0)
FLAG_AT, LAG_AT, MIN_FLAGS = 0.02, 0.03, 100
REG_MIN = 20.0
FEATURES = (["is_dk", "is_over", "log_min_to_tip"] + [f"m_{m}" for m in RP.MARKETS]
            + ["ev_fd", "ev_fd_missing", "dk_minus_fd", "other_line_gap", "line_move_open", "line_move_60",
               "fd_q_drift", "team_news_min", "opp_news_min", "team_out", "opp_out", "own_questionable",
               "own_probable", "min10", "min_trend", "line_minus_avg"])
STAT_IX = {"pts": 0, "reb": 1, "ast": 2, "fg3m": 3}


class StatHistory:
    """Appearances (minutes > 0) with their stats, before any date: last season's logs and this season's box scores."""

    def __init__(self, gamelogs_db, matchup_db):
        self.apps = defaultdict(list)                    # pid -> [(date, team, min, (pts, reb, ast, fg3m))]
        g, m = PD._ro(gamelogs_db), PD._ro(matchup_db)
        if g is not None:
            for d, team, pid, mn, a, b, c, t in g.execute("SELECT date, team, player_id, min, pts, reb, ast, fg3m FROM logs WHERE min > 0"):
                self.apps[pid].append((d, team, mn, (a, b, c, t)))
        if m is not None:
            for d, team, pid, mn, a, b, c, t in m.execute("SELECT gm.date, p.team, p.pid, p.min, p.pts, p.reb, p.ast, p.fg3m FROM "
                                                          "player_games p JOIN games gm ON gm.gid = p.gid WHERE p.min > 0"):
                self.apps[pid].append((d, team, mn, (a, b, c, t)))
        for v in self.apps.values():
            v.sort()

    def before(self, pid, date):
        return [a for a in self.apps.get(pid, ()) if a[0] < date]


def market_value(stats, market):
    return sum(stats[STAT_IX[c]] for c in PD.MARKET_PARTS[market])


class Tracker:
    """Stateful, look-ahead-free feature builder. In collect mode it records every row; with `score` it returns
    signals where score(row) >= FLAG_AT (the ML1 rule)."""
    name = "ML1_COLLECT"
    kind = "replay"

    def __init__(self, stats, score=None, name=None):
        self.stats, self.score = stats, score
        self.name = name or self.name
        self.rows = []

    def start_day(self, v):
        self.first = {}                                  # (g, p, mk, book) -> (t, board copy) at first sight with a main
        self.hist = defaultdict(list)                    # (g, p, mk, book) -> [(t, main line)] on each change
        self.done = defaultdict(set)                     # gid -> checkpoints taken
        self.pending = []                                # (report time, gid)
        self.news_at = {}                                # team -> time of the latest regular newly Out/Doubtful
        self.team_out = defaultdict(dict)                # team -> {pid: latest status}
        self.cache = {}

    def _track(self, v):
        for k in v.changed:
            m = RP.main_of(v.board(*k))
            if m is None:
                continue
            if k not in self.first:
                self.first[k] = (v.t, dict(v.board(*k)))
            if not self.hist[k] or self.hist[k][-1][1] != m[0]:
                self.hist[k].append((v.t, m[0]))

    def on_report(self, v, t, rows, prev, seen_before):
        import nba_sxs_rules as SR                       # lazy: SR imports this module for the ML1 rule
        self._track(v)
        for team, pid, st in rows:
            self.team_out[team][pid] = st
        for x, team, g in SR.newly_out(v, t, rows, seen_before, prev):
            self.news_at[team] = t
            self.pending.append((t, g))
        return ()

    def on_tick(self, v, gid, minutes):
        self._track(v)
        return ()

    def on_obs(self, v, book, seen):
        self._track(v)
        if book != "fd":
            return ()
        games, out = v.games(), []
        fire = {}
        for g in seen:
            tip = games[g]["tip"]
            if v.t > RP.minus(tip, 5):
                continue
            crossed = [c for c in CHECKPOINTS if c not in self.done[g] and v.t >= RP.minus(tip, c)]
            if crossed:
                self.done[g].update(crossed)
                fire[g] = f"cp{min(crossed)}"
        keep = []
        for P, g in self.pending:
            if RP.minus(v.t, NEWS_WINDOW) > P:
                continue
            if g in seen and v.t <= RP.minus(games[g]["tip"], 5):
                fire[g] = "news"
            elif g not in seen:
                keep.append((P, g))
        self.pending = keep
        for g, label in sorted(fire.items()):
            out += self._rows(v, g, label)
        return out

    def _player(self, v, p, mk):
        key = (p, mk)
        if key not in self.cache:
            a = self.stats.before(p, v.date)
            l10, l3 = a[-10:], a[-3:]
            self.cache[key] = (sum(x[2] for x in l10) / len(l10) if l10 else None,
                               (sum(x[2] for x in l3) / len(l3) - sum(x[2] for x in l10) / len(l10)) if l10 else None,
                               sum(market_value(x[3], mk) for x in l10) / len(l10) if l10 else None,
                               a[-1][1] if a else None)
        return self.cache[key]

    def _regulars_out(self, v, team):
        key = ("out", team, v.t)
        if key not in self.cache:
            n = 0
            for pid, st in self.team_out.get(team, {}).items():
                if st in RP.OUTS:
                    if ("l10", pid) not in self.cache:
                        self.cache[("l10", pid)] = v.last10_min(pid)
                    mn, k = self.cache[("l10", pid)]
                    n += bool(k >= 3 and mn >= REG_MIN)
            self.cache[key] = n
        return self.cache[key]

    def features(self, v, g, p, mk, book, side, line, odds):
        sgn = 1.0 if side == "over" else -1.0
        tip = v.games()[g]["tip"]
        fd, dk = v.board(g, p, mk, "fd"), v.board(g, p, mk, "dk")
        q_fd, q_dk = RP.q_close(fd, side, line), RP.q_close(dk, side, line)
        other = RP.main_of(dk if book == "fd" else fd)
        k = (g, p, mk, book)
        first_t, first_b = self.first.get(k, (None, None))
        open_m = RP.main_of(first_b) if first_b else None
        h = self.hist.get(k, [])
        l60 = next((ln for t, ln in reversed(h) if t <= RP.minus(v.t, 60)), h[0][1] if h else None)
        fd_first = self.first.get((g, p, mk, "fd"), (None, None))[1]
        q_fd0 = RP.q_close(fd_first, side, line) if fd_first else None
        min10, trend, avg, team = self._player(v, p, mk)
        home, away = v.games()[g]["home"], v.games()[g]["away"]
        opp = away if team == home else home if team == away else None
        since = lambda tm: min(NEWS_CAP, (dt_min(v.t) - dt_min(self.news_at[tm]))) if tm in self.news_at else NEWS_CAP
        st = v.status(p)
        f = {"is_dk": float(book == "dk"), "is_over": float(side == "over"),
             "log_min_to_tip": math.log1p(max(0.0, dt_min(tip) - dt_min(v.t))),
             "ev_fd": (q_fd * odds - 1) if q_fd is not None else 0.0, "ev_fd_missing": float(q_fd is None),
             "dk_minus_fd": (q_dk - q_fd) if q_dk is not None and q_fd is not None else 0.0,
             "other_line_gap": (other[0] - line) * sgn if other else 0.0,
             "line_move_open": (line - open_m[0]) * sgn if open_m else 0.0,
             "line_move_60": (line - l60) * sgn if l60 is not None else 0.0,
             "fd_q_drift": (q_fd - q_fd0) if q_fd is not None and q_fd0 is not None else 0.0,
             "team_news_min": since(team), "opp_news_min": since(opp),
             "team_out": float(self._regulars_out(v, team)) if team else 0.0,
             "opp_out": float(self._regulars_out(v, opp)) if opp else 0.0,
             "own_questionable": float(st == "Questionable"), "own_probable": float(st == "Probable"),
             "min10": min10 or 0.0, "min_trend": trend or 0.0,
             "line_minus_avg": (line - avg) * sgn if avg is not None else 0.0}
        for m_ in RP.MARKETS:
            f[f"m_{m_}"] = float(mk == m_)
        return [f[n] for n in FEATURES]

    def _rows(self, v, g, label):
        out = []
        for p, mk in sorted(set(v.props(g, "fd")) | set(v.props(g, "dk"))):
            for book in ("fd", "dk"):
                m = RP.main_of(v.board(g, p, mk, book))
                if not m:
                    continue
                for side, odds in (("over", m[1]), ("under", m[2])):
                    x = self.features(v, g, p, mk, book, side, m[0], odds)
                    row = {"date": v.date, "t": v.t, "label": label, "gid": g, "pid": p, "market": mk, "book": book,
                           "side": side, "line": m[0], "odds": odds, "x": x}
                    if self.score is None:
                        self.rows.append(row)
                    else:
                        s = self.score(x)
                        if s >= FLAG_AT:
                            out.append(dict(gid=g, pid=p, market=mk, side=side, line=m[0], book=book, odds=odds,
                                            note=f"pred={s:.3f}", _s=s))
        return sorted(out, key=lambda r: -r.pop("_s"))


def dt_min(t):
    import datetime as dt
    return dt.datetime.fromisoformat(t).timestamp() / 60.0


def build(since, until, out_path, lines_db=RP.HERE / "nba_lines.sqlite", news_db=RP.HERE / "nba_news.sqlite",
          matchup_db=RP.HERE / "nba_matchup.sqlite", gamelogs_db=RP.HERE / "nba_gamelogs.sqlite"):
    hist, stats = RP.History(gamelogs_db, matchup_db), StatHistory(gamelogs_db, matchup_db)
    rows = []
    for d in RP.dates(matchup_db, lines_db, since, until):
        day = RP.Day(d, lines_db, news_db, matchup_db, hist)
        tr = Tracker(stats)
        RP.run_day(day, [tr])
        cl, box = RP.closes(day), RP.box_of(matchup_db, list(day.games))
        for r in tr.rows:
            q = RP.q_close(cl.get((r["gid"], r["pid"], r["market"])), r["side"], r["line"])
            if q is None:
                continue
            r["y"] = q * r["odds"] - 1
            mn, stt = box.get((r["gid"], r["pid"]), (None, None))
            if mn:
                a = sum(stt[c] for c in PD.MARKET_PARTS[r["market"]])
                r["profit"] = 0.0 if a == r["line"] else (r["odds"] - 1 if (a > r["line"]) == (r["side"] == "over") else -1.0)
            rows.append(r)
        print(f"{d}: {len(day.games)} games, {len(tr.rows)} rows, {sum(1 for r in tr.rows if 'y' in r)} with a close")
    with gzip.open(out_path, "wt") as fh:
        json.dump({"features": FEATURES, "rows": rows}, fh)
    return rows


# ── fitting and validation ──────────────────────────────────────────────────────────────────────────────────────
def ridge(X, y, alpha):
    """Standardize, fit with an unpenalized intercept. -> (mu, sd, w, b)."""
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    yb = y.mean()
    w = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - yb))
    return mu, sd, w, yb


def predict(model, X):
    mu, sd, w, b = model
    return ((X - mu) / sd) @ w + b


def choose_alpha(X, y, days):
    best = None
    for a in ALPHAS:
        err = []
        for d in sorted(set(days)):
            tr, te = days != d, days == d
            err.append(np.mean((predict(ridge(X[tr], y[tr], a), X[te]) - y[te]) ** 2))
        if best is None or np.mean(err) < best[1]:
            best = (a, float(np.mean(err)))
    return best[0]


def first_flags(rows, pred, at):
    """The first checkpoint where each (game, player, market, side) fires; ties go to the higher prediction."""
    best = {}
    for r, s in zip(rows, pred):
        if s < at:
            continue
        k = (r["gid"], r["pid"], r["market"], r["side"])
        if k not in best or (r["t"], -s) < (best[k][0]["t"], -best[k][1]):
            best[k] = (r, s)
    return [r for r, _ in best.values()]


def summ(flags):
    if not flags:
        return {"n": 0}
    y = [r["y"] for r in flags]
    m_, lo, hi = E.boot_ci(y, [r["date"] for r in flags], reps=4000)
    pr = [r["profit"] for r in flags if r.get("profit") is not None]
    return {"n": len(flags), "clv": round(m_, 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "roi": round(float(np.mean(pr)), 4) if pr else None, "graded": len(pr),
            "w": sum(p > 0 for p in pr), "l": sum(p < 0 for p in pr)}


def validate(data):
    rows = data["rows"]
    X = np.array([r["x"] for r in rows], float)
    y = np.array([r["y"] for r in rows], float)
    days = np.array([r["date"] for r in rows])
    res = {"rows": len(rows), "days": sorted(set(days)), "by_day": {}, "pooled": {}}
    pool = {"model": [], "dk_lag": [], "all": []}
    ev_fd = X[:, FEATURES.index("ev_fd")]
    for d in sorted(set(days)):
        tr, te = days != d, days == d
        a = choose_alpha(X[tr], y[tr], days[tr])
        model = ridge(X[tr], y[tr], a)
        held = [r for r, k in zip(rows, te) if k]
        f_model = first_flags(held, predict(model, X[te]), FLAG_AT)
        f_lag = first_flags(held, ev_fd[te], LAG_AT)
        f_all = first_flags(held, np.ones(int(te.sum())), 0.5)
        pool["model"] += f_model
        pool["dk_lag"] += f_lag
        pool["all"] += f_all
        res["by_day"][d] = {"alpha": a, "model": summ(f_model), "dk_lag": summ(f_lag), "all": summ(f_all)}
    res["pooled"] = {k: summ(v) for k, v in pool.items()}
    pm, pl = res["pooled"]["model"], res["pooled"]["dk_lag"]
    pos_days = sum(1 for d in res["by_day"].values() if d["model"].get("n") and d["model"]["clv"] > 0)
    checks = {"pooled_clv_positive": pm.get("n", 0) > 0 and pm["clv"] > 0,
              "beats_dk_lag": pm.get("n", 0) > 0 and pm["clv"] > pl.get("clv", -1e9),
              "positive_days_4_of_5": pos_days >= 4, "flags_100": pm.get("n", 0) >= MIN_FLAGS}
    res["checks"], res["positive_days"] = checks, pos_days
    res["verdict"] = "PASS: register ML1 for a forward test" if all(checks.values()) else "FAIL: no registration"
    a_all = choose_alpha(X, y, days)
    full = ridge(X, y, a_all)
    res["final"] = {"alpha": a_all, "mu": full[0].tolist(), "sd": full[1].tolist(), "w": full[2].tolist(), "b": full[3],
                    "top": sorted(zip(FEATURES, full[2].tolist()), key=lambda kv: -abs(kv[1]))[:10]}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build")
    ap.add_argument("--from", dest="since", default="2026-10-22")
    ap.add_argument("--to", dest="until", default="2026-10-26")
    ap.add_argument("--data", help="a folder holding nba_lines / nba_news / nba_matchup / nba_gamelogs .sqlite")
    ap.add_argument("--validate")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.build:
        kw = {}
        if a.data:
            from pathlib import Path
            d = Path(a.data)
            kw = {f"{k}_db": d / f"nba_{k}.sqlite" for k in ("lines", "news", "matchup", "gamelogs")}
        build(a.since, a.until, a.build, **kw)
    if a.validate:
        with gzip.open(a.validate, "rt") as fh:
            res = validate(json.load(fh))
        print(json.dumps({k: res[k] for k in ("rows", "days", "pooled", "checks", "positive_days", "verdict")}, indent=1))
        for d, v in res["by_day"].items():
            print(d, "alpha", v["alpha"], "model", v["model"], "| dk_lag", v["dk_lag"].get("clv"), v["dk_lag"].get("n"),
                  "| all", v["all"].get("clv"), v["all"].get("n"))
        print("final top features:", res["final"]["top"])
        if a.json:
            open(a.json, "w").write(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
