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


def grade(lines_db, matchup_db, out_json=None, since=SINCE, rule="t4", until=None):
    sig, n = (signals(lines_db, matchup_db, since) if rule == "t4" else signals_t5(lines_db, matchup_db, since, until))
    g = [r for r in sig if r["profit"] is not None]
    res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "since": since,
           "rule": f"EV vs FanDuel fair > {EDGE:.0%}" + (" (T4, tip − 30, both sides)" if rule == "t4" else " (T5, earliest, unders)"),
           "signals": len(sig), "graded": len(g), "counts": n, "note": "research only; nothing is bet (NBA_T4_LIVE_PREREG.md)"}
    if g:
        pr = np.array([r["profit"] for r in g])
        dts = [r["date"] for r in g]
        m_, lo, hi = E.boot_ci(pr, dts, reps=4000)
        res["roi"] = {"mean": m_, "lo": lo, "hi": hi}
        for key in ("side", "market"):
            res["by_" + key] = {v: {"n": int(sum(r[key] == v for r in g)), "roi": float(np.mean([r["profit"] for r in g if r[key] == v]))}
                                for v in sorted({r[key] for r in g})}
        if rule == "t5":
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
    ap.add_argument("--rule", choices=("t4", "t5"), default="t4")
    a = ap.parse_args()
    if a.grade:
        r = grade(PD.HERE / "nba_lines.sqlite", PD.HERE / "nba_matchup.sqlite", a.grade, rule=a.rule)
        print("nba_t4_live --grade:", {k: r.get(k) for k in ("signals", "graded", "roi", "verdict")})


if __name__ == "__main__":
    main()
