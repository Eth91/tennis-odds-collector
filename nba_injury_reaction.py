#!/usr/bin/env python3
"""NBA_INJURY_REACTION_PREREG.md (Step 1 of the injury flagger rebuild): how FanDuel and DraftKings reprice teammates
after an official Out. Read-only and descriptive, on copies of the VM's nightly backup. Mac only.

    python3 nba_injury_reaction.py --stores .projdata/vm_backup_20261103 --stamp 20261103
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import sqlite3
import statistics as stx
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
BOOKS = ("fd", "dk")
MARKETS = ("points", "rebounds", "assists", "threes", "pra", "pts_reb", "pts_ast", "reb_ast")
P_MOVE = 0.03                      # 3.0 no-vig points: above FanDuel's price jitter
BASE_MAX = CLOSE_MAX = 30.0        # minutes: a baseline or close older than this is missing
TIP_MIN = 30.0                     # an event's game tips 30+ minutes after the report
MIN_AVG, MIN_GP = 15.0, 2          # a qualifying Out averaged 15+ minutes over 2+ games this season
CONTROL_REPORTS = 12               # control teams: no fresh Out or Doubtful in this report or the previous 12
TS = (1, 5, 15)
CUM = (1, 2, 5, 10, 15, 30, 60)
SEASON = "2026-27"


def t_(s):
    """An aware UTC datetime from the stores' timestamp spellings."""
    s = s.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def nv(o, u):
    return (1 / o) / (1 / o + 1 / u)


def mins(a, b):
    return (b - a).total_seconds() / 60


# ---- the boards --------------------------------------------------------------------------------------------------
class Boards:
    """Each book's board rebuilt from the change log: per (gid, pid, stat), the state after every change, and the
    book's observations per game (successful full fetches; a game-scoped fetch only for the games it wrote rows for)."""

    def __init__(self, lines_db):
        con = sqlite3.connect(f"file:{lines_db}?mode=ro", uri=True)
        self.ok = {b: [] for b in BOOKS}
        game_ts = {b: set() for b in BOOKS}
        for ts, book, status in con.execute("SELECT ts, book, status FROM cycles ORDER BY ts"):
            if book in self.ok and status == "ok":
                self.ok[book].append(t_(ts))
            elif book in self.ok and status == "game":
                game_ts[book].add(ts)
        self.tip, self.first, self.names = {}, {}, {}
        self.scoped = defaultdict(set)                      # (book, gid) -> game-fetch times that wrote rows
        self.states = defaultdict(list)                     # (book, gid, pid, stat) -> [(t, state)]
        ladders = defaultdict(lambda: defaultdict(dict))    # (book, gid, pid, stat) -> {line: {side: odds}}
        cur, batch = None, []
        q = ("SELECT seen_at, book, gid, tip_utc, pid, player, stat, line, side, odds FROM quotes "
             "WHERE pid IS NOT NULL AND book IN ('fd', 'dk') AND stat IN (%s) ORDER BY seen_at" % ",".join("?" * len(MARKETS)))
        for row in con.execute(q, MARKETS):
            if row[0] != cur:
                self._apply(batch, ladders, game_ts)
                cur, batch = row[0], []
            batch.append(row)
        self._apply(batch, ladders, game_ts)
        con.close()

    def _apply(self, batch, ladders, game_ts):
        if not batch:
            return
        t = t_(batch[0][0])
        touched = set()
        for seen, book, gid, tip, pid, player, stat, line, side, odds in batch:
            k = (book, gid, pid, stat)
            lad = ladders[k][line]
            if odds is None:
                lad.pop(side, None)
            else:
                lad[side] = odds
            touched.add(k)
            self.tip.setdefault(gid, t_(tip))
            self.first.setdefault((book, gid), t)
            self.names[pid] = player
            if seen in game_ts[book]:
                self.scoped[(book, gid)].add(t)
        for k in touched:
            st = self.main(ladders[k])
            seq = self.states[k]
            if not seq or seq[-1][1] != st:
                seq.append((t, st))

    @staticmethod
    def main(ladder):
        """(main line, no-vig over, over odds, under odds, two-sided rungs) or None when nothing is two-sided."""
        two = [(ln, s["over"], s["under"]) for ln, s in ladder.items() if s.get("over") and s.get("under")]
        if not two:
            return None
        ln, o, u = min(two, key=lambda r: (abs(nv(r[1], r[2]) - 0.5), r[0]))
        return (ln, nv(o, u), o, u, tuple(sorted(two)))

    def obs(self, book, gid):
        """The book's observation times for a game, before its tip."""
        k = (book, gid)
        if not hasattr(self, "_obs"):
            self._obs = {}
        if k not in self._obs:
            first, tip = self.first.get(k), self.tip.get(gid)
            if first is None or tip is None:
                self._obs[k] = []
            else:
                lo, hi = bisect.bisect_left(self.ok[book], first), bisect.bisect_left(self.ok[book], tip)
                self._obs[k] = sorted(set(self.ok[book][lo:hi]) | {s for s in self.scoped[k] if s < tip})
        return self._obs[k]

    def state(self, book, gid, pid, stat, t):
        k = (book, gid, pid, stat)
        seq = self.states.get(k)
        if not seq:
            return None
        if not hasattr(self, "_times"):
            self._times = {}
        if k not in self._times:
            self._times[k] = [x[0] for x in seq]
        i = bisect.bisect_right(self._times[k], t) - 1
        return seq[i][1] if i >= 0 else None

    def props(self, book, gid):
        if not hasattr(self, "_props"):
            self._props = defaultdict(set)
            for (b, g, p, s) in self.states:
                self._props[(b, g)].add((p, s))
        return self._props.get((book, gid), set())


