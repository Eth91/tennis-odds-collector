#!/usr/bin/env python3
"""How fast do FanDuel and DraftKings react to official injury-report news? (NBA_NEWS_LATENCY_PREREG.md)
Descriptive. Then the shadow flags against those timings.
    python3 nba_news_latency.py LINES_DB NEWS_DB MATCHUP_DB SHADOW_DB [--json OUT]
"""
import argparse
import bisect
import datetime as dt
import json
from collections import defaultdict

import numpy as np

import nba_proj_data as PD
import nba_project as NP

REG_MIN = 20.0
MOVE_P = 0.02
OUTS = ("Out", "Doubtful")


def iso(t):
    return dt.datetime.fromisoformat(str(t).replace("Z", "+00:00")).replace(tzinfo=None)


def mins(a, b):
    return (iso(b) - iso(a)).total_seconds() / 60


def histories(lines_db, gids):
    import nba_research as R
    q = PD._ro(lines_db)
    marks = ",".join("?" * len(gids))
    rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN ({marks}) AND book IN ('fd','dk') "
                     f"AND pid IS NOT NULL ORDER BY seen_at", list(gids))
    h = defaultdict(list)
    for t, ch in R.replay(r for r in rows if r[4] in PD.MARKET_PARTS):
        for k, st in ch.items():
            h[k].append((t, dict(st)))
    return h


def at(hist, t):
    ts = [x[0] for x in hist]
    i = bisect.bisect_right(ts, t) - 1
    return hist[i][1] if i >= 0 else {}


def main_of(st):
    two = [ln for (ln, s) in st if s == "over" and st.get((ln, "over")) and st.get((ln, "under"))]
    if not two:
        return None, None
    ln = min(two, key=lambda x: abs(float(NP.no_vig(st[(x, "over")], st[(x, "under")])) - .5))
    return ln, float(NP.no_vig(st[(ln, "over")], st[(ln, "under")]))


def moved(before, after):
    """Did the book move: main line changed, or P(over) at the old main changed by >= MOVE_P (or the old main vanished)."""
    l0, p0 = main_of(before)
    l1, _ = main_of(after)
    if l0 is None:
        return None
    if l1 is None:
        return True                                              # pulled
    if l1 != l0:
        return True
    o, u = after.get((l0, "over")), after.get((l0, "under"))
    return abs(float(NP.no_vig(o, u)) - p0) >= MOVE_P if o and u else True


def events(news_db, matchup_db):
    """News events: a regular newly Out/Doubtful on a report after an earlier same-day report listing his team."""
    n, m = PD._ro(news_db), PD._ro(matchup_db)
    games = {}
    for gid, d, h, a in m.execute("SELECT gid, date, home, away FROM games"):
        games[(d, h)] = games[(d, a)] = gid
    apps = defaultdict(list)                                     # pid -> [(date, min)]
    for d, pid, mn in m.execute("SELECT g.date, p.pid, p.min FROM player_games p JOIN games g ON g.gid = p.gid WHERE p.min > 0 ORDER BY g.date"):
        apps[pid].append((d, mn))

    def regular(pid, d):
        a = [mn for dd, mn in apps.get(pid, []) if dd < d][-10:]
        return len(a) >= 3 and np.mean(a) >= REG_MIN
    reps = defaultdict(lambda: defaultdict(dict))                # (date, team) -> published_at -> {pid: status}
    for pub, d, team, pid, st in n.execute("SELECT published_at, game_date, team, pid, status FROM snapshots WHERE pid IS NOT NULL ORDER BY published_at"):
        reps[(d, team)][pub][int(pid)] = st
    out = []
    for (d, team), by_pub in reps.items():
        gid = games.get((d, team))
        if gid is None:
            continue
        pubs = sorted(by_pub)
        for i, pub in enumerate(pubs):
            if i == 0:
                continue
            prev = by_pub[pubs[i - 1]]
            for pid, st in by_pub[pub].items():
                if not regular(pid, d):
                    continue
                was = prev.get(pid)
                if st in OUTS and was not in OUTS:
                    out.append({"kind": "out", "gid": gid, "date": d, "team": team, "pid": pid, "pub": pub, "was": was or "not listed"})
                elif was == "Questionable" and st == "Available":
                    out.append({"kind": "cleared", "gid": gid, "date": d, "team": team, "pid": pid, "pub": pub, "was": was})
    return out


