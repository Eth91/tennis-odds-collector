#!/usr/bin/env python3
"""The replay tool (NBA_SXS_PREREG.md): run a flagging rule over the live logs exactly as they were known.

One ET game date at a time, events in time order:
  obs     a book observed games: a full poll (cycles status ok / partial) sees every game of the day; a targeted
          poll (status 'game') sees only the games it wrote a quote for. A rule never acts on an unseen price.
  report  an official injury report was published (nba_news.snapshots, each publication a full report).
  tick    a game reached tip - 30 or tip - 5 (the board is then each book's latest observation).
Before each event every quote with seen_at <= t is applied. A rule sees a View: the boards, the reports and the
box scores from BEFORE the date - never the day's results, which only the grader reads.

    python3 nba_replay.py --rule nba_sxs_rules:NEWS_FD --from 2026-10-22 --to 2026-10-26
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_proj_data as PD
import nba_proj_eval as E
import nba_research as R

HERE = PD.HERE
MARKETS = ("points", "rebounds", "assists", "threes", "pts_reb", "pts_ast", "reb_ast", "pra")
FULL_POLL = ("ok", "partial")
OUTS = ("Out", "Doubtful")
TICKS = (30, 5)                                         # minutes before tip


def iso(t):
    """Naive UTC 'YYYY-MM-DDTHH:MM:SS' from any ISO time (an offset is converted, a naive one is taken as UTC)."""
    x = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    if x.tzinfo:
        x = x.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return x.replace(microsecond=0).isoformat()


def minus(t, minutes):
    return (dt.datetime.fromisoformat(t) - dt.timedelta(minutes=minutes)).isoformat()


def main_of(board):
    """(line, over, under) of a board's main rung (two-sided, over nearest even money), or None."""
    return R.main_of(board) if board else None


class History:
    """Every appearance (minutes > 0) before any date: last season's logs and this season's box scores."""

    def __init__(self, gamelogs_db, matchup_db):
        self.apps = defaultdict(list)                   # pid -> [(date, team, min)]
        g, m = PD._ro(gamelogs_db), PD._ro(matchup_db)
        if g is not None:
            for d, team, pid, mn in g.execute("SELECT date, team, player_id, min FROM logs WHERE min > 0"):
                self.apps[pid].append((d, team, mn))
        if m is not None:
            for d, team, pid, mn in m.execute("SELECT gm.date, p.team, p.pid, p.min FROM player_games p "
                                              "JOIN games gm ON gm.gid = p.gid WHERE p.min > 0"):
                self.apps[pid].append((d, team, mn))
        for v in self.apps.values():
            v.sort()

    def before(self, pid, date):
        return [a for a in self.apps.get(pid, ()) if a[0] < date]


class View:
    """What a rule may read at time t: boards, today's reports so far, and appearances before the date."""

    def __init__(self, day):
        self._day = day
        self.t = None
        self.date = day.date
        self.changed = set()                            # (gid, pid, market, book) changed since the previous event

    def board(self, gid, pid, market, book):
        return self._day.boards.get((gid, pid, market, book), {})

    def props(self, gid, book):
        return [(p, mk) for (g, p, mk, b) in self._day.keys_by_gid.get(gid, ()) if b == book]

    def games(self):
        return dict(self._day.games)

    def game_of(self, team):
        return next((g for g, x in self._day.games.items() if team in (x["home"], x["away"])), None)

    def status(self, pid):
        return self._day.status.get(pid)

    def team_of(self, pid):
        a = self._day.history.before(pid, self.date)
        return a[-1][1] if a else None

    def last10_min(self, pid):
        a = self._day.history.before(pid, self.date)[-10:]
        return (sum(x[2] for x in a) / len(a), len(a)) if a else (None, 0)


