#!/usr/bin/env python3
"""S1, the news-window signal (NBA_S1_PREREG.md). Research only: nothing is bet, nothing is shown as a pick.
    python3 nba_news_window.py --process            # every minute: new reports -> S1 signals (news_signals)
    python3 nba_news_window.py --grade OUT_JSON     # nightly: CLV vs FanDuel at tip − 30, ROI, decision lines
"""
import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np

import nba_news_latency as NL
import nba_proj11 as P
import nba_proj11_live as L
import nba_proj_data as PD
import nba_proj_eval as E
import nba_project as NP

HERE = PD.HERE
EDGE, CUT_MIN, NEED_CLV, NEED_ROI = 0.05, 30, 300, 500
MARKETS = ("points", "rebounds", "assists", "threes", "pts_reb", "pts_ast", "reb_ast", "pra")
DDL = ["CREATE TABLE IF NOT EXISTS news_signals (mark TEXT, published_at TEXT, observed_at TEXT, gid TEXT, pid INTEGER, "
       "market TEXT, line REAL, over REAL, under REAL, p_fd REAL, p_model REAL, edge REAL, out_pid INTEGER, version TEXT, "
       "logged_at TEXT, PRIMARY KEY (mark, gid, pid, market))",
       "CREATE TABLE IF NOT EXISTS s1_processed (mark TEXT PRIMARY KEY, processed_at TEXT, n_events INTEGER, n_signals INTEGER)"]


def model_probs(cfg, hit, lineups, status, wanted):
    """{(gid, pid, market, line): P(over | no push)} from the proj cache with F0's game-day inputs as given."""
    Xt, _ = L.live_inputs(hit, lineups, status)
    f = ((Xt - hit["wmu"]) / hit["wsd"]) @ hit["W"]
    mu = L.recalibrate(P.apply_residual(hit["mu10"], f), cfg)
    tf = NP.features(mu, np.array(hit["n_hist"], float), np.array(hit["rest"], float), NP.PROJ_CONFIG)
    nb = NP.neighbors(tf, hit["pool_f"], NP.PROJ_CONFIG["K"], hit["scale"])
    d = NP.Dist(mu, hit["pool_mu"], hit["pool_y"], nb)
    out = {}
    for g, p, mk, line in wanted:
        j = hit["at"].get((g, p))
        if j is None:
            continue
        sub = NP.Dist.__new__(NP.Dist)
        sub.vals, sub.mu = d.vals[j:j + 1], d.mu[j:j + 1]
        po, pu, _ = sub.probs(mk, [line])
        out[(g, p, mk, line)] = float(po[0] / max(po[0] + pu[0], 1e-9))
    return out


def candidates(lines_db, gid, team_pids, P_, obs):
    """Teammate props whose FanDuel main line and no-vig P(over) at `obs` equal those just before P_ (stale)."""
    H = NL.histories(lines_db, [gid])
    out = []
    for (g, pid, stat, book), h in H.items():
        if book != "fd" or pid not in team_pids or stat not in MARKETS:
            continue
        before, now = NL.at(h, P_), NL.at(h, obs)
        lb, pb = NL.main_of(before)
        ln, pn = NL.main_of(now)
        if lb is None or ln is None or lb != ln or abs(pn - pb) >= 1e-9 or NL.moved(before, now):
            continue
        out.append({"gid": g, "pid": pid, "market": stat, "line": ln, "over": now[(ln, "over")], "under": now[(ln, "under")], "p_fd": pn})
    return out


