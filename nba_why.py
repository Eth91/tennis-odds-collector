#!/usr/bin/env python3
"""Why each prop won or lost, and simple filters from it (NBA_WHY_PREREG.md).

Every prop at FanDuel's main line at tip - 30 (the cp30 FanDuel rows of nba_ml1's point-in-time dataset), with its
over and under prices, result and CLV. Part 1 explains results with the box score; part 2 searches 1- and
2-condition filters over fixed pre-game buckets, validated leave-one-day-out and against a shuffle control.

    python3 nba_why.py --ml1 DATA.json.gz --data DIR [--json OUT]
DIR holds nba_matchup.sqlite and nba_gamelogs.sqlite (the box scores and history).
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_ml1 as M
import nba_proj_data as PD
import nba_proj_eval as E

COMBOS = ("pts_reb", "pts_ast", "reb_ast", "pra")
COVER, SHUFFLES, SEED = 0.05, 200, 7


def props(ml1_rows):
    """{(gid, pid, market): {"over": row, "under": row}} from the cp30 FanDuel rows with a result."""
    out = defaultdict(dict)
    for r in ml1_rows:
        if r["label"] == "cp30" and r["book"] == "fd" and r.get("profit") is not None:
            out[(r["gid"], r["pid"], r["market"])][r["side"]] = r
    return {k: v for k, v in out.items() if "over" in v and "under" in v}


def context(data_dir):
    """Box scores, game results, team schedules and the stat history (before any date)."""
    m = PD._ro(Path(data_dir) / "nba_matchup.sqlite")
    games = {g: (d, h, a, hp, ap) for g, d, h, a, hp, ap in m.execute("SELECT gid, date, home, away, home_pts, away_pts FROM games")}
    box = {(g, p): (tm, st, mn, (a, b, c, t)) for g, tm, p, st, mn, a, b, c, t in
           m.execute("SELECT gid, team, pid, starter, min, pts, reb, ast, fg3m FROM player_games")}
    played = defaultdict(set)                            # team -> dates played (this season + last season's logs)
    for d, h, a in m.execute("SELECT date, home, away FROM games"):
        played[h].add(d)
        played[a].add(d)
    g = PD._ro(Path(data_dir) / "nba_gamelogs.sqlite")
    for d, tm in g.execute("SELECT DISTINCT date, team FROM logs"):
        played[tm].add(d)
    stats = M.StatHistory(Path(data_dir) / "nba_gamelogs.sqlite", Path(data_dir) / "nba_matchup.sqlite")
    return games, box, played, stats


def table(pr, ctx):
    """One record per prop: buckets (pre-game), both sides' profit / CLV / price, and the explanation (post-game)."""
    games, box, played, stats = ctx
    F = M.FEATURES
    recs = []
    for (g, p, mk), s in pr.items():
        o, u = s["over"], s["under"]
        x = dict(zip(F, o["x"]))
        d = o["date"]
        hist = stats.before(p, d)[-10:]
        if not hist:
            continue
        team = hist[-1][1]
        _gd, home, away, hp, ap = games.get(g, (d, None, None, None, None))
        avg = o["line"] - x["line_minus_avg"]
        rel = (o["line"] - avg) / max(avg, 1.0)
        mv = x["line_move_open"]
        rec = {"date": d, "gid": g, "pid": p, "market": mk, "line": o["line"],
               "b": {"market": mk if mk in ("points", "rebounds", "assists", "threes") else "combo",
                     "line_vs_avg": "below" if rel <= -0.10 else "above" if rel >= 0.10 else "near",
                     "min_trend": "falling" if x["min_trend"] <= -3 else "rising" if x["min_trend"] >= 3 else "flat",
                     "role": "bench" if x["min10"] < 20 else "starter30" if x["min10"] >= 30 else "mid",
                     "teammate_out": "yes" if x["team_out"] >= 1 else "no",
                     "opp_out": "yes" if x["opp_out"] >= 1 else "no",
                     "team_news_6h": "yes" if x["team_news_min"] <= 360 else "no",
                     "own_listed": "yes" if x["own_questionable"] or x["own_probable"] else "no",
                     "fd_line_move": "up" if mv > 0 else "down" if mv < 0 else "none",
                     "dk_vs_fd": "dk_higher" if x["dk_minus_fd"] >= 0.02 else "dk_lower" if x["dk_minus_fd"] <= -0.02 else "near",
                     "home": "home" if team == home else "away" if team == away else "unknown",
                     "b2b": "yes" if (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat() in played.get(team, ()) else "no"},
               "price": {sd: ("short" if s[sd]["odds"] < 1.80 else "long" if s[sd]["odds"] > 2.00 else "mid") for sd in ("over", "under")},
               "profit": {sd: s[sd]["profit"] for sd in ("over", "under")},
               "odds": {sd: s[sd]["odds"] for sd in ("over", "under")},
               "clv": {sd: s[sd]["y"] for sd in ("over", "under")}}
        bx = box.get((g, p))
        if bx:
            _tm, starter, mn, st4 = bx
            actual = M.market_value(st4, mk)
            mins10 = sum(h[2] for h in hist)
            rate10 = sum(M.market_value(h[3], mk) for h in hist) / max(1e-9, mins10)
            min10 = mins10 / len(hist)
            rec["why"] = {"actual": actual, "result": "over" if actual > o["line"] else "under" if actual < o["line"] else "push",
                          "minutes_effect": (mn - min10) * rate10,
                          "rate_effect": mn * ((actual / mn if mn else 0.0) - rate10), "min_minus_l10": mn - min10,
                          "started": bool(starter),
                          "blowout": hp is not None and abs(hp - ap) >= 15}
        recs.append(rec)
    return recs


def explain(recs):
    """Part 1: what separates over winners from under winners."""
    out = {}
    w = [r for r in recs if "why" in r]
    for res in ("over", "under"):
        k = [r["why"] for r in w if r["why"]["result"] == res]
        if not k:
            continue
        out[res + "_winners"] = {
            "n": len(k), "minutes_effect": round(float(np.mean([x["minutes_effect"] for x in k])), 2),
            "rate_effect": round(float(np.mean([x["rate_effect"] for x in k])), 2),
            "min_vs_last10": round(float(np.mean([x["min_minus_l10"] for x in k])), 2),
            "played_5plus_more": round(float(np.mean([x["min_minus_l10"] >= 5 for x in k])), 3),
            "played_5plus_less": round(float(np.mean([x["min_minus_l10"] <= -5 for x in k])), 3),
            "blowout": round(float(np.mean([x["blowout"] for x in k])), 3),
            "started": round(float(np.mean([x["started"] for x in k])), 3)}
    out["over_rate"] = round(float(np.mean([r["why"]["result"] == "over" for r in w if r["why"]["result"] != "push"])), 3)
    out["always_over_roi"] = round(float(np.mean([r["profit"]["over"] for r in recs])), 4)
    out["always_under_roi"] = round(float(np.mean([r["profit"]["under"] for r in recs])), 4)
    out["by_market_over_rate"] = {mk: round(float(np.mean([r["why"]["result"] == "over" for r in w if r["b"]["market"] == mk
                                                           and r["why"]["result"] != "push"])), 3)
                                  for mk in sorted({r["b"]["market"] for r in w})}
    return out


# ── the filter search ───────────────────────────────────────────────────────────────────────────────────────────
def conditions(recs):
    """{(condition, bucket): {side: bool array}}; price is per side, the rest apply to both sides."""
    out = {}
    names = sorted(recs[0]["b"])
    for c in names:
        for v in sorted({r["b"][c] for r in recs}):
            a = np.array([r["b"][c] == v for r in recs])
            out[(c, v)] = {"over": a, "under": a}
    for v in ("short", "mid", "long"):
        out[("price", v)] = {sd: np.array([r["price"][sd] == v for r in recs]) for sd in ("over", "under")}
    return out


def filters(conds):
    """Every side x (1 condition, or 2 conditions from different rows)."""
    keys = sorted(conds)
    singles = [(k,) for k in keys]
    pairs = [(a, b) for a, b in itertools.combinations(keys, 2) if a[0] != b[0]]
    return [(sd, ks) for sd in ("over", "under") for ks in singles + pairs]


def mask_of(conds, f):
    sd, ks = f
    m = conds[ks[0]][sd].copy()
    for k in ks[1:]:
        m &= conds[k][sd]
    return m


def select(recs, conds, flist, idx, profit):
    """Filters selected on the props in `idx`: ROI > 0 on every date and pooled, covering >= 5%, firing every date."""
    dates = np.array([r["date"] for r in recs])
    days = sorted(set(dates[idx]))
    n_all = int(idx.sum())
    out = []
    for f in flist:
        m = mask_of(conds, f) & idx
        n = int(m.sum())
        if n < COVER * n_all:
            continue
        pr = profit[f[0]]
        ok = True
        for d in days:
            md = m & (dates == d)
            if not md.any() or pr[md].mean() <= 0:
                ok = False
                break
        if ok and pr[m].mean() > 0:
            out.append(f)
    return out


def bets(recs, conds, chosen, idx):
    """The union of `chosen` filters on the props in idx: one bet per (prop, side); a prop with both sides is skipped."""
    side = {"over": np.zeros(len(recs), bool), "under": np.zeros(len(recs), bool)}
    for f in chosen:
        side[f[0]] |= mask_of(conds, f)
    both = side["over"] & side["under"]
    out = []
    for sd in ("over", "under"):
        for i in np.where(side[sd] & ~both & idx)[0]:
            r = recs[i]
            out.append({"date": r["date"], "side": sd, "profit": r["profit"][sd], "clv": r["clv"][sd], "i": int(i)})
    return out


def summ(b):
    if not b:
        return {"n": 0}
    m1, lo1, hi1 = E.boot_ci([x["profit"] for x in b], [x["date"] for x in b], reps=4000)
    m2, lo2, hi2 = E.boot_ci([x["clv"] for x in b], [x["date"] for x in b], reps=4000)
    return {"n": len(b), "roi": round(m1, 4), "roi_lo": round(lo1, 4), "roi_hi": round(hi1, 4),
            "clv": round(m2, 4), "clv_lo": round(lo2, 4), "clv_hi": round(hi2, 4),
            "w": sum(x["profit"] > 0 for x in b), "l": sum(x["profit"] < 0 for x in b)}


def search(recs):
    conds = conditions(recs)
    flist = filters(conds)
    dates = np.array([r["date"] for r in recs])
    profit = {sd: np.array([r["profit"][sd] for r in recs], float) for sd in ("over", "under")}
    res = {"props": len(recs), "filters_considered": len(flist), "by_day": {}}
    held = []
    for d in sorted(set(dates)):
        chosen = select(recs, conds, flist, dates != d, profit)
        b = bets(recs, conds, chosen, dates == d)
        held += b
        res["by_day"][d] = {"selected_on_other_days": len(chosen), "held_out": summ(b)}
    res["held_out"] = summ(held)
    every = np.ones(len(recs), bool)
    final = select(recs, conds, flist, every, profit)
    res["selected_all_days"] = []
    for f in final:
        m = mask_of(conds, f)
        pr, cl = profit[f[0]][m], np.array([recs[i]["clv"][f[0]] for i in np.where(m)[0]])
        res["selected_all_days"].append({"side": f[0], "conditions": [f"{c}={v}" for c, v in f[1]], "n": int(m.sum()),
                                         "roi": round(float(pr.mean()), 4), "clv": round(float(cl.mean()), 4),
                                         "by_day": {d: round(float(profit[f[0]][m & (dates == d)].mean()), 3) for d in sorted(set(dates))}})
    res["selected_all_days"].sort(key=lambda x: -x["roi"])
    # the shuffle control: results permuted within (date, market); prices and conditions kept
    rng = np.random.default_rng(SEED)
    groups = defaultdict(list)
    for i, r in enumerate(recs):
        groups[(r["date"], r["market"])].append(i)
    res_over = np.array([r["profit"]["over"] > 0 for r in recs])
    res_push = np.array([r["profit"]["over"] == 0 for r in recs])
    odds = {sd: np.array([r["odds"][sd] for r in recs]) for sd in ("over", "under")}
    counts = []
    for _ in range(SHUFFLES):
        perm = np.arange(len(recs))
        for ix in groups.values():
            perm[ix] = rng.permutation(ix)
        ov, pu = res_over[perm], res_push[perm]
        sp = {"over": np.where(pu, 0.0, np.where(ov, odds["over"] - 1, -1.0)),
              "under": np.where(pu, 0.0, np.where(~ov, odds["under"] - 1, -1.0))}
        counts.append(len(select(recs, conds, flist, every, sp)))
    res["shuffle"] = {"median": float(np.median(counts)), "p95": float(np.percentile(counts, 95)), "max": int(max(counts))}
    h = res["held_out"]
    res["checks"] = {"held_out_roi_positive": h.get("n", 0) > 0 and h["roi"] > 0,
                     "held_out_clv_positive": h.get("n", 0) > 0 and h["clv"] > 0,
                     "more_than_chance": len(final) > res["shuffle"]["p95"]}
    res["verdict"] = "PASS: register WHY5 for a forward test" if all(res["checks"].values()) else "FAIL: no registration"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ml1", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    with gzip.open(a.ml1, "rt") as fh:
        rows = json.load(fh)["rows"]
    recs = table(props(rows), context(a.data))
    res = {"why": explain(recs), "search": search(recs)}
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