# ---- classification ----------------------------------------------------------------------------------------------
def classify(base, st):
    """stale / moved / pulled against the baseline state."""
    if st is None:
        return "pulled"
    if st[0] == base[0] and abs(st[1] - base[1]) < P_MOVE:
        return "stale"
    return "moved"


def track(boards, book, gid, pid, stat, pub):
    """One prop's path after a report: baseline, close, the state at every observation, latency [L, U]; None without a
    baseline."""
    obs = boards.obs(book, gid)
    i = bisect.bisect_right(obs, pub) - 1
    if i < 0 or mins(obs[i], pub) > BASE_MAX:
        return None
    t0 = obs[i]
    base = boards.state(book, gid, pid, stat, t0)
    if base is None:
        return None
    tip = boards.tip[gid]
    path = [(t, classify(base, boards.state(book, gid, pid, stat, t))) for t in obs[i + 1:]]
    close_t = obs[-1] if obs and mins(obs[-1], tip) <= CLOSE_MAX and obs[-1] > pub else None
    close = boards.state(book, gid, pid, stat, close_t) if close_t else None
    U = next((t for t, c in path if c != "stale"), None)
    stale_before = [t for t, c in path if c == "stale" and (U is None or t < U)]
    L = stale_before[-1] if stale_before else pub
    first_kind = next((c for t, c in path if c != "stale"), None)
    return {"base_t": t0, "base": base, "close_t": close_t, "close": close,
            "close_kind": classify(base, close) if close_t else None, "U": U, "L": L, "first_kind": first_kind,
            "path": path}


def move_of(base, close):
    """(direction, main-line change, no-vig change): up when the main line rose, else when the over got likelier."""
    dl, dp = close[0] - base[0], close[1] - base[1]
    d = "up" if (dl > 0 or (dl == 0 and dp > 0)) else "down" if (dl < 0 or dp < 0) else "none"
    return d, dl, dp


# ---- events ------------------------------------------------------------------------------------------------------
def load_events(news_db, matchup_db, boards):
    """(qualifying events, every fresh Out with why it did or didn't qualify, the per-report fresh Out/Doubtful teams)."""
    con = sqlite3.connect(f"file:{news_db}?mode=ro", uri=True)
    reps = [(m, t_(p)) for m, p in con.execute("SELECT mark, published_at FROM reports WHERE published_at IS NOT NULL")]
    reps.sort(key=lambda r: r[1])
    snap = defaultdict(lambda: defaultdict(dict))
    names = {}
    for mark, gdate, team, pid, player, status in con.execute(
            "SELECT mark, game_date, team, pid, player, status FROM snapshots WHERE pid IS NOT NULL"):
        snap[mark][(gdate, team)][pid] = status
        names[pid] = player
    news = defaultdict(list)
    for pid, gdate, status, det, src in con.execute(
            "SELECT pid, game_date, status, detected_at, source FROM news_items WHERE pid IS NOT NULL"):
        if status in ("out", "doubtful") and det:
            news[(pid, gdate)].append((t_(det), src))
    con.close()
    mc = sqlite3.connect(f"file:{matchup_db}?mode=ro", uri=True)
    games = {}
    for gid, date, home, away in mc.execute("SELECT gid, date, home, away FROM games WHERE season = ?", (SEASON,)):
        games[(date, home)] = games[(date, away)] = gid
    tg = defaultdict(list)                                  # team -> [(date, gid)]
    for gid, date, home, away in mc.execute("SELECT gid, date, home, away FROM games WHERE season = ?", (SEASON,)):
        tg[home].append((date, gid))
        tg[away].append((date, gid))
    for v in tg.values():
        v.sort()
    pg = defaultdict(dict)                                  # gid -> {pid: (team, min)}
    for gid, team, pid, m in mc.execute("SELECT pg.gid, pg.team, pg.pid, pg.min FROM player_games pg JOIN games g "
                                        "USING (gid) WHERE g.season = ?", (SEASON,)):
        pg[gid][pid] = (team, m or 0.0)
    gdate = {gid: d for (d, _t), gid in games.items()}
    mc.close()

    memo = {}

    def team_of(pid, date):
        if (pid, date) in memo:
            return memo[(pid, date)]
        memo[(pid, date)] = _team_of(pid, date)
        return memo[(pid, date)]

    def _team_of(pid, date):
        best = None
        for gid, rows in pg.items():
            if pid in rows and gdate.get(gid, "9") <= date and (best is None or gdate[gid] > best[0]):
                best = (gdate[gid], rows[pid][0])
        return best[1] if best else None

    def his_minutes(pid, team, date):
        """(played his team's last game before the date, his mean minutes and games before the date)."""
        prior = [gid for d, gid in tg[team] if d < date]
        if not prior:
            return None, None, 0
        played_last = pg[prior[-1]].get(pid, (None, 0.0))[1] > 0
        ms = [pg[g][pid][1] for g in prior if pid in pg[g] and pg[g][pid][1] > 0]
        return played_last, (sum(ms) / len(ms) if ms else 0.0), len(ms)

    last = {}                                               # (game_date, team) -> statuses in the last report listing it
    fresh_all, events, fresh_teams = [], {}, []
    for mark, pub in reps:
        teams_now = set()
        for key, st in snap.get(mark, {}).items():
            prev = last.get(key, {})
            for pid, s in st.items():
                ps = prev.get(pid)
                if s in ("Out", "Doubtful") and ps not in ("Out", s):
                    teams_now.add(key[1])
                if s != "Out" or ps == "Out":
                    continue
                date, team = key
                gid = games.get((date, team))
                f = {"mark": mark, "pub": pub, "date": date, "team": team, "pid": pid, "player": names.get(pid),
                     "prior": ps or "not listed", "gid": gid}
                tip = boards.tip.get(gid) if gid else None
                played_last, avg, gp = his_minutes(pid, team, date)
                f.update(avg_min=avg, gp=gp, played_last=played_last)
                why = ("no game in the box scores" if gid is None else "no lines for the game" if tip is None else
                       "tips < 30 min after the report" if mins(pub, tip) < TIP_MIN else
                       "no earlier team game this season" if played_last is None else
                       "missed his team's last game (not absence game 1)" if not played_last else
                       f"under {MIN_AVG:.0f} min average or < {MIN_GP} games" if (avg or 0) < MIN_AVG or gp < MIN_GP
                       else None)
                f["why_not"] = why
                nw = [x for x in news.get((pid, date), []) if x[0] < pub]
                f["news_first"] = min(nw)[1] if nw else None
                f["news_lead_min"] = mins(min(nw)[0], pub) if nw else None
                fresh_all.append(f)
                if why is None:
                    ev = events.setdefault((mark, gid, team), {"mark": mark, "pub": pub, "gid": gid, "team": team,
                                                               "date": date, "tip": tip, "outs": []})
                    ev["outs"].append(f)
            last[key] = st
        fresh_teams.append((mark, pub, teams_now))
    for ev in events.values():
        lead = max(ev["outs"], key=lambda f: f["avg_min"])
        ev.update(lead=lead, star=lead["avg_min"] >= 28.0, prior=lead["prior"], news_first=any(f["news_first"] for f in ev["outs"]),
                  horizon="today" if ev["date"] == ev["pub"].astimezone(ET).date().isoformat() else "tomorrow")
    return sorted(events.values(), key=lambda e: e["pub"]), fresh_all, fresh_teams, team_of


