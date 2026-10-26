#!/usr/bin/env python3
"""Walk-forward evaluation of the projection engine (NBA_PROJECTION_PREREG.md). Mac-side (local copies of the
VM stores in .projdata/), read-only.

    python3 nba_proj_eval.py --tune            # coordinate descent on 2023-24 ONLY; prints the config to freeze
    python3 nba_proj_eval.py --final           # the frozen PROJ_CONFIG on 2023-24 (tuning), 2024-25 (A),
                                               # 2025-26 (B), 2026-27 (C); writes PROJECTION_RESULTS.md + .json

Every prediction for date d comes from nba_project.walk (state from earlier dates only) and an analog pool of
player-games dated before the first day of d's month (stricter than "before d", so a month is one block).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_proj_data as PD
import nba_project as NP

HERE = Path(__file__).resolve().parent
DATA = HERE / ".projdata"
ODDS = Path.home() / "tennis-odds-collector" / "basketball_nba_odds_hist.sqlite"
GRIDS = {"min": 70, "pts": 90, "reb": 35, "ast": 30, "fg3m": 16, "stl": 12, "blk": 14, "tov": 16,
         "points": 90, "rebounds": 35, "assists": 30, "threes": 16, "steals": 12, "blocks": 14, "turnovers": 16,
         "pra": 120, "pts_reb": 105, "pts_ast": 105, "reb_ast": 55}
TUNE, TEST_A, TEST_B, TEST_C = "2023-24", "2024-25", "2025-26", "2026-27"
BOOT, SEED = 4000, 7


def load(refresh=False):
    """(rows, hist lines, live lines) — cached in .projdata/cache.pkl (rebuilt with --refresh)."""
    cache = DATA / "cache.pkl"
    if cache.exists() and not refresh:
        return pickle.loads(cache.read_bytes())
    rows, dnps, pos = PD.load_box(DATA / "nba_gamelogs.sqlite", DATA / "nba_matchup.sqlite", DATA / "nba_profiles.sqlite")
    hist, st = PD.load_hist_lines(ODDS, rows, DATA / "nba_gamelogs.sqlite")
    live = PD.load_live_lines(DATA / "nba_lines.sqlite")
    obj = {"rows": rows, "dnps": dnps, "hist": hist, "hist_stats": dict(st), "live": live}
    cache.write_bytes(pickle.dumps(obj))
    return obj


class Run:
    """One configuration's walk-forward means plus the arrays the evaluation needs."""

    def __init__(self, rows, cfg, consts=None):
        self.rows, self.cfg = rows, cfg
        out, _ = NP.walk(rows, cfg, consts=consts)
        self.Y = np.array([[r[s] for s in NP.STATS] for r in rows], float)
        self.Y[:, 0] = np.round(self.Y[:, 0])                      # minutes graded as whole minutes everywhere
        self.mu = {k: np.array([o[k] for o in out]) for k in ("b1", "b2", "m1")}
        self.n_hist = np.array([o["n_hist"] for o in out], float)
        self.rest = np.array([o["rest"] for o in out], float)
        self.date = np.array([r["date"] for r in rows])
        self.season = np.array([r["season"] for r in rows])
        self.key = {(r["gid"], r["pid"]): i for i, r in enumerate(rows)}
        hist_rows = self.season == "2022-23"
        f = NP.features(self.mu["m1"][hist_rows], self.n_hist[hist_rows], self.rest[hist_rows], cfg)
        self.scale = np.where(f.std(0) > 0, f.std(0), 1.0)
        self.sd = self.Y[hist_rows].std(0)                          # CRPS normalizer: 2022-23 outcome sd

    def dist(self, idx):
        """Dist for target rows idx (sorted by date), built month by month from the strictly earlier pool."""
        cfg = self.cfg
        feats = NP.features(self.mu["m1"], self.n_hist, self.rest, cfg)
        parts, order = [], []
        month = defaultdict(list)
        for i in idx:
            month[self.date[i][:7]].append(i)
        vals = np.zeros((len(idx), cfg["K"], NP.NS))
        pos = {i: j for j, i in enumerate(idx)}
        for mth, ii in sorted(month.items()):
            pool = pool_index(self, mth + "-01")
            ii = np.array(ii)
            nb = NP.neighbors(feats[ii], feats[pool], cfg["K"], self.scale)
            d = NP.Dist(self.mu["m1"][ii], self.mu["m1"][pool], self.Y[pool], nb)
            vals[[pos[i] for i in ii]] = d.vals
        out = NP.Dist.__new__(NP.Dist)
        out.vals, out.mu = vals, self.mu["m1"][idx]
        return out


