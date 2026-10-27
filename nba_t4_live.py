#!/usr/bin/env python3
"""T4-live (NBA_T4_LIVE_PREREG.md): DraftKings against FanDuel's fair price at tip − 30, forward only. Research only,
nothing is bet and nothing is shown as a pick.
    python3 nba_t4_live.py --grade OUT_JSON       # nightly: signals from the quote change log, graded on box scores
"""
import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np

import nba_proj_data as PD
import nba_proj_eval as E
import nba_project as NP

SINCE = "2026-10-28"                          # games tipping on/after this ET date (the prereg's start)
EDGE, CUT_MIN, NEED, REPL = 0.02, 30, 500, 500


def _iso(t):
    return dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))


def signals(lines_db, matchup_db, since=SINCE):
    """[signal dicts] for final games since `since`: board at tip − 30, FanDuel two-sided, DraftKings same line, EV > 2%."""
    import nba_research as R
    q, m = PD._ro(lines_db), PD._ro(matchup_db)
    if q is None or m is None:
        return [], {"error": "missing store"}
    final = {g: d for g, d in m.execute("SELECT gid, date FROM games WHERE home_pts IS NOT NULL AND date >= ?", (since,))}
    if not final:
        return [], {}
    marks = ",".join("?" * len(final))
    tips = {g: _iso(t) for g, t in q.execute(f"SELECT gid, MAX(tip_utc) FROM quotes WHERE gid IN ({marks}) GROUP BY gid", list(final)) if t}
    cut, tip_s, n = {}, {}, {"void_postponed": 0}
    for g, t in tips.items():
        if E._et_date(t.isoformat()) != final[g]:
            n["void_postponed"] += 1
            continue
        cut[g] = (t - dt.timedelta(minutes=CUT_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        tip_s[g] = t.strftime("%Y-%m-%dT%H:%M:%S")
    box = {(g, p): (mn, {"pts": a, "reb": b, "ast": c, "fg3m": d, "stl": e, "blk": f, "tov": h}) for g, p, mn, a, b, c, d, e, f, h in
           m.execute(f"SELECT gid, pid, min, pts, reb, ast, fg3m, stl, blk, tov FROM player_games WHERE gid IN ({marks})", list(final))}
    rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN ({marks}) "
                     f"AND book IN ('fd', 'dk') AND pid IS NOT NULL ORDER BY seen_at", list(final))
    board, last = {}, {}
    for t, changed in R.replay(r for r in rows if r[4] in PD.MARKET_PARTS):
        for k, st in changed.items():
            g = k[0]
            if g in cut and t <= cut[g]:
                board[k] = dict(st)
            if g in tip_s and t < tip_s[g]:
                last[k] = dict(st)
    out = []
    for (g, p, stat, book), st in board.items():
        if book != "fd":
            continue
        dk = board.get((g, p, stat, "dk")) or {}
        for (line, side), fo in st.items():
            fu = st.get((line, "under"))
            if side != "over" or not fo or not fu:
                continue
            pf = float(NP.no_vig(fo, fu))
            for s, ps in (("over", pf), ("under", 1 - pf)):
                o = dk.get((line, s))
                if not o or ps * o - 1 <= EDGE:
                    continue
                mn, stats = box.get((g, p), (None, None))
                lst = last.get((g, p, stat, "fd")) or {}
                lo, lu = lst.get((line, "over")), lst.get((line, "under"))
                clv = None
                if lo and lu:
                    pc = float(NP.no_vig(lo, lu))
                    clv = (pc - pf) if s == "over" else (pf - pc)
                rec = {"gid": g, "pid": p, "market": stat, "line": line, "side": s, "odds": o, "ev_fd": ps * o - 1,
                       "tip": tip_s[g], "date": final[g], "clv": clv}
                if not mn:
                    rec["result"] = "void"
                else:
                    actual = sum(stats[c] for c in PD.MARKET_PARTS[stat])
                    rec["result"] = "push" if actual == line else ("win" if (actual > line) == (s == "over") else "loss")
                rec["profit"] = {"void": None, "push": 0.0, "win": o - 1, "loss": -1.0}[rec["result"]]
                out.append(rec)
    return sorted(out, key=lambda r: (r["tip"], r["gid"], r["pid"], r["market"], r["side"])), n


def signals_t5(lines_db, matchup_db, since=SINCE, until=None):
    """T5 (NBA_T5_PREREG.md): replay the day's change log until tip − 30; the FIRST moment DraftKings' under at a
    line L beats FanDuel's no-vig under at L by EV > 2% gives one signal per player-game and market."""
    import nba_research as R
    q, m = PD._ro(lines_db), PD._ro(matchup_db)
    if q is None or m is None:
        return [], {"error": "missing store"}
    sql = "SELECT gid, date FROM games WHERE home_pts IS NOT NULL AND date >= ?" + (" AND date <= ?" if until else "")
    final = {g: d for g, d in m.execute(sql, (since, until) if until else (since,))}
    if not final:
        return [], {}
    marks = ",".join("?" * len(final))
    tips = {g: _iso(t) for g, t in q.execute(f"SELECT gid, MAX(tip_utc) FROM quotes WHERE gid IN ({marks}) GROUP BY gid", list(final)) if t}
    cut, tip_s, n = {}, {}, {"void_postponed": 0}
    for g, t in tips.items():
        if E._et_date(t.isoformat()) != final[g]:
            n["void_postponed"] += 1
            continue
        cut[g] = (t - dt.timedelta(minutes=CUT_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        tip_s[g] = t.strftime("%Y-%m-%dT%H:%M:%S")
    box = {(g, p): (mn, {"pts": a, "reb": b, "ast": c, "fg3m": d, "stl": e, "blk": f, "tov": h}) for g, p, mn, a, b, c, d, e, f, h in
           m.execute(f"SELECT gid, pid, min, pts, reb, ast, fg3m, stl, blk, tov FROM player_games WHERE gid IN ({marks})", list(final))}
    rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN ({marks}) "
                     f"AND book IN ('fd', 'dk') AND pid IS NOT NULL ORDER BY seen_at", list(final))
    cur, last, sig = {}, {}, {}
    for t, changed in R.replay(r for r in rows if r[4] in PD.MARKET_PARTS):
        for k, st in changed.items():
            g, p, stat, book = k
            if g in tip_s and t < tip_s[g]:
                last[k] = dict(st)
            if g not in cut or t > cut[g]:
                continue
            cur[k] = dict(st)
            if (g, p, stat) in sig:
                continue
            fd, dk = cur.get((g, p, stat, "fd")) or {}, cur.get((g, p, stat, "dk")) or {}
            for (line, side), du in sorted(dk.items()):
                if side != "under" or not du:
                    continue
                fo, fu = fd.get((line, "over")), fd.get((line, "under"))
                if not fo or not fu:
                    continue
                pu = 1 - float(NP.no_vig(fo, fu))
                if pu * du - 1 > EDGE:
                    sig[(g, p, stat)] = {"gid": g, "pid": p, "market": stat, "line": line, "side": "under", "odds": du,
                                         "ev_fd": pu * du - 1, "p_fd": pu, "seen_at": t, "tip": tip_s[g], "date": final[g],
                                         "min_before_tip": round((_iso(tip_s[g] + "+00:00") - _iso(t + "+00:00")).total_seconds() / 60)}
                    break
    out = []
    for (g, p, stat), rec in sig.items():
        lst = last.get((g, p, stat, "fd")) or {}
        lo, lu = lst.get((rec["line"], "over")), lst.get((rec["line"], "under"))
        rec["clv"] = (1 - float(NP.no_vig(lo, lu))) - rec["p_fd"] if lo and lu else None
        mn, stats = box.get((g, p), (None, None))
        if not mn:
            rec["result"] = "void"
        else:
            actual = sum(stats[c] for c in PD.MARKET_PARTS[stat])
            rec["result"] = "push" if actual == rec["line"] else ("win" if actual < rec["line"] else "loss")
        rec["profit"] = {"void": None, "push": 0.0, "win": rec["odds"] - 1, "loss": -1.0}[rec["result"]]
        out.append(rec)
    return sorted(out, key=lambda r: (r["tip"], r["gid"], r["pid"], r["market"])), n


UNCLEAN = ("Questionable", "Doubtful", "Probable")


def _hist(lines_db, gids):
    """{(gid, pid, stat, book): [(t, state)]} for FanDuel and DraftKings, from the change log."""
    import nba_research as R
    q = PD._ro(lines_db)
    marks = ",".join("?" * len(gids))
    rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN ({marks}) "
                     f"AND book IN ('fd', 'dk') AND pid IS NOT NULL ORDER BY seen_at", list(gids))
    h = {}
    for t, changed in R.replay(r for r in rows if r[4] in PD.MARKET_PARTS):
        for k, st in changed.items():
            h.setdefault(k, []).append((t, dict(st)))
    return h


def _at(hist, t):
    import bisect
    ts = [x[0] for x in hist]
    i = bisect.bisect_right(ts, t) - 1
    return hist[i][1] if i >= 0 else {}


def model_pmf_before(log_db, version, gid, pid, market, t):
    """The newest logged forecast pmf for (gid, pid, market) made at or before t: its 'cutoff' row if logged by t,
    else its 'first' row if logged by t, else None."""
    lg = PD._ro(log_db)
    if lg is None or not lg.execute("SELECT 1 FROM sqlite_master WHERE name = 'forecast_pmf'").fetchone():
        return None
    best = None
    for kind, at in lg.execute("SELECT kind, logged_at FROM forecasts WHERE gid = ? AND pid = ? AND market = ? AND version = ?",
                               (gid, pid, market, version)):
        if at <= t and (best is None or at > best[1]):
            best = (kind, at)
    if best is None:
        return None
    r = lg.execute("SELECT pmf FROM forecast_pmf WHERE kind = ? AND gid = ? AND pid = ? AND market = ? AND version = ?",
                   (best[0], gid, pid, market, version)).fetchone()
    return json.loads(r[0]) if r else None


def signals_t5b(lines_db, matchup_db, news_db, since=SINCE, until=None, model_p_under=None, log_db=None, version=None):
    """T5b (NBA_T5B_PREREG.md): T5's first trigger, kept only if (1) the edge still holds at FanDuel's next successful
    poll (placed then, at DraftKings' price then), (2) the player is not Questionable/Doubtful/Probable in the newest
    report before it, (3) the model's P(under | no push) at the line beats FanDuel's. model_p_under(sig, t) -> float or
    None; live it comes from the newest proj-1.2 pmf logged before t (log_db, version)."""
    import bisect
    trig, n = signals_t5(lines_db, matchup_db, since, until)
    if not trig:
        return [], n
    q, m, nw = PD._ro(lines_db), PD._ro(matchup_db), PD._ro(news_db)
    polls = sorted(t for (t,) in q.execute("SELECT ts FROM cycles WHERE book = 'fd' AND status IN ('ok', 'partial', 'game')"))
    hist = _hist(lines_db, sorted({s["gid"] for s in trig}))
    team = {(g, p): t for g, t, p in m.execute("SELECT gid, team, pid FROM player_games")}
    box = {(g, p): (mn, {"pts": a, "reb": b, "ast": c, "fg3m": d, "stl": e, "blk": f, "tov": h}) for g, p, mn, a, b, c, d, e, f, h in
           m.execute("SELECT gid, pid, min, pts, reb, ast, fg3m, stl, blk, tov FROM player_games")}
    if model_p_under is None and log_db is not None:
        def model_p_under(sg, t):
            pm = model_pmf_before(log_db, version, sg["gid"], sg["pid"], sg["market"], t)
            return None if pm is None else 1 - E.p_at(pm, sg["line"])
    out, n = [], dict(n, fail_confirm=0, fail_status=0, fail_model=0)
    for s in trig:
        g, p, stat, L = s["gid"], s["pid"], s["market"], s["line"]
        i = bisect.bisect_right(polls, s["seen_at"])
        tc = polls[i] if i < len(polls) else None
        cut = (_iso(s["tip"] + "+00:00") - dt.timedelta(minutes=CUT_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        if tc is None or tc > cut:
            n["fail_confirm"] += 1
            continue
        fd, dk = _at(hist.get((g, p, stat, "fd"), []), tc), _at(hist.get((g, p, stat, "dk"), []), tc)
        fo, fu, du = fd.get((L, "over")), fd.get((L, "under")), dk.get((L, "under"))
        if not (fo and fu and du) or (1 - float(NP.no_vig(fo, fu))) * du - 1 <= EDGE:
            n["fail_confirm"] += 1
            continue
        pu = 1 - float(NP.no_vig(fo, fu))
        st = None
        if nw is not None:
            for pub, status in nw.execute("SELECT published_at, status FROM snapshots WHERE game_date = ? AND team = ? AND pid = ? "
                                          "ORDER BY published_at", (s["date"], team.get((g, p)), p)):
                if pub <= tc + "+00:00":
                    st = status
        if st in UNCLEAN:
            n["fail_status"] += 1
            continue
        mp = model_p_under(s, tc) if model_p_under else None
        if mp is None or mp <= pu:
            n["fail_model"] += 1
            continue
        lst = _at(hist.get((g, p, stat, "fd"), []), s["tip"])
        lo, lu = lst.get((L, "over")), lst.get((L, "under"))
        rec = dict(s, seen_at=tc, odds=du, p_fd=pu, ev_fd=pu * du - 1, model_p_under=mp, own_status=st,
                   min_before_tip=round((_iso(s["tip"] + "+00:00") - _iso(tc + "+00:00")).total_seconds() / 60),
                   clv=(1 - float(NP.no_vig(lo, lu))) - pu if lo and lu else None)
        mn, stats = box.get((g, p), (None, None))
        if not mn:
            rec["result"] = "void"
        else:
            actual = sum(stats[c] for c in PD.MARKET_PARTS[stat])
            rec["result"] = "push" if actual == L else ("win" if actual < L else "loss")
        rec["profit"] = {"void": None, "push": 0.0, "win": du - 1, "loss": -1.0}[rec["result"]]
        out.append(rec)
    return out, n


def grade(lines_db, matchup_db, out_json=None, since=SINCE, rule="t4", until=None, news_db=None, log_db=None, version=None,
          model_p_under=None):
    if rule == "t4":
        sig, n = signals(lines_db, matchup_db, since)
    elif rule == "t5":
        sig, n = signals_t5(lines_db, matchup_db, since, until)
    else:
        sig, n = signals_t5b(lines_db, matchup_db, news_db, since, until, model_p_under=model_p_under, log_db=log_db, version=version)
    g = [r for r in sig if r["profit"] is not None]
    res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "since": since,
           "rule": f"EV vs FanDuel fair > {EDGE:.0%}" + {"t4": " (T4, tip − 30, both sides)", "t5": " (T5, earliest, unders)",
                                                           "t5b": " (T5b: T5 + confirmation, clean status, model agrees)"}[rule],
           "signals": len(sig), "graded": len(g), "counts": n, "note": "research only; nothing is bet (NBA_T4_LIVE_PREREG.md)"}
    if g:
        pr = np.array([r["profit"] for r in g])
        dts = [r["date"] for r in g]
        m_, lo, hi = E.boot_ci(pr, dts, reps=4000)
        res["roi"] = {"mean": m_, "lo": lo, "hi": hi}
        for key in ("side", "market"):
            res["by_" + key] = {v: {"n": int(sum(r[key] == v for r in g)), "roi": float(np.mean([r["profit"] for r in g if r[key] == v]))}
                                for v in sorted({r[key] for r in g})}
        if rule in ("t5", "t5b"):
            res["by_timing"] = {}
            for lab, lo_, hi_ in (("6h+", 360, 1e9), ("2-6h", 120, 360), ("<2h", 0, 120)):
                k = [r for r in g if lo_ <= r["min_before_tip"] < hi_]
                if k:
                    res["by_timing"][lab] = {"n": len(k), "roi": float(np.mean([r["profit"] for r in k]))}
        cl = [r["clv"] for r in g if r["clv"] is not None]
        if cl:
            res["clv"] = {"n": len(cl), "mean": float(np.mean(cl)), "share_positive": float(np.mean(np.array(cl) > 0))}
    if len(g) < NEED:
        res["verdict"] = f"not enough prospective evidence ({len(g)} of {NEED} graded signals)"
    else:
        first = np.array([r["profit"] for r in g[:NEED]])
        m1, lo1, hi1 = E.boot_ci(first, [r["date"] for r in g[:NEED]], reps=4000)
        res["decision_first_500"] = {"mean": m1, "lo": lo1, "hi": hi1}
        if lo1 <= 0:
            res["verdict"] = "NO: first 500 signals' ROI interval reaches 0"
        elif len(g) < NEED + REPL:
            res["verdict"] = f"first 500 pass; waiting on the replication window ({len(g) - NEED} of {REPL})"
        else:
            r2 = float(np.mean([r["profit"] for r in g[NEED:NEED + REPL]]))
            res["replication_roi"] = r2
            res["verdict"] = "YES: first 500 pass and the replication window is positive" if r2 > 0 else "NO: replication window not positive"
    if out_json:
        tmp = Path(str(out_json) + ".tmp")
        tmp.write_text(json.dumps(res, default=float))
        tmp.replace(out_json)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grade", metavar="OUT_JSON")
    ap.add_argument("--rule", choices=("t4", "t5", "t5b"), default="t4")
    a = ap.parse_args()
    if a.grade:
        kw = {}
        if a.rule == "t5b":
            import nba_proj11_live as L
            kw = dict(news_db=PD.HERE / "nba_news.sqlite", log_db=PD.HERE / "nba_proj_log.sqlite",
                      version=L.load_config(PD.HERE / "nba_proj12_config.json")["version"])
        r = grade(PD.HERE / "nba_lines.sqlite", PD.HERE / "nba_matchup.sqlite", a.grade, rule=a.rule, **kw)
        print("nba_t4_live --grade:", {k: r.get(k) for k in ("signals", "graded", "roi", "verdict")})


if __name__ == "__main__":
    main()