# ---- the analysis ------------------------------------------------------------------------------------------------
def units(events, boards, team_of):
    """Every (event, book, teammate, market) with a baseline: its track and the event's context. Plus drop counts."""
    out, drops = [], defaultdict(int)
    for ev in events:
        outs = {f["pid"] for f in ev["outs"]}
        for book in BOOKS:
            obs = boards.obs(book, ev["gid"])
            i = bisect.bisect_right(obs, ev["pub"]) - 1
            first = boards.first.get((book, ev["gid"]))
            if i < 0 or mins(obs[i], ev["pub"]) > BASE_MAX:
                drops[f"{book}: events with the game not posted at the report" if first is None or first > ev["pub"]
                      else f"{book}: events with no observation in the 30 min before"] += 1
            for pid, stat in sorted(boards.props(book, ev["gid"])):
                if pid in outs:
                    continue
                tm = team_of(pid, ev["date"])
                if tm is None:
                    drops["unknown team"] += 1
                    continue
                if tm != ev["team"]:
                    continue
                tr = track(boards, book, ev["gid"], pid, stat, ev["pub"])
                if tr is None:
                    seq = boards.states[(book, ev["gid"], pid, stat)]
                    why = ("no observation" if i < 0 or mins(obs[i], ev["pub"]) > BASE_MAX else
                           "posted after the report" if seq[0][0] > ev["pub"] else "not two-sided at the report")
                    drops[f"{book} props: {why}"] += 1
                    continue
                if tr["close_t"] is None:
                    drops[f"{book}: no close"] += 1
                out.append({"ev": ev, "book": book, "pid": pid, "player": boards.names.get(pid), "stat": stat, **tr})
    return out, dict(drops)


def controls(events, boards, fresh_teams, team_of):
    """Background movement: at each event's report time, props of teams playing that date with no fresh Out or Doubtful
    in that report or the previous 12."""
    idx = {m: i for i, (m, _p, _t) in enumerate(fresh_teams)}
    gids_by_date = defaultdict(set)
    for (book, gid) in boards.first:
        gids_by_date[boards.tip[gid].astimezone(ET).date().isoformat()].add(gid)
    out, seen = [], set()
    for ev in events:
        if (ev["mark"], ev["date"]) in seen:
            continue
        seen.add((ev["mark"], ev["date"]))
        i = idx[ev["mark"]]
        hot = set().union(*[fresh_teams[j][2] for j in range(max(0, i - CONTROL_REPORTS), i + 1)])
        for gid in gids_by_date[ev["date"]]:
            if mins(ev["pub"], boards.tip[gid]) < TIP_MIN:
                continue
            for book in BOOKS:
                for pid, stat in boards.props(book, gid):
                    tm = team_of(pid, ev["date"])
                    if tm is None or tm in hot:
                        continue
                    tr = track(boards, book, gid, pid, stat, ev["pub"])
                    if tr is not None and tr["close_t"] is not None:
                        out.append({"book": book, "gid": gid, "pid": pid, "stat": stat, "pub": ev["pub"], **tr})
    return out


def stale_at(u, t):
    pub = u["ev"]["pub"] if "ev" in u else u["pub"]
    cut = pub + dt.timedelta(minutes=t)
    if u["U"] is not None and u["U"] <= cut:
        return "moved"
    if u["L"] >= cut:
        return "stale"
    return "unknown"