def process(now=None, news_db=HERE / "nba_news.sqlite", lines_db=HERE / "nba_lines.sqlite", log_db=HERE / "nba_proj_log.sqlite",
            matchup_db=HERE / "nba_matchup.sqlite", cfg_path=L.CONFIG, cache=L.CACHE, model_fn=None, lineups_db=L.LINEUPS):
    """Log S1 signals for every new report trigger whose lines have been fetched. Returns a status line."""
    import sqlite3
    now = now or dt.datetime.now(dt.timezone.utc)
    con = sqlite3.connect(log_db, timeout=30)
    for d_ in DDL:
        con.execute(d_)
    done = {m for (m,) in con.execute("SELECT mark FROM s1_processed")}
    n = PD._ro(news_db)
    trig = [(m, pub, la) for m, pub, la in n.execute("SELECT mark, published_at, lines_at FROM triggers WHERE lines_at IS NOT NULL ORDER BY published_at")
            if m not in done]
    if not trig:
        return "no new report"
    cfg = L.load_config(cfg_path)
    hit = L._load(cache) if model_fn is None else None
    q = PD._ro(lines_db)
    ev_all = NL.events(news_db, matchup_db)
    total = 0
    for mark, pub, la in trig:
        ev = [e for e in ev_all if e["kind"] == "out" and e["pub"] == pub]
        sigs = []
        for e in ev:
            tip = (q.execute("SELECT MAX(tip_utc) FROM quotes WHERE gid = ?", (e["gid"],)).fetchone()[0] or "")[:19]
            if not tip or NL.iso(la) >= NL.iso(tip) - dt.timedelta(minutes=CUT_MIN):
                continue
            if model_fn is None and hit is not None:
                team_pids = {t["pid"] for t in hit["slate"] if t["gid"] == e["gid"] and t["team"] == e["team"] and t["pid"] != e["pid"]}
            else:
                team_pids = None
            obs = NL.iso(la).strftime("%Y-%m-%dT%H:%M:%S")
            cands = candidates(lines_db, e["gid"], team_pids if team_pids is not None else _team_pids(matchup_db, e), pub[:19], obs)
            if not cands:
                continue
            wanted = [(c["gid"], c["pid"], c["market"], c["line"]) for c in cands]
            if model_fn is not None:
                mp = model_fn(e, wanted)
            elif hit is not None and hit.get("version") == cfg["version"]:
                mp = model_probs(cfg, hit, L.latest_lineups(lineups_db, NL.iso(la).replace(tzinfo=dt.timezone.utc)),
                                 L.latest_status(news_db, NL.iso(la).replace(tzinfo=dt.timezone.utc), {e["date"]}), wanted)
            else:
                mp = {}
            for c in cands:
                pm = mp.get((c["gid"], c["pid"], c["market"], c["line"]))
                if pm is not None and pm - c["p_fd"] >= EDGE:
                    sigs.append(dict(c, p_model=pm, edge=pm - c["p_fd"], out_pid=e["pid"]))
        stamp = now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for s in sigs:
            con.execute("INSERT OR IGNORE INTO news_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (mark, pub, la, s["gid"], s["pid"], s["market"], s["line"], s["over"], s["under"], s["p_fd"], s["p_model"],
                         s["edge"], s["out_pid"], cfg["version"], stamp))
        con.execute("INSERT OR REPLACE INTO s1_processed VALUES (?,?,?,?)", (mark, stamp, len(ev), len(sigs)))
        total += len(sigs)
    con.commit()
    con.close()
    return f"processed {len(trig)} report(s), logged {total} S1 signal(s)"


def _team_pids(matchup_db, e):
    m = PD._ro(matchup_db)
    return {p for (p,) in m.execute("SELECT pid FROM player_games WHERE gid = ? AND team = ?", (e["gid"], e["team"])) if p != e["pid"]}