class Day:
    """One ET game date's logs: final games whose tip falls on the date, their quotes, polls and reports."""

    def __init__(self, date, lines_db, news_db, matchup_db, history):
        self.date, self.history = date, history
        q, n, m = PD._ro(lines_db), PD._ro(news_db), PD._ro(matchup_db)
        sched = {g: (h, a) for g, h, a in m.execute("SELECT gid, home, away FROM games WHERE date = ? AND home_pts IS NOT NULL",
                                                     (date,))}
        self.games, self.void = {}, []
        if sched:
            marks = ",".join("?" * len(sched))
            for g, tip in q.execute(f"SELECT gid, MAX(tip_utc) FROM quotes WHERE gid IN ({marks}) GROUP BY gid", list(sched)):
                if not tip:
                    continue
                if E._et_date(tip) != date:
                    self.void.append(g)                 # postponed: its quotes belong to another night
                    continue
                self.games[g] = {"tip": iso(tip), "home": sched[g][0], "away": sched[g][1]}
        gids = sorted(self.games)
        marks = ",".join("?" * len(gids))
        self.rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN ({marks}) "
                              f"AND book IN ('fd', 'dk') AND pid IS NOT NULL ORDER BY seen_at", gids).fetchall() if gids else []
        self.rows = [r for r in self.rows if r[4] in MARKETS]
        wrote = defaultdict(set)                        # (book, seen_at) -> games written
        for r in self.rows:
            wrote[(r[1], r[0])].add(r[2])
        lo = min((x["tip"] for x in self.games.values()), default=None)
        self.polls = []                                 # (ts, book, games observed)
        if gids:
            first = minus(lo, 36 * 60)
            last = max(x["tip"] for x in self.games.values())
            for ts, book, status in q.execute("SELECT ts, book, status FROM cycles WHERE ts BETWEEN ? AND ? ORDER BY ts",
                                              (first, last)):
                seen = set(gids) if status in FULL_POLL else (wrote.get((book, ts), set()) if status == "game" else set())
                if seen:
                    self.polls.append((ts, book, seen))
        self.reports = defaultdict(list)                # published_at (naive UTC) -> [(team, pid, status)]
        if n is not None:
            for pub, team, pid, st in n.execute("SELECT published_at, team, pid, status FROM snapshots WHERE game_date = ? "
                                                "AND pid IS NOT NULL", (date,)):
                self.reports[iso(pub)].append((team, int(pid), st))
        self.boards, self.keys_by_gid, self.status, self.teams_seen = {}, defaultdict(set), {}, set()

    def events(self):
        ev = [(ts, 0, "obs", (book, seen)) for ts, book, seen in self.polls]
        ev += [(pub, 1, "report", rows) for pub, rows in self.reports.items()]
        ev += [(minus(x["tip"], m), 2, "tick", (g, m)) for g, x in self.games.items() for m in TICKS]
        return sorted(ev, key=lambda e: (e[0], e[1]))


def run_day(day, rules):
    """Replay one day through `rules` (objects with start_day / on_obs / on_report / on_tick). -> [signal dicts]."""
    v = View(day)
    for r in rules:
        r.start_day(v)
    out, i, rows = [], 0, day.rows
    for t, _o, kind, payload in day.events():
        changed = set()
        while i < len(rows) and rows[i][0] <= t:
            seen_at, book, gid, pid, stat, line, side, odds = rows[i]
            k = (gid, pid, stat, book)
            b = day.boards.setdefault(k, {})
            if odds is None:
                b.pop((round(float(line), 1), side), None)
            else:
                b[(round(float(line), 1), side)] = odds
            day.keys_by_gid[gid].add(k)
            changed.add(k)
            i += 1
        v.t, v.changed = t, changed
        if kind == "report":                            # rules see the report applied, plus what came before it
            prev = {pid: day.status.get(pid) for _tm, pid, _st in payload}
            seen_before = set(day.teams_seen)
            for tm, pid, st in payload:
                day.status[pid] = st
        for r in rules:
            if kind == "obs":
                sig = r.on_obs(v, *payload)
            elif kind == "report":
                sig = r.on_report(v, t, payload, prev, seen_before)
            else:
                sig = r.on_tick(v, *payload)
            for s in sig or ():
                out.append(dict(s, rule=r.name, t=t))
        if kind == "report":
            day.teams_seen.update(tm for tm, _pid, _st in payload)
    seen, uniq = set(), []
    for s in out:                                       # one per (rule, game, player, market, side): the first
        k = (s["rule"], s["gid"], s["pid"], s["market"], s["side"])
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq


# ── grading (identical for every rule; the only reader of the day's results) ───────────────────────────────────
def closes(day):
    """{(gid, pid, market): FanDuel board} at FanDuel's last observation of the game before tip."""
    tips = {g: x["tip"] for g, x in day.games.items()}
    obs = defaultdict(list)
    for ts, book, seen in day.polls:
        if book == "fd":
            for g in seen:
                if ts < tips[g]:
                    obs[g].append(ts)
    last = {g: max(v) for g, v in obs.items()}
    st, out = defaultdict(dict), {}
    for seen_at, book, gid, pid, stat, line, side, odds in day.rows:
        if book != "fd" or gid not in last or seen_at > last[gid]:
            continue
        b = st[(gid, pid, stat)]
        if odds is None:
            b.pop((round(float(line), 1), side), None)
        else:
            b[(round(float(line), 1), side)] = odds
    for k, b in st.items():
        out[k] = dict(b)
    return out