def summary(us):
    """Counts and shares for a set of units."""
    n = len(us)
    with_close = [u for u in us if u["close_t"]]
    kinds = defaultdict(int)
    for u in with_close:
        kinds[u["close_kind"]] += 1
    movers = [u for u in with_close if u["close_kind"] == "moved"]
    res = {"n": n, "with_close": len(with_close), "close": dict(kinds), "movers": len(movers)}
    if movers:
        mv = [move_of(u["base"], u["close"]) for u in movers]
        res["up_share"] = sum(d == "up" for d, _, _ in mv) / len(mv)
        res["median_abs_line"] = stx.median(abs(dl) for _, dl, _ in mv)
        res["line_changed_share"] = sum(dl != 0 for _, dl, _ in mv) / len(mv)
        same = [abs(dp) for _, dl, dp in mv if dl == 0]
        res["median_abs_p_when_line_same"] = stx.median(same) if same else None
        pub = lambda u: u["ev"]["pub"] if "ev" in u else u["pub"]
        U = [mins(pub(u), u["U"]) for u in movers if u["U"]]
        L = [mins(pub(u), u["L"]) for u in movers]
        res["latency_U_median"] = stx.median(U) if U else None
        res["latency_L_median"] = stx.median(L) if L else None
        res["moved_by"] = {t: sum(1 for x in U if x <= t) / len(movers) for t in CUM}
        res["stale_at"] = {t: {k: sum(stale_at(u, t) == k for u in movers) for k in ("stale", "moved", "unknown")} for t in TS}
    if with_close:
        res["moved_rate"] = len(movers) / len(with_close)
    return res


def dk_lag(us, boards, lagger="dk", leader="fd"):
    """Leader movers with a lagger baseline: was the lagger still stale at an observation after the leader's first
    move, and by how much (the leader's line minus the lagger's; the leader-fair EV of the lagger's price)."""
    by = {(id(u["ev"]), u["pid"], u["stat"], u["book"]): u for u in us}
    rows = []
    for u in us:
        if u["book"] != leader or u["close_kind"] != "moved" or u["U"] is None:
            continue
        v = by.get((id(u["ev"]), u["pid"], u["stat"], lagger))
        if v is None:
            continue
        after = [(t, c) for t, c in v["path"] if t > u["U"]]
        r = {"ev": u["ev"], "pid": u["pid"], "player": u["player"], "stat": u["stat"], "lead_U": u["U"],
             "lag_U": v["U"], "status": "unknown" if not after else ("lag" if after[0][1] == "stale" else "no lag")}
        if r["status"] == "lag":
            s = after[0][0]
            ls = boards.state(leader, u["ev"]["gid"], u["pid"], u["stat"], max(t for t in boards.obs(leader, u["ev"]["gid"]) if t <= s))
            gs = boards.state(lagger, u["ev"]["gid"], u["pid"], u["stat"], s)
            d, _, _ = move_of(u["base"], u["close"])
            r["at"] = s
            r["lag_after_lead_min"] = mins(u["U"], s)
            if gs:
                lv, pc = clv(v["close"], gs[0], "over" if d == "up" else "under", gs[2] if d == "up" else gs[3])
                r["lag_clv_line"], r["lag_clv_price"] = lv, pc
            if ls and gs:
                r["line_gap"] = ls[0] - gs[0]
                rung = {ln: (o, un) for ln, o, un in ls[4]}.get(gs[0])
                if rung:
                    p = nv(*rung)
                    r["ev_fair"] = p * gs[2] - 1 if d == "up" else (1 - p) * gs[3] - 1
                    r["side"] = "over" if d == "up" else "under"
            r["lag_window_min"] = mins(u["U"], v["U"]) if v["U"] else None
        rows.append(r)
    return rows


def clv(close, line, side, odds):
    """EXPLORATORY. (line value in units, price CLV or None) of a bet against the same book's close: the close main line
    beyond the bet line on the bet's side, and, when the close has a two-sided rung at the bet line, p_close × odds − 1."""
    if close is None:
        return None, None
    lv = (close[0] - line) if side == "over" else (line - close[0])
    rung = {ln: (o, un) for ln, o, un in close[4]}.get(line)
    if not rung:
        return lv, None
    p = nv(*rung)
    return lv, (p if side == "over" else 1 - p) * odds - 1


def pub_of(u):
    return u["ev"]["pub"] if "ev" in u else u["pub"]


def stale_bets(us, boards, within=15.0):
    """EXPLORATORY. For props still stale at the book's first observation after the report (within 15 min of it): the
    over and the under at that observation's main line and prices, against the same book's close."""
    rows = []
    for u in us:
        if not u["close_t"] or u["close"] is None or not u["path"]:   # pulled at the close: no close to compare
            continue
        t, c = u["path"][0]
        if c != "stale" or mins(pub_of(u), t) > within:
            continue
        gid = u["ev"]["gid"] if "ev" in u else u["gid"]
        st = boards.state(u["book"], gid, u["pid"], u["stat"], t)
        for side, odds in (("over", st[2]), ("under", st[3])):
            lv, pc = clv(u["close"], st[0], side, odds)
            rows.append({"u": u, "side": side, "lv": lv, "pc": pc, "gid": gid})
    return rows