def main():
    ap = argparse.ArgumentParser()
    for a_ in ("lines_db", "news_db", "matchup_db", "shadow_db"):
        ap.add_argument(a_)
    ap.add_argument("--json")
    a = ap.parse_args()
    ev = events(a.news_db, a.matchup_db)
    q, m = PD._ro(a.lines_db), PD._ro(a.matchup_db)
    team_of = defaultdict(dict)
    for gid, team, pid in m.execute("SELECT gid, team, pid FROM player_games"):
        team_of[gid][pid] = team
    fl = PD._ro(a.shadow_db)
    flag_gids = {g for (g,) in fl.execute("SELECT DISTINCT gid FROM flags WHERE gid IS NOT NULL")} if fl else set()
    gids = sorted({e["gid"] for e in ev} | flag_gids)
    tips = {g: t for g, t in q.execute(f"SELECT gid, MAX(tip_utc) FROM quotes WHERE gid IN ({','.join('?' * len(gids))}) GROUP BY gid", gids)}
    polls = {b: sorted(t for (t,) in q.execute("SELECT ts FROM cycles WHERE book = ? AND status IN ('ok','partial','game')", (b,))) for b in ("fd", "dk")}
    H = histories(a.lines_db, gids)
    by_gid = defaultdict(list)
    for k in H:
        by_gid[k[0]].append(k)
    rows = []
    for e in ev:
        tip = (tips.get(e["gid"]) or "")[:19]
        P = e["pub"][:19]
        if not tip or P >= tip:
            continue
        for k in by_gid[e["gid"]]:
            g, pid, stat, book = k
            if team_of[g].get(pid) is None:
                continue
            same = team_of[g][pid] == e["team"]
            role = "own" if pid == e["pid"] else ("teammate" if same else "opponent")
            h = H[k]
            before = at(h, P)
            if main_of(before)[0] is None:
                continue
            i = bisect.bisect_right(polls[book], P)
            nxt = [t for t in polls[book][i:i + 40] if t < tip]
            first_move = next((t for t in nxt if moved(before, at(h, t))), None)
            pre = at(h, (iso(P) - dt.timedelta(minutes=60)).isoformat())
            rows.append({"event": e["kind"], "role": role, "book": book, "stat": stat,
                         "moved_first_poll": bool(nxt) and moved(before, at(h, nxt[0])),
                         "first_poll_after_s": round(mins(P, nxt[0]) * 60) if nxt else None,
                         "lag_min": round(mins(P, first_move), 1) if first_move else None,
                         "moved_before": bool(main_of(pre)[0]) and moved(pre, before)})
    rep = {}
    for kind in ("out", "cleared"):
        for role in ("teammate", "opponent", "own"):
            for book in ("fd", "dk"):
                r = [x for x in rows if x["event"] == kind and x["role"] == role and x["book"] == book]
                if not r:
                    continue
                lags = [x["lag_min"] for x in r if x["lag_min"] is not None]
                rep[f"{kind}|{role}|{book}"] = {
                    "props": len(r), "events": len({(x['stat']) for x in r}) and None,
                    "moved_by_first_poll": round(np.mean([x["moved_first_poll"] for x in r]), 3),
                    "first_poll_after_s_median": float(np.median([x["first_poll_after_s"] for x in r if x["first_poll_after_s"] is not None])) if any(x["first_poll_after_s"] is not None for x in r) else None,
                    "moved_before_tip": round(len(lags) / len(r), 3),
                    "lag_min_median": float(np.median(lags)) if lags else None,
                    "lag_min_p75": float(np.percentile(lags, 75)) if lags else None,
                    "moved_in_hour_before_report": round(np.mean([x["moved_before"] for x in r]), 3)}
    out = {"events": {k: sum(e["kind"] == k for e in ev) for k in ("out", "cleared")}, "by_cell": rep}
    out["shadow_flags"] = flags_vs_latency(a.shadow_db, H, polls)
    print(json.dumps(out, indent=1))
    if a.json:
        open(a.json, "w").write(json.dumps({"report": out, "rows": rows}, indent=1, default=str))


def flags_vs_latency(shadow_db, H, polls):
    """Each graded shadow flag: minutes from the news to the flag; did FanDuel's main move between the news and the
    flag (already priced) or between the flag and tip (CLV); profit at the flagged odds."""
    s = PD._ro(shadow_db)
    stat_map = {"pts": "points", "reb": "rebounds", "ast": "assists"}
    res = []
    for fid, logged, news_at, gid, pid, stat, line, odds, result, tier, gtime in s.execute(
            "SELECT flag_id, logged_at, news_at, gid, pid, stat, line, odds, result, tier, gtime FROM flags WHERE result IN ('win','loss','push')"):
        st = stat_map.get(stat, stat)
        h = H.get((gid, pid, st, "fd"))
        prof = {"win": odds - 1, "loss": -1.0, "push": 0.0}[result]
        rec = {"tier": tier, "result": result, "profit": prof, "latency_min": round(mins(news_at, logged), 1) if news_at else None}
        if h and news_at:
            before, flag, close = at(h, news_at[:19]), at(h, logged[:19]), at(h, (gtime or "")[:19])
            rec["fd_moved_before_flag"] = moved(before, flag)
            l0, _ = main_of(flag)
            lc, _ = main_of(close)
            rec["fd_close_line_move"] = None if l0 is None or lc is None else lc - l0
        res.append(rec)
    def summ(rr):
        pr = [x["profit"] for x in rr]
        return {"n": len(rr), "roi": round(float(np.mean(pr)), 3) if pr else None,
                "win_rate": round(float(np.mean([x["result"] == "win" for x in rr])), 3) if rr else None}
    out = {"all": summ(res)}
    out["fd_moved_before_flag"] = {str(v): summ([x for x in res if x.get("fd_moved_before_flag") == v]) for v in (True, False, None)}
    out["latency"] = {lab: summ([x for x in res if x["latency_min"] is not None and lo <= x["latency_min"] < hi])
                      for lab, lo, hi in (("<5 min", 0, 5), ("5-30", 5, 30), ("30-120", 30, 120), ("2h+", 120, 1e9))}
    out["close_line_moved_toward_flag (up, for overs)"] = {lab: summ([x for x in res if x.get("fd_close_line_move") is not None and f(x["fd_close_line_move"])])
                                                           for lab, f in (("up", lambda v: v > 0), ("same", lambda v: v == 0), ("down", lambda v: v < 0))}
    out["tier"] = {t: summ([x for x in res if x["tier"] == t]) for t in sorted({x["tier"] for x in res})}
    return out


if __name__ == "__main__":
    main()
