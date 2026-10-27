#!/usr/bin/env python3
"""NBA_FLAGS_WL_PREREG.md amendment 1: two changes to the wowy projection, each fit on 2023-24 for accuracy only
(no line, price or result), then judged on the card's units at tip lines in BOTH 2023-24 and 2024-25.

  R  rate shrinkage   rate = (stat without X + base_rate x K) / (minutes without X + K), K from a fixed grid
  M  minutes recency  proj_min = a + b x last-10 min + c x last-3 min + k x d_min, least squares

The candidate walk is the backtest's (volume4 / amendment 30): every absent star >= 24 min, absence games 1-4,
FanDuel + DraftKings main line and best over price at the archive's tip snapshot.

    python3 nba_flags_model_test.py DATA_DIR [--json OUT]
DATA_DIR holds basketball_nba_odds_hist.sqlite and nba_gamelogs.sqlite.
"""
import argparse
import datetime as dt
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_margin_refit as MR
import nba_wowy as N

A_MIN, K_MIN_SLOPE = 0.980, 0.356               # nba_flags.MIN_A, MIN_K
K_RATE_NOW = 60.0                               # nba_flags.K_MIN
K_GRID = (60.0, 120.0, 240.0, 480.0, 960.0, 1920.0)
MARGIN = {"pts": 5.0, "reb": 1.0, "pra": 6.5}
COMBOS = {"pra"}
SPLIT = "2024-08-01"
MKT = {"pts": "player_points", "reb": "player_rebounds", "pra": "player_points_rebounds_assists"}
FDK = {"fanduel", "draftkings"}


def main_line(lines_by_book):
    """(line, best over) at the rung whose best FanDuel/DraftKings over is nearest even money (two-sided)."""
    best = None
    for line, bk in lines_by_book.items():
        ov = [v[0] for b, v in bk.items() if b in FDK and v[0] and v[1]]
        if not ov:
            continue
        gap = min(abs(x - 2.0) for x in ov)
        if best is None or gap < best[0] - 1e-9:
            best = (gap, line, max(ov))
    return (best[1], best[2]) if best else None