def bet_sum(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    pcs = [r["pc"] for r in rows if r["pc"] is not None]
    lvs = [r["lv"] for r in rows]
    beat = sum(1 for r in rows if r["lv"] > 0 or (r["lv"] == 0 and r["pc"] is not None and r["pc"] > 0))
    return {"n": n, "games": len({r["gid"] for r in rows}), "line_better": sum(x > 0 for x in lvs) / n,
            "line_worse": sum(x < 0 for x in lvs) / n, "mean_line_value": sum(lvs) / n, "same_line": len(pcs),
            "mean_price_clv_same_line": sum(pcs) / len(pcs) if pcs else None, "beat_close": beat / n}


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stores", required=True)
    ap.add_argument("--stamp", required=True)
    ap.add_argument("--out", default="NBA_INJURY_REACTION_TABLES.md")
    a = ap.parse_args()
    d = Path(a.stores)
    lines_db, news_db, matchup_db = (d / f"nba_{n}.{a.stamp}.sqlite" for n in ("lines", "news", "matchup"))
    boards = Boards(lines_db)
    events, fresh_all, fresh_teams, team_of = load_events(news_db, matchup_db, boards)
    us, drops = units(events, boards, team_of)
    ctl = controls(events, boards, fresh_teams, team_of)
    res = {"stamp": a.stamp, "events": len(events), "fresh_outs": len(fresh_all), "drops": drops}

    why = defaultdict(int)
    for f in fresh_all:
        why[f["why_not"] or "QUALIFIES"] += 1
    res["fresh_out_reasons"] = dict(why)
    cad = {}
    for book in BOOKS:
        gaps = []
        for ev in events:
            ob = [t for t in boards.obs(book, ev["gid"]) if ev["pub"] < t <= ev["pub"] + dt.timedelta(minutes=30)]
            prev = [t for t in boards.obs(book, ev["gid"]) if t <= ev["pub"]]
            if prev:
                ob = [prev[-1]] + ob
            gaps += [mins(x, y) for x, y in zip(ob, ob[1:])]
            if ob and len(ob) == 1:
                pass
        first = [mins(ev["pub"], next((t for t in boards.obs(book, ev["gid"]) if t > ev["pub"]), ev["pub"]))
                 for ev in events if any(t > ev["pub"] for t in boards.obs(book, ev["gid"]))]
        cad[book] = {"median_gap_30min_after": stx.median(gaps) if gaps else None,
                     "median_first_obs_after_report": stx.median(first) if first else None,
                     "first_obs_within_1min": sum(x <= 1 for x in first) / len(first) if first else None,
                     "first_obs_within_5min": sum(x <= 5 for x in first) / len(first) if first else None,
                     "first_obs_within_15min": sum(x <= 15 for x in first) / len(first) if first else None,
                     "first_obs_within_30min": sum(x <= 30 for x in first) / len(first) if first else None,
                     "events_observed_after": len(first)}
    res["cadence"] = cad

    res["teammates"] = {b: summary([u for u in us if u["book"] == b]) for b in BOOKS}
    res["teammates"]["both"] = summary(us)
    res["control"] = {b: summary([u for u in ctl if u["book"] == b]) for b in BOOKS}
    res["control"]["both"] = summary(ctl)
    res["by_market"] = {f"{b} {m}": summary([u for u in us if u["book"] == b and u["stat"] == m]) for b in BOOKS for m in MARKETS}
    splits = {"star (28+ min)": lambda u: u["ev"]["star"], "rotation (15-28 min)": lambda u: not u["ev"]["star"],
              "news before the report": lambda u: u["ev"]["news_first"], "no news before": lambda u: not u["ev"]["news_first"],
              "game today": lambda u: u["ev"]["horizon"] == "today", "game tomorrow": lambda u: u["ev"]["horizon"] == "tomorrow"}
    for p in ("not listed", "Available", "Probable", "Questionable", "Doubtful"):
        splits[f"prior {p}"] = (lambda p_: lambda u: u["ev"]["prior"] == p_)(p)
    res["splits"] = {f"{b} {k}": summary([u for u in us if u["book"] == b and f(u)]) for b in BOOKS for k, f in splits.items()}
    lag = dk_lag(us, boards)
    rev = dk_lag(us, boards, lagger="fd", leader="dk")

    def lag_sum(rows):
        n = len(rows)
        lg = [r for r in rows if r["status"] == "lag"]
        evs = [r["ev_fair"] for r in lg if r.get("ev_fair") is not None]
        gaps = [abs(r["line_gap"]) for r in lg if r.get("line_gap") is not None]
        return {"leader_movers_with_baseline": n, "lag": len(lg), "no_lag": sum(r["status"] == "no lag" for r in rows),
                "unknown": sum(r["status"] == "unknown" for r in rows), "lag_rate": len(lg) / n if n else None,
                "median_ev_fair": stx.median(evs) if evs else None, "ev_n": len(evs), "ev_missing": len(lg) - len(evs),
                "share_ev_ge_3": sum(e >= 0.03 for e in evs) / len(evs) if evs else None,
                "share_ev_ge_5": sum(e >= 0.05 for e in evs) / len(evs) if evs else None,
                "median_abs_line_gap": stx.median(gaps) if gaps else None,
                "median_lag_after_lead_min": stx.median([r["lag_after_lead_min"] for r in lg]) if lg else None,
                "lagger_close": bet_sum([{"lv": r["lag_clv_line"], "pc": r["lag_clv_price"], "gid": r["ev"]["gid"]}
                                         for r in lg if r.get("lag_clv_line") is not None])}
    res["dk_lags_fd"], res["fd_lags_dk"] = lag_sum(lag), lag_sum(rev)

    # EXPLORATORY (not pre-registered): how much of the reaction is in the first hour, and what a stale bet got
    ex = {"reacted_by": {}, "stale_bets": {}}
    for name, pool in (("teammates", us), ("control", ctl)):
        for b in BOOKS:
            wc = [u for u in pool if u["book"] == b and u["close_t"]]
            ex["reacted_by"][f"{name} {b}"] = {t: (sum(1 for u in wc if u["U"] and mins(pub_of(u), u["U"]) <= t) / len(wc)
                                               if wc else None) for t in (5, 15, 60)}
    big = ("points", "pra", "pts_reb", "pts_ast")
    sb_t, sb_c = stale_bets(us, boards), stale_bets(ctl, boards)
    groups = {"all": lambda r: True, "points/PRA/P+R/P+A": lambda r: r["u"]["stat"] in big,
              "reb/ast/threes/R+A": lambda r: r["u"]["stat"] not in big}
    tm_groups = {"no news before the report": lambda r: not r["u"]["ev"]["news_first"],
                 "news before the report": lambda r: r["u"]["ev"]["news_first"],
                 "star Out (28+ min)": lambda r: r["u"]["ev"]["star"], "game today": lambda r: r["u"]["ev"]["horizon"] == "today"}
    for b in BOOKS:
        for side in ("over", "under"):
            for gname, g in groups.items():
                ex["stale_bets"][f"teammates {b} {side} {gname}"] = bet_sum([r for r in sb_t if r["u"]["book"] == b and r["side"] == side and g(r)])
                ex["stale_bets"][f"control {b} {side} {gname}"] = bet_sum([r for r in sb_c if r["u"]["book"] == b and r["side"] == side and g(r)])
            for gname, g in tm_groups.items():
                ex["stale_bets"][f"teammates {b} {side} {gname}"] = bet_sum([r for r in sb_t if r["u"]["book"] == b and r["side"] == side and g(r)])
    fk = defaultdict(int)
    for u in us:
        fk[f"{u['book']} {u['first_kind'] or 'never'}"] += 1
    ex["first_change"] = dict(fk)
    res["exploratory"] = ex

    # the go/no-go (NBA_INJURY_REACTION_PREREG.md)
    movers = [u for u in us if u["close_kind"] == "moved"]
    st5 = sum(stale_at(u, 5) == "stale" for u in movers) / len(movers) if movers else 0
    pp = [u for u in movers if u["stat"] in ("points", "pra")]
    mv = [move_of(u["base"], u["close"]) for u in pp]
    med_line = stx.median(abs(dl) for _, dl, _ in mv) if mv else 0
    med_line_cond = stx.median(abs(dl) for _, dl, _ in mv if dl != 0) if any(dl != 0 for _, dl, _ in mv) else None
    same_p = [abs(dp) for _, dl, dp in mv if dl == 0]
    rate_t, rate_c = res["teammates"]["both"].get("moved_rate", 0), res["control"]["both"].get("moved_rate", 0)
    window = {"stale_at_5_share": st5, "median_line_move_pts_pra": med_line, "median_line_move_pts_pra_when_changed": med_line_cond,
              "pts_pra_movers": len(pp), "pts_pra_line_changed": sum(dl != 0 for _, dl, _ in mv),
              "median_p_move_pts_pra_when_line_same": stx.median(same_p) if same_p else None,
              "moved_rate_teammates": rate_t, "moved_rate_control": rate_c}
    window["go"] = bool(len(events) >= 30 and st5 >= 0.25 and (med_line >= 1.0 or (window["median_p_move_pts_pra_when_line_same"] or 0) >= 0.05)
                        and rate_c and rate_t >= 2 * rate_c)
    dl_ = res["dk_lags_fd"]
    dkgo = bool(len(events) >= 30 and (dl_["lag_rate"] or 0) >= 0.20 and (dl_["median_ev_fair"] or -1) >= 0.03)
    res["go_no_go"] = {"insufficient": len(events) < 30, "window": window, "dk_lag_go": dkgo}

    # audit files
    stamp = a.stamp
    with open(d / f"inj_units.{stamp}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["report", "published_at", "gid", "team", "outs", "book", "pid", "player", "stat", "base_t", "base_line",
                    "base_p", "close_t", "close_line", "close_p", "close_kind", "L_min", "U_min", "first_kind",
                    "stale_1", "stale_5", "stale_15"])
        for u in us:
            ev = u["ev"]
            w.writerow([ev["mark"], ev["pub"].isoformat(), ev["gid"], ev["team"], "; ".join(f["player"] or "" for f in ev["outs"]),
                        u["book"], u["pid"], u["player"], u["stat"], u["base_t"].isoformat(), u["base"][0], round(u["base"][1], 4),
                        u["close_t"].isoformat() if u["close_t"] else "", u["close"][0] if u["close"] else "",
                        round(u["close"][1], 4) if u["close"] else "", u["close_kind"] or "", round(mins(ev["pub"], u["L"]), 2),
                        round(mins(ev["pub"], u["U"]), 2) if u["U"] else "", u["first_kind"] or "",
                        *[stale_at(u, t) for t in TS]])
    with open(d / f"inj_fresh_outs.{stamp}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["report", "published_at", "date", "team", "pid", "player", "prior", "avg_min", "gp", "played_last",
                    "news_first", "news_lead_min", "qualifies_or_why_not"])
        for f in fresh_all:
            w.writerow([f["mark"], f["pub"].isoformat(), f["date"], f["team"], f["pid"], f["player"], f["prior"],
                        round(f["avg_min"], 1) if f["avg_min"] is not None else "", f["gp"], f["played_last"],
                        f["news_first"] or "", round(f["news_lead_min"], 1) if f["news_lead_min"] is not None else "",
                        f["why_not"] or "QUALIFIES"])
    with open(d / f"inj_lag.{stamp}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["direction", "report", "gid", "player", "stat", "status", "leader_U", "lagger_U", "lag_obs_at",
                    "lag_after_lead_min", "line_gap", "side", "ev_fair"])
        for name, rows in (("dk lags fd", lag), ("fd lags dk", rev)):
            for r in rows:
                w.writerow([name, r["ev"]["mark"], r["ev"]["gid"], r["player"], r["stat"], r["status"],
                            r["lead_U"].isoformat(), r["lag_U"].isoformat() if r["lag_U"] else "",
                            r["at"].isoformat() if r.get("at") else "", round(r.get("lag_after_lead_min") or 0, 2),
                            r.get("line_gap", ""), r.get("side", ""), round(r["ev_fair"], 4) if r.get("ev_fair") is not None else ""])

    # per event and per player
    ev_rows = []
    for ev in events:
        mine = [u for u in us if u["ev"] is ev]
        s = summary(mine)
        ev_rows.append((ev, s))
    res["per_event"] = [{"report": ev["mark"], "team": ev["team"], "gid": ev["gid"],
                         "outs": [(f["player"], round(f["avg_min"], 1), f["prior"]) for f in ev["outs"]],
                         "news_first": ev["news_first"], "horizon": ev["horizon"], **{k: s.get(k) for k in
                         ("n", "movers", "moved_rate", "latency_U_median", "median_abs_line")},
                         "stale5": s.get("stale_at", {}).get(5)} for ev, s in ev_rows]
    by_tm = defaultdict(list)
    for u in us:
        by_tm[(u["player"], u["book"])].append(u)
    res["per_teammate"] = sorted(([k[0], k[1], len(v), summary(v).get("movers"), summary(v).get("moved_rate")]
                                  for k, v in by_tm.items()), key=lambda r: -r[2])[:25]
    (d / f"inj_result.{stamp}.json").write_text(json.dumps(res, indent=1, default=str))
    write_tables(res, a.out, events)
    print(json.dumps({k: res[k] for k in ("events", "fresh_outs", "drops", "fresh_out_reasons", "cadence", "go_no_go",
                                          "dk_lags_fd", "fd_lags_dk")}, indent=1, default=str))