def grade(log_db=HERE / "nba_proj_log.sqlite", lines_db=HERE / "nba_lines.sqlite", matchup_db=HERE / "nba_matchup.sqlite", out_json=None):
    lg, m, q = PD._ro(log_db), PD._ro(matchup_db), PD._ro(lines_db)
    res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "rule": "S1 (NBA_S1_PREREG.md)",
           "note": "research only; nothing is bet", "signals": 0, "graded": 0}
    if lg is None or not lg.execute("SELECT 1 FROM sqlite_master WHERE name = 'news_signals'").fetchone():
        res["verdict"] = f"not enough prospective evidence (0 of {NEED_CLV} graded signals)"
        if out_json:
            Path(out_json).write_text(json.dumps(res))
        return res
    sig = [dict(zip(("mark", "pub", "obs", "gid", "pid", "market", "line", "over", "under", "p_fd", "p_model", "edge"), r))
           for r in lg.execute("SELECT mark, published_at, observed_at, gid, pid, market, line, over, under, p_fd, p_model, edge FROM news_signals")]
    res["signals"] = len(sig)
    final = {g: d for g, d in m.execute("SELECT gid, date FROM games WHERE home_pts IS NOT NULL")}
    box = {(g, p): (mn, {"pts": a, "reb": b, "ast": c, "fg3m": d, "stl": e, "blk": f, "tov": h}) for g, p, mn, a, b, c, d, e, f, h in
           m.execute("SELECT gid, pid, min, pts, reb, ast, fg3m, stl, blk, tov FROM player_games")}
    gids = sorted({s["gid"] for s in sig} & set(final))
    H = NL.histories(lines_db, gids) if gids else {}
    rows = []
    for s in sig:
        if s["gid"] not in final:
            continue
        mn, st = box.get((s["gid"], s["pid"]), (None, None))
        if not mn:
            continue
        actual = sum(st[c] for c in PD.MARKET_PARTS[s["market"]])
        tip = (q.execute("SELECT MAX(tip_utc) FROM quotes WHERE gid = ?", (s["gid"],)).fetchone()[0] or "")[:19]
        cut = (NL.iso(tip) - dt.timedelta(minutes=CUT_MIN)).strftime("%Y-%m-%dT%H:%M:%S") if tip else None
        close = NL.at(H.get((s["gid"], s["pid"], s["market"], "fd"), []), cut) if cut else {}
        o, u = close.get((s["line"], "over")), close.get((s["line"], "under"))
        clv = float(NP.no_vig(o, u)) - s["p_fd"] if o and u else None
        prof = 0.0 if actual == s["line"] else (s["over"] - 1 if actual > s["line"] else -1.0)
        rows.append({"date": final[s["gid"]], "clv": clv, "profit": prof, "market": s["market"], "edge": s["edge"]})
    res["graded"] = len(rows)
    if rows:
        cl = [(r["clv"], r["date"]) for r in rows if r["clv"] is not None]
        if cl:
            m_, lo, hi = E.boot_ci([c for c, _ in cl], [d for _, d in cl], reps=4000)
            res["clv"] = {"n": len(cl), "mean": m_, "lo": lo, "hi": hi}
        pr = [r["profit"] for r in rows]
        m2, lo2, hi2 = E.boot_ci(pr, [r["date"] for r in rows], reps=4000)
        res["roi"] = {"n": len(pr), "mean": m2, "lo": lo2, "hi": hi2}
        res["by_market"] = {mk: {"n": sum(r["market"] == mk for r in rows), "roi": float(np.mean([r["profit"] for r in rows if r["market"] == mk]))}
                            for mk in sorted({r["market"] for r in rows})}
    if len(rows) < NEED_CLV:
        res["verdict"] = f"not enough prospective evidence ({len(rows)} of {NEED_CLV} graded signals)"
    else:
        c = res.get("clv")
        clv_ok = bool(c and c["lo"] > 0)
        roi_txt = ("ROI " + ("lower bound > 0" if res["roi"]["lo"] > 0 else "interval reaches 0")) if len(rows) >= NEED_ROI else f"ROI read at {NEED_ROI}"
        res["verdict"] = ("CLV YES" if clv_ok else "CLV NO") + f"; {roi_txt}"
    if out_json:
        tmp = Path(str(out_json) + ".tmp")
        tmp.write_text(json.dumps(res, default=float))
        tmp.replace(out_json)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", action="store_true")
    ap.add_argument("--grade", metavar="OUT_JSON")
    a = ap.parse_args()
    if a.process:
        print(dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "nba_news_window --process:", process())
    if a.grade:
        r = grade(out_json=a.grade)
        print("nba_news_window --grade:", {k: r.get(k) for k in ("signals", "graded", "clv", "roi", "verdict")})


if __name__ == "__main__":
    main()