def candidates(data):
    MR.ODDS, MR.LOGS, N.LOGS = data / "basketball_nba_odds_hist.sqlite", data / "nba_gamelogs.sqlite", data / "nba_gamelogs.sqlite"
    inv = {v: k for k, v in MKT.items()}
    raw = defaultdict(lambda: defaultdict(dict))
    o = sqlite3.connect(f"file:{MR.ODDS}?mode=ro", uri=True, timeout=90)
    for d, p, m, line, side, price, book in o.execute(
            "SELECT game_date, player, market, line, side, price, book FROM props WHERE price IS NOT NULL AND line IS NOT NULL"):
        s = inv.get(m)
        if s and book in FDK:
            raw[(d, MR.norm(p), s)][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
    g = sqlite3.connect(f"file:{MR.LOGS}?mode=ro", uri=True, timeout=60)
    pid2name = {pid: nm for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs")}
    tg, _ = N.load_team_games(1)
    rows = []
    for team, games in tg.items():
        first_app = {}
        for i, (date, gid, box) in enumerate(games):
            for pid in box:
                first_app.setdefault(pid, date)
            if i < 12:
                continue
            cut = (N._d(date) - dt.timedelta(days=N.POOL_DAYS)).isoformat()
            lo = 0
            while lo < i and games[lo][0] < cut:
                lo += 1
            prior = games[lo:i]
            if len(prior) < 12:
                continue
            pb = defaultdict(list)
            for pd, _pg, pbox in prior:
                for pid, (mn, stt) in pbox.items():
                    pb[pid].append((pd, mn, stt))
            m10 = lambda p: sum(a[1] for a in pb[p][-10:]) / 10
            absents = sorted([p for p, a in pb.items() if p not in box and len(a) >= 10 and m10(p) >= 24
                              and (N._d(date) - N._d(a[-1][0])).days <= N.ACTIVE_DAYS], key=m10, reverse=True)
            for X in absents:
                aidx = 1
                for _pd, _pg, pbox in reversed(prior):
                    if X in pbox:
                        break
                    aidx += 1
                if aidx > 4:
                    continue
                xf = first_app.get(X, "0000")
                og = [pbox for pd, _pg, pbox in prior if pd >= xf and X not in pbox]
                ig = [pbox for pd, _pg, pbox in prior if pd >= xf and X in pbox]
                for B, (bmn, bst) in box.items():
                    if B == X or B in absents:
                        continue
                    apps = pb.get(B, [])
                    if len(apps) < N.MIN_PRIOR_APPS:
                        continue
                    bo = [p[B] for p in og if B in p]
                    bi = [p[B] for p in ig if B in p]
                    if len(bo) < N.MIN_WOWY or len(bi) < 3:
                        continue
                    a10 = apps[-10:]
                    min_out = sum(m for m, _ in bo)
                    d_shr = (min_out / len(bo) - sum(m for m, _ in bi) / len(bi)) * len(bo) / (len(bo) + N.K_DMIN)
                    nm = MR.norm(pid2name.get(B, ""))
                    for stat in MKT:
                        ml = raw.get((date, nm, stat))
                        lp = main_line(ml) if ml else None
                        rows.append({"date": date, "season": "23-24" if date < SPLIT else "24-25", "tg": (date, team),
                                     "b": B, "x": X, "stat": stat, "n_out": len(absents), "xmin": m10(X), "aidx": aidx,
                                     "base10": sum(a[1] for a in a10) / len(a10),
                                     "last3": sum(a[1] for a in apps[-3:]) / len(apps[-3:]), "d_shr": d_shr,
                                     "so": sum(s[stat] for _, s in bo), "min_out": min_out,
                                     "br": sum(a[2][stat] for a in a10) / max(1e-9, sum(a[1] for a in a10)),
                                     "act": bst[stat], "min": bmn, "fdk": lp})
    return rows


def rate(r, k):
    return (r["so"] + r["br"] * k) / (r["min_out"] + k)


def fit_k(rows):
    """R: the grid K minimizing the mean over stats of MSE(actual, rate_K x actual minutes) / MSE at K = 60."""
    fit = [r for r in rows if r["season"] == "23-24"]
    mse = {k: {s: np.mean([(r["act"] - rate(r, k) * r["min"]) ** 2 for r in fit if r["stat"] == s]) for s in MKT}
           for k in K_GRID}
    rel = {k: float(np.mean([mse[k][s] / mse[K_RATE_NOW][s] for s in MKT])) for k in K_GRID}
    return min(rel, key=rel.get), rel


def fit_minutes(rows):
    """M: least squares on 2023-24, one row per (date, B, X): min ~ 1 + last-10 + last-3 + d_min."""
    seen, X, y = set(), [], []
    for r in rows:
        k = (r["date"], r["b"], r["x"])
        if r["season"] != "23-24" or k in seen:
            continue
        seen.add(k)
        X.append((1.0, r["base10"], r["last3"], r["d_shr"]))
        y.append(r["min"])
    X, y = np.array(X), np.array(y)
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    now = np.array([A_MIN + x[1] + K_MIN_SLOPE * x[3] for x in X])
    return [float(c) for c in coef], {"n": len(y), "rmse_now": float(np.sqrt(np.mean((y - now) ** 2))),
                                      "rmse_fit": float(np.sqrt(np.mean((y - X @ coef) ** 2)))}


def project(r, k, coef):
    pmin = (A_MIN + r["base10"] + K_MIN_SLOPE * r["d_shr"]) if coef is None else \
        coef[0] + coef[1] * r["base10"] + coef[2] * r["last3"] + coef[3] * r["d_shr"]
    return rate(r, k) * pmin


def card(rows, k, coef, rebounds=True):
    """The current card's rules (amendments 22-32 that a backtest can see) on one projection."""
    pool = []
    for r in rows:
        if not r["fdk"] or not 3 <= r["d_shr"] <= 8 or r["n_out"] >= 2 or r["xmin"] >= 32:
            continue
        if not rebounds and r["stat"] == "reb":
            continue
        line, price = r["fdk"]
        proj = project(r, k, coef)
        ex = (proj - line) / MARGIN[r["stat"]]
        if price < 1.8 or not 1 <= ex < 2:
            continue
        u = (price - 1) if r["act"] > line else 0.0 if r["act"] == line else -1.0
        pool.append(dict(r, line=line, price=price, proj=proj, ex=ex, u=u))
    byp = defaultdict(list)
    for r in pool:
        byp[(r["date"], r["b"])].append(r)
    leads = [max([x for x in w if x["stat"] not in COMBOS] or w, key=lambda x: x["ex"]) for w in byp.values()]
    bt = defaultdict(list)
    for r in leads:
        bt[r["tg"]].append(r)
    return [r for w in bt.values() for r in sorted(w, key=lambda r: -r["ex"])[:2]]


def season_units(plays):
    out = {}
    for s in ("23-24", "24-25"):
        w = [r for r in plays if r["season"] == s]
        out[s] = {"n": len(w), "units": round(sum(r["u"] for r in w), 2),
                  "roi": round(100 * sum(r["u"] for r in w) / max(1, len(w)), 1),
                  "act_minus_proj": round(float(np.mean([r["act"] - r["proj"] for r in w])), 2) if w else None}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = candidates(a.data)
    k, rel = fit_k(rows)
    coef, mfit = fit_minutes(rows)
    print(f"candidates {len(rows)} · with a FanDuel/DraftKings line {sum(1 for r in rows if r['fdk'])}")
    print(f"R: K = {k:g} (relative MSE by K: " + ", ".join(f"{kk:g} {v:.4f}" for kk, v in rel.items()) + ")")
    print(f"M: proj_min = {coef[0]:.2f} + {coef[1]:.3f} x last10 + {coef[2]:.3f} x last3 + {coef[3]:.3f} x d_min "
          f"(2023-24 RMSE {mfit['rmse_now']:.2f} -> {mfit['rmse_fit']:.2f}, n {mfit['n']})")
    parity = season_units(card(rows, K_RATE_NOW, None, rebounds=False))
    print("parity with amendment 30's current card (no rebounds; it read 35 bets +20.7% and 38 bets +40.4%): "
          + " | ".join(f"{s} {v['n']} bets {v['roi']:+.1f}%" for s, v in parity.items()))
    models = {"current": (K_RATE_NOW, None), "R": (k, None), "M": (K_RATE_NOW, coef), "R+M": (k, coef)}
    res = {name: season_units(card(rows, *km)) for name, km in models.items()}
    for name, v in res.items():
        print(f"  {name:<8} " + " | ".join(f"{s}: {x['n']:3d} bets {x['roi']:+6.1f}% {x['units']:+7.2f}u  act-proj {x['act_minus_proj']}"
                                           for s, x in v.items()))
    passes = {m: all(res[m][s]["units"] >= res["current"][s]["units"] for s in ("23-24", "24-25")) for m in ("R", "M", "R+M")}
    tot = lambda m: sum(res[m][s]["units"] for s in ("23-24", "24-25"))
    if passes["R"] and passes["M"]:
        adopt = "R+M" if passes["R+M"] else max(("R", "M"), key=tot)
    else:
        adopt = "R" if passes["R"] else "M" if passes["M"] else None
    print("passes:", passes)
    print("REGISTERED DECISION:", f"ADOPT {adopt}" if adopt else "KEEP the current projection")
    if a.json:
        open(a.json, "w").write(json.dumps({"K": k, "K_rel_mse": rel, "minutes_coef": coef, "minutes_fit": mfit,
                                            "parity": parity, "results": res, "passes": passes, "adopt": adopt}, indent=1))


if __name__ == "__main__":
    main()