def write_tables(res, path, events):
    L = [f"# Step 1 tables (generated by nba_injury_reaction.py from the {res['stamp']} backup)", ""]
    L += ["## Fresh Outs and why they did or didn't qualify", "", "| Reason | Count |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in sorted(res["fresh_out_reasons"].items(), key=lambda x: -x[1])]
    L += ["", f"Qualifying events (report, game, team): **{res['events']}**. Dropped teammate props: "
          + ", ".join(f"{k} {v}" for k, v in res["drops"].items()), ""]
    L += ["## How often each book was checked around a report (observations that include the event's game)", "",
          "| Book | Events observed after | Median minutes between checks (30 min after) | Median minutes to the first check after "
          "the report | First check within 1 / 5 / 15 / 30 min |", "|---|---|---|---|---|"]
    for b, c in res["cadence"].items():
        f = lambda x: "—" if x is None else f"{x:.1f}"
        L.append(f"| {b} | {c['events_observed_after']} | {f(c['median_gap_30min_after'])} | {f(c['median_first_obs_after_report'])} | "
                 + " / ".join(pct(c[f"first_obs_within_{t}min"]) for t in (1, 5, 15, 30)) + " |")

    def block(title, d):
        out = ["", f"## {title}", "", "| Set | Props (close) | Moved | Pulled | Unchanged | Up | Median line move | Line changed "
               "| Median no-vig move (line same) | Latency U / L (median min) | Moved by 1 / 5 / 15 / 60 min | Stale at 1 / 5 / 15 (confirmed; unknown) |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, s in d.items():
            if not s.get("with_close"):
                continue
            c = s["close"]
            wc = s["with_close"]
            if s.get("movers"):
                sa = s["stale_at"]
                stale = " / ".join(f"{sa[t]['stale']} ({pct(sa[t]['stale'] / s['movers'])}; {sa[t]['unknown']})" for t in TS)
                mb = " / ".join(pct(s["moved_by"][t]) for t in (1, 5, 15, 60))
                lat = f"{s['latency_U_median']:.1f} / {s['latency_L_median']:.1f}" if s["latency_U_median"] is not None else "—"
                mp = s["median_abs_p_when_line_same"]
                row = (f"{pct(s['up_share'])} | {s['median_abs_line']:.1f} | {pct(s['line_changed_share'])} | "
                       f"{'—' if mp is None else f'{100 * mp:.1f} pts'} | {lat} | {mb} | {stale}")
            else:
                row = "— | — | — | — | — | — | —"
            out.append(f"| {k} | {wc} | {c.get('moved', 0)} ({pct(c.get('moved', 0) / wc)}) | {c.get('pulled', 0)} | "
                       f"{c.get('stale', 0)} | {row} |")
        return out

    L += block("Teammates vs control, baseline to close", {**{f"teammates {k}": v for k, v in res["teammates"].items()},
                                                            **{f"control {k}": v for k, v in res["control"].items()}})
    L += block("Teammates by market", res["by_market"])
    L += block("Teammates by split", res["splits"])
    L += ["", "## One book lagging the other", "", "| Direction | Leader movers with a lagger baseline | Lag | No lag | Unknown "
          "| Lag rate | Median line gap | Median leader-fair EV (n; missing) | EV ≥ 3% | EV ≥ 5% | Median minutes after the leader moved |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, k in (("DraftKings lags FanDuel", "dk_lags_fd"), ("FanDuel lags DraftKings", "fd_lags_dk")):
        s = res[k]
        f = lambda x: "—" if x is None else f"{x:.1f}"
        ev = "—" if s["median_ev_fair"] is None else f"{100 * s['median_ev_fair']:+.1f}% ({s['ev_n']}; {s['ev_missing']})"
        L.append(f"| {name} | {s['leader_movers_with_baseline']} | {s['lag']} | {s['no_lag']} | {s['unknown']} | {pct(s['lag_rate'])} | "
                 f"{f(s['median_abs_line_gap'])} | {ev} | {pct(s['share_ev_ge_3'])} | {pct(s['share_ev_ge_5'])} | "
                 f"{f(s['median_lag_after_lead_min'])} |")
    g = res["go_no_go"]
    w = g["window"]
    L += ["", "## Go / no-go (as pre-registered)", "",
          f"- Insufficient (< 30 events): {g['insufficient']}",
          f"- WINDOW: stale at +5 among movers {pct(w['stale_at_5_share'])} (needs 25%); median points/PRA main-line move "
          f"{w['median_line_move_pts_pra']} over all {w['pts_pra_movers']} points/PRA movers ({w['median_line_move_pts_pra_when_changed']} "
          f"over the {w['pts_pra_line_changed']} whose line changed) (needs 1.0) or no-vig "
          f"{pct(w['median_p_move_pts_pra_when_line_same'])} when the line held "
          f"(needs 5 pts); moved rate teammates {pct(w['moved_rate_teammates'])} vs control {pct(w['moved_rate_control'])} (needs 2×) "
          f"-> **{'GO' if w['go'] else 'NO-GO'}**",
          f"- DK-LAG: lag rate {pct(res['dk_lags_fd']['lag_rate'])} (needs 20%), median FanDuel-fair EV "
          f"{pct(res['dk_lags_fd']['median_ev_fair'])} (needs +3%) -> **{'GO' if g['dk_lag_go'] else 'NO-GO'}**", ""]
    ex = res["exploratory"]
    L += ["## EXPLORATORY (not pre-registered): share of all props that changed within t minutes of the report", "",
          "| Set | Changed by 5 min | By 15 min | By 60 min |", "|---|---|---|---|"]
    L += [f"| {k} | {pct(v[5])} | {pct(v[15])} | {pct(v[60])} |" for k, v in ex["reacted_by"].items()]
    L += ["", "First change after the report (teammates): " + ", ".join(f"{k} {v}" for k, v in sorted(ex["first_change"].items())), ""]
    L += ["## EXPLORATORY: a bet on a prop still stale at the book's first check after the report (within 15 min), vs the same "
          "book's close", "", "Line value = the close main line beyond the bet line on the bet's side. Price CLV only where the close "
          "still has a two-sided rung at the bet line.", "",
          "| Set | Bets | Games | Close line better | Close line worse | Mean line value | Same-line closes | Mean price CLV (same line) "
          "| Beat the close |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in ex["stale_bets"].items():
        if not v["n"]:
            continue
        mp = "—" if v["mean_price_clv_same_line"] is None else f"{100 * v['mean_price_clv_same_line']:+.1f}%"
        L.append(f"| {k} | {v['n']} | {v['games']} | {pct(v['line_better'])} | {pct(v['line_worse'])} | {v['mean_line_value']:+.2f} | "
                 f"{v['same_line']} | {mp} | {pct(v['beat_close'])} |")
    L += ["", "## EXPLORATORY: the lagging book's stale price (side the leader moved toward) vs the lagging book's own close", "",
          "| Direction | Bets | Close line better | Close line worse | Mean line value | Same-line closes | Mean price CLV (same line) "
          "| Beat the close |", "|---|---|---|---|---|---|---|---|"]
    for name, k in (("DraftKings stale after FanDuel moved", "dk_lags_fd"), ("FanDuel stale after DraftKings moved", "fd_lags_dk")):
        v = res[k]["lagger_close"]
        if v["n"]:
            mp = "—" if v["mean_price_clv_same_line"] is None else f"{100 * v['mean_price_clv_same_line']:+.1f}%"
            L.append(f"| {name} | {v['n']} | {pct(v['line_better'])} | {pct(v['line_worse'])} | {v['mean_line_value']:+.2f} | "
                     f"{v['same_line']} | {mp} | {pct(v['beat_close'])} |")
    L += ["", "## Per event", "", "| Report (ET mark) | Team | Out (avg min, prior) | News first | Game | Props | Movers | Moved rate "
          "| Median U (min) | Median line move | Stale at 5 (stale / moved / unknown) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in res["per_event"]:
        outs = "; ".join(f"{n} ({m}, {p})" for n, m, p in e["outs"])
        s5 = e["stale5"]
        lat = "—" if e["latency_U_median"] is None else f"{e['latency_U_median']:.1f}"
        mal = "—" if e["median_abs_line"] is None else e["median_abs_line"]
        s5s = "—" if not s5 else f"{s5['stale']} / {s5['moved']} / {s5['unknown']}"
        L.append(f"| {e['report']} | {e['team']} | {outs} | {'yes' if e['news_first'] else 'no'} | {e['horizon']} | {e['n']} | "
                 f"{e['movers']} | {pct(e['moved_rate'])} | {lat} | {mal} | {s5s} |")
    L += ["", "## Teammates with the most props", "", "| Player | Book | Props | Movers | Moved rate |", "|---|---|---|---|---|"]
    L += [f"| {p} | {b} | {n} | {m} | {pct(r)} |" for p, b, n, m, r in res["per_teammate"]]
    Path(path).write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