def q_close(board, side, line):
    """FanDuel's closing no-vig probability of `side` at `line`: the rung's own no-vig if two-sided, else an over-only
    alternate de-vigged at the main rung's overround (an under = 1 - over). None when neither exists."""
    if not board:
        return None
    o, u = board.get((line, "over")), board.get((line, "under"))
    if o and u:
        p = R.no_vig(o, u)
    else:
        m = main_of(board)
        if not (o and m and m[1] and m[2]):
            return None
        p = (1 / o) / (1 / m[1] + 1 / m[2])
    return p if side == "over" else 1 - p


def grade(day, signals, box):
    """Attach result, profit, q (closing fair probability) and clv (EV at the close) to each signal."""
    cl = closes(day)
    for s in signals:
        mn, stt = box.get((s["gid"], s["pid"]), (None, None))
        if not mn:
            s["result"], s["profit"] = "void", None
        else:
            actual = sum(stt[c] for c in PD.MARKET_PARTS[s["market"]])
            s["actual"] = actual
            s["result"] = "push" if actual == s["line"] else ("win" if (actual > s["line"]) == (s["side"] == "over") else "loss")
            s["profit"] = {"push": 0.0, "win": s["odds"] - 1, "loss": -1.0}[s["result"]]
        q = q_close(cl.get((s["gid"], s["pid"], s["market"])), s["side"], s["line"])
        s["q_close"] = q
        s["clv"] = None if q is None else q * s["odds"] - 1
    return signals


def box_of(matchup_db, gids):
    m = PD._ro(matchup_db)
    if not gids:
        return {}
    marks = ",".join("?" * len(gids))
    return {(g, p): (mn, {"pts": a, "reb": b, "ast": c, "fg3m": d}) for g, p, mn, a, b, c, d in
            m.execute(f"SELECT gid, pid, min, pts, reb, ast, fg3m FROM player_games WHERE gid IN ({marks})", list(gids))}


def dates(matchup_db, lines_db, since, until):
    m, q = PD._ro(matchup_db), PD._ro(lines_db)
    first = q.execute("SELECT MIN(seen_at) FROM quotes").fetchone()[0] or "9999"
    return [d for (d,) in m.execute("SELECT DISTINCT date FROM games WHERE home_pts IS NOT NULL AND date BETWEEN ? AND ? "
                                    "ORDER BY date", (max(since, first[:10]), until))]


def summarize(sig):
    """n, graded, CLV (mean, date-clustered 95% CI, coverage) and ROI (mean, CI) of graded signals."""
    g = [s for s in sig if s.get("profit") is not None]
    out = {"signals": len(sig), "graded": len(g)}
    c = [s for s in g if s.get("clv") is not None]
    out["clv_coverage"] = round(len(c) / len(g), 3) if g else None
    if c:
        m_, lo, hi = E.boot_ci([s["clv"] for s in c], [s["date"] for s in c], reps=4000)
        out["clv"] = {"n": len(c), "dates": len({s["date"] for s in c}), "mean": round(m_, 4), "lo": round(lo, 4), "hi": round(hi, 4)}
    if g:
        m_, lo, hi = E.boot_ci([s["profit"] for s in g], [s["date"] for s in g], reps=4000)
        out["roi"] = {"n": len(g), "dates": len({s["date"] for s in g}), "mean": round(m_, 4), "lo": round(lo, 4), "hi": round(hi, 4),
                      "w": sum(s["result"] == "win" for s in g), "l": sum(s["result"] == "loss" for s in g)}
    return out


def replay(rules, since, until, lines_db=HERE / "nba_lines.sqlite", news_db=HERE / "nba_news.sqlite",
           matchup_db=HERE / "nba_matchup.sqlite", gamelogs_db=HERE / "nba_gamelogs.sqlite", history=None):
    """[graded signals] for every rule over every final date in [since, until]."""
    history = history or History(gamelogs_db, matchup_db)
    out = []
    for d in dates(matchup_db, lines_db, since, until):
        day = Day(d, lines_db, news_db, matchup_db, history)
        sig = run_day(day, rules)
        for s in sig:
            s["date"] = d
        out += grade(day, sig, box_of(matchup_db, list(day.games)))
    return out


def load_rule(spec):
    mod, name = spec.split(":")
    return getattr(importlib.import_module(mod), name)()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", required=True, action="append", help="MODULE:NAME (repeatable)")
    ap.add_argument("--from", dest="since", required=True)
    ap.add_argument("--to", dest="until", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    rules = [load_rule(s) for s in a.rule]
    sig = replay(rules, a.since, a.until)
    res = {r.name: summarize([s for s in sig if s["rule"] == r.name]) for r in rules}
    res["note"] = "a development record (replayed), never a verdict: verdicts count only signals after registration"
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": res, "signals": sig}, indent=1, default=str))


if __name__ == "__main__":
    main()
