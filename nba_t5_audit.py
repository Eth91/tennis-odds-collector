#!/usr/bin/env python3
"""Why did T5 lose in its development look? (NBA_T5_PREREG.md, games 2026-10-22..25.) An audit of the signals, not a
new test: every split here is post hoc on about 255 signals, so a split that looks good is a hypothesis for a new
pre-registration, never a result.

Per signal:
- which book's move triggered it;
- how stale FanDuel's price was: minutes since FanDuel's last successful poll;
- what FanDuel showed at its next poll;
- whether FanDuel's main line moved later, and which way;
- whether official-report news for the player or a teammate landed after the signal;
- proj-1.1.1's own P(under) at the same line;
- EV size, market and timing.
    python3 nba_t5_audit.py LINES_DB MATCHUP_DB NEWS_DB [--json OUT]
"""
import argparse
import bisect
import datetime as dt
import json
import pickle
from collections import defaultdict

import numpy as np

import nba_proj11 as P
import nba_proj11_feat as FT
import nba_proj_data as PD
import nba_proj_eval as E
import nba_project as NP
import nba_t4_live as T


def fd_polls(lines_db):
    q = PD._ro(lines_db)
    return sorted(t for (t,) in q.execute("SELECT ts FROM cycles WHERE book = 'fd' AND status IN ('ok', 'partial', 'game')"))


def fd_history(lines_db, gids):
    """{(gid, pid, stat): [(t, FanDuel state)]} in time order, from the change log."""
    import nba_research as R
    q = PD._ro(lines_db)
    marks = ",".join("?" * len(gids))
    rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN ({marks}) "
                     f"AND book = 'fd' AND pid IS NOT NULL ORDER BY seen_at", list(gids))
    h = defaultdict(list)
    for t, changed in R.replay(r for r in rows if r[4] in PD.MARKET_PARTS):
        for k, st in changed.items():
            h[k[:3]].append((t, dict(st)))
    return h


def state_at(hist, t):
    ts = [x[0] for x in hist]
    i = bisect.bisect_right(ts, t) - 1
    return hist[i][1] if i >= 0 else {}


def p_under(st, line):
    o, u = st.get((line, "over")), st.get((line, "under"))
    return 1 - float(NP.no_vig(o, u)) if o and u else None


def main_line(st):
    two = [ln for (ln, s) in st if s == "over" and st.get((ln, "under")) and st.get((ln, "over"))]
    return min(two, key=lambda ln: abs(p_under(st, ln) - .5)) if two else None


def model_p_under(signals):
    """proj-1.1.1's P(under | no push) at each signal's line, from the walk-forward evaluation rows (2026-27)."""
    data = E.load()
    rows = data["rows"]
    run = E.Run(rows, NP.PROJ_CONFIG, NP.context_constants(rows))
    X, *_ = FT.build(rows, families=("F0",), f0_rule="1.1.1")
    arm = P.arm_run(run, P.apply_residual(run.mu["m1"], P.residual_walk(run.date, X.astype(float), P.residual_targets(run), 10)))
    key = {(r["gid"], r["pid"]): i for i, r in enumerate(rows)}
    need = sorted({key[(s["gid"], s["pid"])] for s in signals if (s["gid"], s["pid"]) in key})
    out = {}
    if not need:
        return out
    idx = np.array(need)
    d = arm.dist(idx)
    pos = {i: j for j, i in enumerate(idx)}
    for s in signals:
        i = key.get((s["gid"], s["pid"]))
        if i is None:
            continue
        sub = NP.Dist.__new__(NP.Dist)
        sub.vals, sub.mu = d.vals[pos[i]:pos[i] + 1], d.mu[pos[i]:pos[i] + 1]
        po, pu, _ = sub.probs(s["market"], [s["line"]])
        out[(s["gid"], s["pid"], s["market"])] = float(pu[0] / max(po[0] + pu[0], 1e-9))
    return out