def pool_index(run, start, days=730):
    """The analog pool for targets in the month starting `start`: player-games dated strictly before it, within
    `days` (two seasons)."""
    lo = (dt.date.fromisoformat(start) - dt.timedelta(days=days)).isoformat()
    return np.where((run.date < start) & (run.date >= lo))[0]


def crps_by_stat(run, idx, d):
    out = {}
    for j, s in enumerate(NP.STATS):
        pm = d.pmf(s if s != "min" else "min", GRIDS[s]) if s == "min" else d.pmf(s, GRIDS[s])
        out[s] = NP.crps_pmf(pm, run.Y[idx, j].astype(int))
    return out


def objective(run, idx, d):
    c = crps_by_stat(run, idx, d)
    return float(np.mean([c[s].mean() / run.sd[j] for j, s in enumerate(NP.STATS)])), c


def fd_join(run, lines, idx_set=None, book="fd"):
    """[(row index, line dict)] for `book` lines whose player appeared (DNP = void) in `idx_set`."""
    out = []
    for ln in lines:
        if ln["book"] != book:
            continue
        i = run.key.get((ln["gid"], ln["pid"]))
        if i is None or (idx_set is not None and i not in idx_set):
            continue
        out.append((i, ln))
    return out


def market_probs(run, d, idx, joined):
    """For joined lines: arrays p_m1, p_mkt, outcome over (1/0), push mask, market, row index."""
    pos = {i: j for j, i in enumerate(idx)}
    by_mkt = defaultdict(list)
    for i, ln in joined:
        by_mkt[ln["market"]].append((i, ln))
    res = defaultdict(list)
    for mk, items in by_mkt.items():
        sel = np.array([pos[i] for i, _ in items])
        sub = NP.Dist.__new__(NP.Dist)
        sub.vals, sub.mu = d.vals[sel], d.mu[sel]
        lines = np.array([ln["line"] for _, ln in items])
        po, pu, pp = sub.probs(mk, lines)
        actual = np.array([sum(run.Y[i, NP.STATS.index(s)] for s in PD.MARKET_PARTS[mk]) for i, _ in items])
        res["p_m1"].append(po / np.clip(po + pu, 1e-9, None))       # conditional on no push
        res["p_mkt"].append(NP.no_vig([ln["over"] for _, ln in items], [ln["under"] for _, ln in items]))
        res["over"].append((actual > lines).astype(float))
        res["push"].append(actual == lines)
        res["market"].append(np.array([mk] * len(items)))
        res["row"].append(np.array([i for i, _ in items]))
        res["line"].append(lines)
        res["po"].append(np.array([ln["over"] for _, ln in items])); res["pu"].append(np.array([ln["under"] for _, ln in items]))
        res["mu"].append(sub.mean(mk))
    return {k: np.concatenate(v) for k, v in res.items()} if res else {}


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def boot_ci(diff, dates, reps=BOOT, seed=SEED):
    """Date-clustered bootstrap: (mean, lo, hi) of the per-item difference."""
    diff, dates = np.asarray(diff, float), np.asarray(dates)
    ud, inv = np.unique(dates, return_inverse=True)
    s = np.bincount(inv, weights=diff)
    n = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(ud), size=(reps, len(ud)))
    m = s[pick].sum(1) / n[pick].sum(1)
    return float(diff.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


# ── tuning (2023-24 only) ───────────────────────────────────────────────────────────────────────────────────
def tune(data, passes=3, every=3):
    rows = data["rows"]
    consts = NP.context_constants(rows)
    cfg = dict(NP.PROJ_CONFIG)
    cache = {}

    def evaluate(c):
        key = NP.cfg_hash(c)
        if key in cache:
            return cache[key]
        run = Run(rows, c, consts)
        dates = sorted({run.date[i] for i in np.where(run.season == TUNE)[0]})[::every]
        dset = set(dates)
        idx = np.array([i for i in np.where(run.season == TUNE)[0] if run.date[i] in dset])
        d = run.dist(idx)
        obj, _ = objective(run, idx, d)
        joined = fd_join(run, data["hist"], set(idx.tolist()))
        mp = market_probs(run, d, idx, joined)
        ll = float(logloss(mp["p_m1"], mp["over"])[~mp["push"]].mean()) if mp else float("nan")
        cache[key] = (obj, ll)
        print(f"  {obj:.5f}  ll {ll:.5f}  {json.dumps({k: c[k] for k in sorted(c)})}", flush=True)
        return cache[key]

    best = evaluate(cfg)
    for p in range(passes):
        changed = False
        for k, vals in NP.GRID.items():
            for v in vals:
                if v == cfg[k]:
                    continue
                c = dict(cfg, **{k: v})
                r = evaluate(c)
                if r < best:
                    best, cfg, changed = r, c, True
                    print(f"pass {p} {k}={v}: objective {r[0]:.5f}", flush=True)
        if not changed:
            break
    print("CHOSEN", json.dumps(cfg, sort_keys=True), "objective", best)
    return cfg, best


# ── the final, pre-registered evaluation ───────────────────────────────────────────────────────────────────
def segment(name, groups, items):
    return {"segment": name, **{g: v for g, v in zip(groups, items)}}


def evaluate_period(run, data, season, nb_disp, w_blend, live=False):
    idx = np.where(run.season == season)[0]
    if not len(idx):
        return None
    d = run.dist(idx)
    res = {"season": season, "n": int(len(idx)), "dates": int(len(set(run.date[idx]))), "stats": {}}
    dates = run.date[idx]
    crps = crps_by_stat(run, idx, d)
    for j, s in enumerate(NP.STATS):
        y = run.Y[idx, j]
        row = {}
        for key in ("b1", "b2", "m1"):
            mu = run.mu[key][idx, j]
            row[key] = {"mae": float(np.abs(mu - y).mean()), "rmse": float(np.sqrt(((mu - y) ** 2).mean()))}
        pm = d.pmf(s, GRIDS[s])
        row["m1"]["crps"] = float(crps[s].mean())
        row["m1"]["log"] = float(NP.logscore_pmf(pm, y.astype(int), run.cfg["K"]).mean())
        nbp = NP.nb_pmf(run.mu["b2"][idx, j], nb_disp[s], GRIDS[s])
        c_b2 = NP.crps_pmf(nbp, y.astype(int))
        row["b2"]["crps"] = float(c_b2.mean())
        row["b2"]["log"] = float(-np.log(np.clip(nbp[np.arange(len(y)), np.clip(y.astype(int), 0, GRIDS[s] - 1)], 1e-12, None)).mean())
        m, lo, hi = boot_ci(crps[s] - c_b2, dates)
        row["m1_minus_b2_crps"] = [m, lo, hi]
        mae_d = np.abs(run.mu["m1"][idx, j] - y) - np.abs(run.mu["b2"][idx, j] - y)
        row["m1_minus_b2_mae"] = list(boot_ci(mae_d, dates))
        mae_d1 = np.abs(run.mu["m1"][idx, j] - y) - np.abs(run.mu["b1"][idx, j] - y)
        row["m1_minus_b1_mae"] = list(boot_ci(mae_d1, dates))
        # PIT (randomized, discrete): deciles
        cdf = np.cumsum(pm, 1)
        yy = np.clip(y.astype(int), 0, GRIDS[s] - 1)
        lo_ = np.where(yy > 0, cdf[np.arange(len(yy)), yy - 1], 0.0)
        hi_ = cdf[np.arange(len(yy)), yy]
        u = lo_ + np.random.default_rng(SEED).random(len(yy)) * (hi_ - lo_)
        row["pit_deciles"] = (np.histogram(u, bins=10, range=(0, 1))[0] / len(u)).round(4).tolist()
        q = d.quantiles(s, (0.1, 0.9))
        row["cover80"] = float(((y >= q[:, 0]) & (y <= q[:, 1])).mean())
        res["stats"][s] = row
    # combined normalized CRPS (the tuning objective's scale)
    res["norm_crps_m1"] = float(np.mean([res["stats"][s]["m1"]["crps"] / run.sd[j] for j, s in enumerate(NP.STATS)]))
    res["norm_crps_b2"] = float(np.mean([res["stats"][s]["b2"]["crps"] / run.sd[j] for j, s in enumerate(NP.STATS)]))
    cr = sum((crps[s] / run.sd[j]) for j, s in enumerate(NP.STATS)) / NP.NS
    cb = 0
    for j, s in enumerate(NP.STATS):
        cb = cb + NP.crps_pmf(NP.nb_pmf(run.mu["b2"][idx, j], nb_disp[s], GRIDS[s]), run.Y[idx, j].astype(int)) / run.sd[j]
    res["norm_crps_m1_minus_b2"] = list(boot_ci(cr - cb / NP.NS, dates))
    # market
    lines = data["live"] if live else data["hist"]
    joined = fd_join(run, lines, set(idx.tolist()))
    mp = market_probs(run, d, idx, joined)
    if mp:
        ok = ~mp["push"]
        y = mp["over"][ok]
        pm1, pmk = mp["p_m1"][ok], mp["p_mkt"][ok]
        pbl = NP.blend(pm1, pmk, w_blend)
        ddates = run.date[mp["row"][ok]]
        mkt = mp["market"][ok]
        mres = {"n": int(ok.sum()), "pushes": int(mp["push"].sum()), "by_market": {}}
        for lab, p in (("m1", pm1), ("market", pmk), ("m1+mkt", pbl)):
            mres[lab] = {"logloss": float(logloss(p, y).mean()), "brier": float(((p - y) ** 2).mean())}
        mres["m1_minus_market_ll"] = list(boot_ci(logloss(pm1, y) - logloss(pmk, y), ddates))
        mres["blend_minus_market_ll"] = list(boot_ci(logloss(pbl, y) - logloss(pmk, y), ddates))
        # B2 naive at the line (NB on the market's own sum)
        b2p = []
        for (i, ln) in [(r, None) for r in mp["row"][ok]]:
            pass
        for mk in sorted(set(mkt)):
            sel = mkt == mk
            mres["by_market"][mk] = {"n": int(sel.sum()), "m1_ll": float(logloss(pm1[sel], y[sel]).mean()),
                                     "market_ll": float(logloss(pmk[sel], y[sel]).mean()),
                                     "blend_ll": float(logloss(pbl[sel], y[sel]).mean()),
                                     "m1_minus_market": list(boot_ci(logloss(pm1[sel], y[sel]) - logloss(pmk[sel], y[sel]), ddates[sel], reps=1000))}
        # reliability: 10 buckets of p_m1, per all markets
        bins = np.clip((pm1 * 10).astype(int), 0, 9)
        mres["reliability_m1"] = [[int((bins == b).sum()), float(pm1[bins == b].mean()) if (bins == b).any() else None,
                                   float(y[bins == b].mean()) if (bins == b).any() else None] for b in range(10)]
        bins = np.clip((pmk * 10).astype(int), 0, 9)
        mres["reliability_market"] = [[int((bins == b).sum()), float(pmk[bins == b].mean()) if (bins == b).any() else None,
                                       float(y[bins == b].mean()) if (bins == b).any() else None] for b in range(10)]
        # line as a point forecast vs the model mean (MAE), on these props
        act = np.array([sum(run.Y[i, NP.STATS.index(s)] for s in PD.MARKET_PARTS[m]) for i, m in zip(mp["row"][ok], mkt)])
        mres["mae_line"] = float(np.abs(mp["line"][ok] - act).mean())
        mres["mae_m1_mean"] = float(np.abs(mp["mu"][ok] - act).mean())
        # pre-specified simulation: bet the side where p_blend - p_mkt >= 0.03, flat 1u at the snapshot price
        edge_o, edge_u = pbl - pmk, (1 - pbl) - (1 - pmk)
        bet_o, bet_u = edge_o >= 0.03, edge_u >= 0.03
        po, pu = mp["po"][ok], mp["pu"][ok]
        pnl = np.where(bet_o, np.where(y == 1, po - 1, -1.0), 0.0) + np.where(bet_u, np.where(y == 0, pu - 1, -1.0), 0.0)
        nb_ = bet_o | bet_u
        if nb_.any():
            order = np.argsort(ddates[nb_], kind="stable")
            cum = np.cumsum(pnl[nb_][order])
            dd = float((np.maximum.accumulate(cum) - cum).max())
            m, lo, hi = boot_ci(pnl[nb_], ddates[nb_])
            mres["sim"] = {"bets": int(nb_.sum()), "win_rate": float((pnl[nb_] > 0).mean()), "roi": m, "roi_ci": [lo, hi],
                           "max_drawdown_units": dd}
        # segments: projected minutes band, history depth
        rows_i = mp["row"][ok]
        pmin = run.mu["m1"][rows_i, 0]
        nh = run.n_hist[rows_i]
        segs = {}
        for name, mask in (("min<15", pmin < 15), ("min15-25", (pmin >= 15) & (pmin < 25)), ("min25-32", (pmin >= 25) & (pmin < 32)),
                           ("min32+", pmin >= 32), ("hist<10", nh < 10), ("hist10-40", (nh >= 10) & (nh < 40)), ("hist40+", nh >= 40),
                           ("market_fav_over", pmk >= 0.5), ("market_fav_under", pmk < 0.5)):
            if mask.sum() >= 50:
                segs[name] = {"n": int(mask.sum()), "m1_ll": float(logloss(pm1[mask], y[mask]).mean()),
                              "market_ll": float(logloss(pmk[mask], y[mask]).mean()), "blend_ll": float(logloss(pbl[mask], y[mask]).mean())}
        mres["segments"] = segs
        res["market"] = mres
    return res


def fit_nb(run, season):
    """Method-of-moments NB size per stat for B2's naive marginals, on `season` (tuning)."""
    idx = run.season == season
    out = {}
    for j, s in enumerate(NP.STATS):
        mu, y = run.mu["b2"][idx, j], run.Y[idx, j]
        excess = ((y - mu) ** 2 - mu).mean()
        out[s] = float((mu ** 2).mean() / excess) if excess > 0 else float("inf")
    return out


def fit_blend(run, data, season, d=None):
    """w for the logit blend, by grid on `season` (tuning) log loss."""
    idx = np.where(run.season == season)[0]
    d = d or run.dist(idx)
    mp = market_probs(run, d, idx, fd_join(run, data["hist"], set(idx.tolist())))
    ok = ~mp["push"]
    best = min((float(logloss(NP.blend(mp["p_m1"][ok], mp["p_mkt"][ok], w), mp["over"][ok]).mean()), w)
               for w in np.round(np.arange(0, 1.01, 0.05), 2))
    return best[1], best[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    data = load(a.refresh)
    print("rows", len(data["rows"]), "hist lines", len(data["hist"]), data["hist_stats"], "live", len(data["live"]))
    if a.tune:
        tune(data)
    if a.final:
        final(data)


def final(data):
    if NP.TUNED_ON != TUNE:
        sys.exit("PROJ_CONFIG is not marked as tuned on 2023-24: run --tune and freeze it first")
    rows = data["rows"]
    run = Run(rows, NP.PROJ_CONFIG, NP.context_constants(rows))
    nb_disp = fit_nb(run, TUNE)
    w, ll = fit_blend(run, data, TUNE)
    out = {"version": NP.VERSION, "config": NP.PROJ_CONFIG, "nb_size": nb_disp, "blend_w": w,
           "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "periods": {}}
    for season, live in ((TUNE, False), (TEST_A, False), (TEST_B, False), (TEST_C, True)):
        print("evaluating", season, flush=True)
        out["periods"][season] = evaluate_period(run, data, season, nb_disp, w, live=live)
    (HERE / "PROJECTION_RESULTS.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote PROJECTION_RESULTS.json")


if __name__ == "__main__":
    main()
