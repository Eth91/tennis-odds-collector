#!/usr/bin/env python3
"""How fast FanDuel reacts to the news. NBA_SPEED_PREREG.md amendment 5 (information only).

For every trigger (an official report's fresh Out, or a news Out ahead of it), rebuild FanDuel's main
rung for every player on the absent player's team from the change log (nba_lines.quotes), and time its
first change after the news (T0):
  LINE   the main line number changes (primary)
  PRICE  the over price on the same line moves by >= PRICE_EPS
  PULL   the main rung is taken down (information; books often pull props on news)
  PRE    the main line at T0 already differs from PRE_MIN before T0: the book had the news first
The same clock is run, at the same T0, on a CONTROL: players in games with no trigger within
CONTROL_GAP_MIN. That is the background rate of line moves. The shadow flags that trigger created are
their own cell. Resolution is the gap since FanDuel's previous poll; nba_watch polls every minute for
20 min after a trigger.

The main rung is the engine's rule: the two-sided line whose over price is nearest even money,
FanDuel only, with a NULL quote meaning pulled. That is exactly nba_clv.close_of(..., books=("fd",)),
and test_nba_reaction checks the replay against it.

    python nba_reaction.py            # per-trigger table, summary, and the reading rules' status
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import re
import sqlite3
import statistics as st
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
NEWS, LINES, SHADOW = HERE / "nba_news.sqlite", HERE / "nba_lines.sqlite", HERE / "nba_shadow.sqlite"
INDEX = HERE / "nba_player_index.json"
WINDOW_MIN, PRE_MIN, CONTROL_GAP_MIN, FLAG_LAG_MIN = 60, 30, 60, 10
PRICE_EPS, EVEN = 0.03, 1.9091
CUTS = (2, 5, 10, 20, 60)
CONTROL_AHEAD_H = 36                     # control games: tipping within this long after T0
ET = ZoneInfo("America/New_York")
READ_AT = 20
STAT = {"pts": "points", "reb": "rebounds", "ast": "assists"}
FRESH = re.compile(r"^(.*) \(([A-Z]{2,4}), (\d{4}-\d{2}-\d{2})\)$")


def _utc(iso):
    """Any ISO string -> naive UTC 'YYYY-MM-DDTHH:MM:SS' (the change log's format)."""
    t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if t.tzinfo:
        t = t.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return t.replace(microsecond=0).isoformat()


def _add(iso, minutes):
    return (dt.datetime.fromisoformat(iso) + dt.timedelta(minutes=minutes)).isoformat()


def _et_date(iso):
    return dt.datetime.fromisoformat(iso).replace(tzinfo=dt.timezone.utc).astimezone(ET).date().isoformat()


def _mins(a, b):
    return (dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds() / 60


def main_of(state):
    """(line, over) of the main rung in {(line, side): odds or None}, or None (nothing two-sided)."""
    best = None
    for (line, side), odds in state.items():
        if side != "over" or odds is None or state.get((line, "under")) is None:
            continue
        if best is None or abs(odds - EVEN) < abs(best[1] - EVEN):
            best = (line, odds)
    return best


def timeline(rows):
    """rows = [(seen_at, line, side, odds)] for one (gid, pid, stat), FanDuel only, any order ->
    [(seen_at, main or None)], one entry per distinct seen_at, in time order."""
    state, out = {}, []
    for t, grp in groupby(sorted(rows, key=lambda r: r[0]), key=lambda r: r[0]):
        for _t, line, side, odds in grp:
            state[(round(float(line), 1), side)] = odds
        out.append((t, main_of(state)))
    return out


def main_at(tl, t):
    m = None
    for ts, mm in tl:
        if ts > t:
            break
        m = mm
    return m


def measure(tl, t0, end, polls):
    """One unit's reaction, or None when FanDuel had no main rung at T0."""
    m0 = main_at(tl, t0)
    if m0 is None:
        return None
    pre = main_at(tl, _add(t0, -PRE_MIN))
    out = {"line0": m0[0], "pre_moved": pre is not None and pre[0] != m0[0],
           "line_min": None, "price_min": None, "pull_min": None, "gap_min": None}
    for ts, m in tl:
        if ts <= t0 or ts > end:
            continue
        mn = _mins(t0, ts)
        if m is None:
            if out["pull_min"] is None:
                out["pull_min"] = mn
            continue
        if out["line_min"] is None and m[0] != m0[0]:
            out["line_min"] = mn
            i = bisect.bisect_left(polls, ts)                # polls sorted; the last one before ts
            out["gap_min"] = _mins(polls[i - 1], ts) if i else None
        if out["price_min"] is None and m[0] == m0[0] and abs(m[1] - m0[1]) >= PRICE_EPS:
            out["price_min"] = mn
    return out


def load_triggers(news):
    out = []
    for mark, pub, det, fresh in news.execute(
            "SELECT mark, published_at, detected_at, fresh FROM triggers ORDER BY detected_at"):
        xs = []
        for s in json.loads(fresh or "[]"):
            m = FRESH.match(s)
            if m:
                xs.append({"name": m.group(1), "team": m.group(2), "date": m.group(3)})
        if xs:
            out.append({"mark": mark, "t0": _utc(pub), "detected": _utc(det), "xs": xs,
                        "src": "news" if str(mark).startswith("news") else "report"})
    return out


def run(now=None):
    now = _utc(now or dt.datetime.now(dt.timezone.utc).isoformat())
    news = sqlite3.connect(f"file:{NEWS}?mode=ro", uri=True)
    q = sqlite3.connect(f"file:{LINES}?mode=ro", uri=True)
    team_of = {int(pid): v[0] for pid, v in json.loads(INDEX.read_text())["players"].items()}
    polls = [r[0] for r in q.execute(
        "SELECT ts FROM cycles WHERE book='fd' AND status IN ('ok','partial') ORDER BY ts")]
    games = defaultdict(set)                                          # gid -> pids with FD quotes
    tip = {}
    for gid, pid, tu in q.execute("SELECT DISTINCT gid, pid, tip_utc FROM quotes WHERE book='fd' "
                                  "AND pid IS NOT NULL"):
        games[gid].add(pid)
        tip[gid] = _utc(tu)
    stats_of = defaultdict(set)
    for gid, pid, stat in q.execute("SELECT DISTINCT gid, pid, stat FROM quotes WHERE book='fd' "
                                    "AND pid IS NOT NULL"):
        stats_of[(gid, pid)].add(stat)
    flags = []
    if SHADOW.exists():
        sh = sqlite3.connect(f"file:{SHADOW}?mode=ro", uri=True)
        flags = sh.execute("SELECT logged_at, x, gid, pid, stat FROM flags WHERE void_reason IS NULL "
                           "AND pid IS NOT NULL").fetchall()
        sh.close()
    trigs = load_triggers(news)
    # the absent player's game: his team's game on his ET game date
    trig_games = [(t["t0"], {g for g in games for x in t["xs"]
                             if _et_date(tip[g]) == x["date"] and _team_in(g, x["team"], games, team_of)})
                  for t in trigs]
    cache = {}

    def tl_of(gid, pid, stat):
        k = (gid, pid, stat)
        if k not in cache:
            cache[k] = timeline(q.execute(
                "SELECT seen_at, line, side, odds FROM quotes WHERE book='fd' AND gid=? AND pid=? "
                "AND stat=?", k).fetchall())
        return cache[k]

    results = []
    for t, (_t0, tg) in zip(trigs, trig_games):
        t0 = t["t0"]
        if _add(t0, WINDOW_MIN) > now:
            continue                                     # window still open: read it next time
        aff_games = {g for g in tg if tip[g] > t0}
        units = {"affected": [], "control": [], "flagged": []}
        x_teams = {x["team"] for x in t["xs"]}
        for g in aff_games:
            end = min(_add(t0, WINDOW_MIN), tip[g])
            for pid in games[g]:
                if team_of.get(pid) not in x_teams:
                    continue
                for stat in stats_of[(g, pid)]:
                    m = measure(tl_of(g, pid, stat), t0, end, polls)
                    if m:
                        units["affected"].append(dict(m, pid=pid, stat=stat, gid=g))
        busy = {g for t0b, gs in trig_games for g in gs if abs(_mins(t0, t0b)) <= CONTROL_GAP_MIN}
        for g in games:
            if g in busy or tip[g] <= t0 or tip[g] > _add(t0, CONTROL_AHEAD_H * 60):
                continue
            end = min(_add(t0, WINDOW_MIN), tip[g])
            for pid in games[g]:
                for stat in stats_of[(g, pid)]:
                    m = measure(tl_of(g, pid, stat), t0, end, polls)
                    if m:
                        units["control"].append(dict(m, pid=pid, stat=stat, gid=g))
        names = {x["name"] for x in t["xs"]}
        for at, x, g, pid, stat in flags:
            if x in names and 0 <= _mins(t["detected"], _utc(at)) <= FLAG_LAG_MIN and g in aff_games:
                m = measure(tl_of(g, pid, STAT.get(stat, stat)), t0, min(_add(t0, WINDOW_MIN), tip[g]), polls)
                if m:
                    units["flagged"].append(dict(m, pid=pid, stat=STAT.get(stat, stat), gid=g))
        results.append(dict(t, units=units))
    news.close()
    q.close()
    return results


def _team_in(gid, team, games, team_of):
    return any(team_of.get(p) == team for p in games[gid])


def summary(units):
    n = len(units)
    if not n:
        return None
    moved = [u["line_min"] for u in units if u["line_min"] is not None]
    return {"n": n, "players": len({u["pid"] for u in units}),
            "within": {c: sum(1 for m in moved if m <= c) / n for c in CUTS},
            "moved60": len(moved) / n, "median_min": st.median(moved) if moved else None,
            "fast_share": (sum(1 for m in moved if m <= 2) / len(moved)) if moved else None,
            "pre_moved": sum(1 for u in units if u["pre_moved"]) / n,
            "pulled": sum(1 for u in units if u["pull_min"] is not None) / n,
            "price_only": sum(1 for u in units if u["line_min"] is None and u["price_min"] is not None) / n,
            "gap_median": st.median([u["gap_min"] for u in units if u["gap_min"] is not None])
            if any(u["gap_min"] is not None for u in units) else None}


def reading(results):
    """The registered reading rules (amendment 5). Returns (status, detail)."""
    q = [r for r in results if r["units"]["affected"]]
    if len(q) < READ_AT:
        return "NOT YET", f"{len(q)} of {READ_AT} triggers with a measured player-stat"
    a = summary([u for r in q for u in r["units"]["affected"]])
    c = summary([u for r in q for u in r["units"]["control"]])
    ratio = a["moved60"] / c["moved60"] if c and c["moved60"] else float("inf")
    pre = " · PRE-MOVED: the report is too slow a news clock" if a["pre_moved"] >= 0.5 else ""
    if ratio < 2:
        return "NO REACTION" + pre, f"affected/control 60-min move rate {ratio:.2f}x"
    if a["fast_share"] is not None and a["fast_share"] >= 0.5:
        return "FAST" + pre, f"{a['fast_share']:.0%} of movers moved within 2 min; {ratio:.1f}x control"
    if a["median_min"] is not None and a["median_min"] >= 10:
        return "WINDOW" + pre, f"median first move {a['median_min']:.0f} min; {ratio:.1f}x control"
    return "A FEW MINUTES" + pre, f"median first move {a['median_min']:.1f} min; {ratio:.1f}x control"


def _fmt(s):
    if not s:
        return "n=0"
    w = " ".join(f"≤{c}m {100 * v:.0f}%" for c, v in s["within"].items())
    med = f"{s['median_min']:.1f}" if s["median_min"] is not None else "—"
    return (f"n={s['n']} ({s['players']} players) · line moved {w} · median {med} min · "
            f"pre-moved {100 * s['pre_moved']:.0f}% · pulled {100 * s['pulled']:.0f}% · "
            f"price-only {100 * s['price_only']:.0f}%")


if __name__ == "__main__":
    res = run()
    print("FanDuel reaction to the news — NBA_SPEED_PREREG.md amendment 5 (information only)\n")
    for r in res:
        a = summary(r["units"]["affected"])
        print(f"{r['t0'][:16]} {r['src']:<6} {', '.join(x['name'] + ' (' + x['team'] + ')' for x in r['xs'])[:60]}")
        print(f"   affected {_fmt(a)}")
        if r["units"]["flagged"]:
            print(f"   flagged  {_fmt(summary(r['units']['flagged']))}")
    allu = lambda k: [u for r in res for u in r["units"][k]]
    print("\nALL TRIGGERS")
    for k in ("affected", "flagged", "control"):
        print(f"  {k:<9}{_fmt(summary(allu(k)))}")
    s = summary(allu("affected"))
    if s and s["gap_median"] is not None:
        print(f"  resolution: median {s['gap_median']:.1f} min between the FanDuel polls around a move")
    status, detail = reading(res)
    print(f"\nREADING (amendment 5): {status} — {detail}")