def news_after(news_db, matchup_db, signals):
    """For each signal: did an official-report status change for the player or a teammate land after the signal and
    before tip? Returns {key: {"own": status change or None, "mates_out": n teammates newly Out/Doubtful}}."""
    n, m = PD._ro(news_db), PD._ro(matchup_db)
    team = {(g, p): t for g, t, p in m.execute("SELECT gid, team, pid FROM player_games")}
    snaps = defaultdict(list)
    for pub, d, tm, pid, status in n.execute("SELECT published_at, game_date, team, pid, status FROM snapshots WHERE pid IS NOT NULL ORDER BY published_at"):
        snaps[(d, tm)].append((pub, int(pid), status))
    out = {}
    for s in signals:
        tm = team.get((s["gid"], s["pid"]))
        tsig = s["seen_at"] + "+00:00"
        ttip = s["tip"] + "+00:00"
        before, after = {}, {}
        for pub, pid, st in snaps.get((s["date"], tm), []):
            (before if pub <= tsig else after if pub < ttip else {})[pid] = st
        own_b, own_a = before.get(s["pid"]), after.get(s["pid"])
        newly_out = [p for p, st in after.items() if p != s["pid"] and st in ("Out", "Doubtful") and before.get(p) not in ("Out", "Doubtful")]
        out[(s["gid"], s["pid"], s["market"])] = {"own": f"{own_b}->{own_a}" if own_a and own_a != own_b else None,
                                                   "mates_newly_out": len(newly_out)}
    return out


def roi(sel):
    pr = [s["profit"] for s in sel if s["profit"] is not None]
    return {"n": len(pr), "roi": round(float(np.mean(pr)), 3) if pr else None,
            "clv": round(float(np.mean([s["clv"] for s in sel if s.get("clv") is not None])), 4) if any(s.get("clv") is not None for s in sel) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines_db"); ap.add_argument("matchup_db"); ap.add_argument("news_db")
    ap.add_argument("--json")
    a = ap.parse_args()
    sig, _ = T.signals_t5(a.lines_db, a.matchup_db, since="2026-10-22", until="2026-10-27")
    sig = [s for s in sig if s["profit"] is not None]
    polls = fd_polls(a.lines_db)
    hist = fd_history(a.lines_db, sorted({s["gid"] for s in sig}))
    mp = model_p_under(sig)
    nw = news_after(a.news_db, a.matchup_db, sig)
    for s in sig:
        k = (s["gid"], s["pid"], s["market"])
        h = hist.get(k, [])
        i = bisect.bisect_right(polls, s["seen_at"]) - 1
        s["fd_age_min"] = round((dt.datetime.fromisoformat(s["seen_at"]) - dt.datetime.fromisoformat(polls[i])).total_seconds() / 60, 1) if i >= 0 else None
        nxt = polls[i + 1] if i + 1 < len(polls) else None
        s["trigger"] = "fd_change" if any(t == s["seen_at"] for t, _ in h) else "dk_change"
        pu_next = p_under(state_at(h, nxt), s["line"]) if nxt and nxt < s["tip"] else None
        s["fd_next_poll_toward_dk"] = None if pu_next is None else bool(pu_next > s["p_fd"] + 0.005)
        st_sig, st_close = state_at(h, s["seen_at"]), state_at(h, s["tip"])
        ml0, ml1 = main_line(st_sig), main_line(st_close)
        s["fd_main_move"] = None if ml0 is None or ml1 is None else ("up" if ml1 > ml0 else "down" if ml1 < ml0 else "same")
        s["model_p_under"] = mp.get(k)
        s["model_agrees"] = None if s["model_p_under"] is None else bool(s["model_p_under"] > s["p_fd"])
        s.update(nw.get(k, {}))
    rep = {"n": len(sig), "all": roi(sig)}
    splits = {
        "trigger": lambda s: s["trigger"],
        "fd_age": lambda s: None if s["fd_age_min"] is None else ("<5 min" if s["fd_age_min"] < 5 else "5-10" if s["fd_age_min"] < 10.5 else ">10"),
        "fd_next_poll_toward_dk": lambda s: s["fd_next_poll_toward_dk"],
        "fd_main_move_after": lambda s: s["fd_main_move"],
        "model_agrees": lambda s: s["model_agrees"],
        "own_status_change": lambda s: s.get("own") is not None,
        "teammate_newly_out": lambda s: (s.get("mates_newly_out") or 0) > 0,
        "ev": lambda s: "2-4%" if s["ev_fd"] < .04 else "4-8%" if s["ev_fd"] < .08 else "8%+",
        "timing": lambda s: "6h+" if s["min_before_tip"] >= 360 else "2-6h" if s["min_before_tip"] >= 120 else "<2h",
        "market": lambda s: s["market"],
    }
    for name, f in splits.items():
        groups = defaultdict(list)
        for s in sig:
            groups[str(f(s))].append(s)
        rep[name] = {g: roi(v) for g, v in sorted(groups.items())}
    print(json.dumps(rep, indent=1))
    if a.json:
        open(a.json, "w").write(json.dumps({"report": rep, "signals": sig}, indent=1, default=str))


if __name__ == "__main__":
    main()
