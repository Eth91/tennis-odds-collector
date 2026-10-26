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


def evaluate_period(run, data, season, nb_disp, w_blend, live=False, nb_disp1=None):
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
        ens_mean = d.mean(s)
        for key in ("b1", "b2", "m1"):
            mu = ens_mean if key == "m1" else run.mu[key][idx, j]          # M1's output is the ensemble, not its input mean
            row[key] = {"mae": float(np.abs(mu - y).mean()), "rmse": float(np.sqrt(((mu - y) ** 2).mean()))}
        pm = d.pmf(s, GRIDS[s])
        med = (np.cumsum(pm, 1) >= .5).argmax(1)
        row["m1"]["mae_median"] = float(np.abs(med - y).mean())
        row["m1"]["crps"] = float(crps[s].mean())
        row["m1"]["log"] = float(NP.logscore_pmf(pm, y.astype(int), run.cfg["K"]).mean())
        nbp = NP.nb_pmf(run.mu["b2"][idx, j], nb_disp[s], GRIDS[s])
        c_b2 = NP.crps_pmf(nbp, y.astype(int))
        row["b2"]["crps"] = float(c_b2.mean())
        row["b2"]["log"] = float(-np.log(np.clip(nbp[np.arange(len(y)), np.clip(y.astype(int), 0, GRIDS[s] - 1)], 1e-12, None)).mean())
        m, lo, hi = boot_ci(crps[s] - c_b2, dates)
        row["m1_minus_b2_crps"] = [m, lo, hi]
        if nb_disp1:
            c_b1 = NP.crps_pmf(NP.nb_pmf(run.mu["b1"][idx, j], nb_disp1[s], GRIDS[s]), y.astype(int))
            row["b1"]["crps"] = float(c_b1.mean())
            row["m1_minus_b1_crps"] = list(boot_ci(crps[s] - c_b1, dates))
        mae_d = np.abs(ens_mean - y) - np.abs(run.mu["b2"][idx, j] - y)
        row["m1_minus_b2_mae"] = list(boot_ci(mae_d, dates))
        mae_d1 = np.abs(ens_mean - y) - np.abs(run.mu["b1"][idx, j] - y)
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
    if nb_disp1:
        c1 = 0
        for j, s in enumerate(NP.STATS):
            c1 = c1 + NP.crps_pmf(NP.nb_pmf(run.mu["b1"][idx, j], nb_disp1[s], GRIDS[s]), run.Y[idx, j].astype(int)) / run.sd[j]
        res["norm_crps_m1_minus_b1"] = list(boot_ci(cr - c1 / NP.NS, dates))
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
        bins = np.clip((pbl * 10).astype(int), 0, 9)
        mres["reliability_blend"] = [[int((bins == b).sum()), float(pbl[bins == b].mean()) if (bins == b).any() else None,
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


def fit_nb(run, season, key="b2"):
    """Method-of-moments NB size per stat for a baseline's naive marginals, on `season` (tuning)."""
    idx = run.season == season
    out = {}
    for j, s in enumerate(NP.STATS):
        mu, y = run.mu[key][idx, j], run.Y[idx, j]
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
    ap.add_argument("--freeze", action="store_true", help="print PROJ_CONSTS / PROJ_SCALE / PROJ_BLEND_W for PROJ_CONFIG")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--prospective", metavar="OUT_JSON", help="VM nightly: grade the logged forecasts (test C)")
    a = ap.parse_args()
    if a.prospective:
        r = prospective(HERE / "nba_proj_log.sqlite", HERE / "nba_lines.sqlite", HERE / "nba_matchup.sqlite", a.prospective)
        print("nba_proj_eval --prospective:", {k: v for k, v in r.items() if k != "note"})
        return
    data = load(a.refresh)
    print("rows", len(data["rows"]), "hist lines", len(data["hist"]), data["hist_stats"], "live", len(data["live"]))
    if a.tune:
        tune(data)
    if a.freeze:
        freeze(data)
    if a.final:
        final(data)


def final(data):
    if NP.TUNED_ON != TUNE:
        sys.exit("PROJ_CONFIG is not marked as tuned on 2023-24: run --tune and freeze it first")
    rows = data["rows"]
    run = Run(rows, NP.PROJ_CONFIG, NP.context_constants(rows))
    nb_disp, nb_disp1 = fit_nb(run, TUNE), fit_nb(run, TUNE, "b1")
    w = NP.PROJ_BLEND_W
    out = {"version": NP.VERSION, "config": NP.PROJ_CONFIG, "config_hash": NP.cfg_hash(NP.PROJ_CONFIG),
           "nb_size_b2": nb_disp, "nb_size_b1": nb_disp1, "blend_w": w,
           "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "periods": {}}
    for season, live in ((TUNE, False), (TEST_A, False), (TEST_B, False), (TEST_C, True)):
        print("evaluating", season, flush=True)
        out["periods"][season] = evaluate_period(run, data, season, nb_disp, w, live=live, nb_disp1=nb_disp1)
    out["periods"][TEST_C]["label"] = "2026-27 replay: point-in-time reconstruction, NOT the prospective test C"
    out["verdicts"] = verdicts(out["periods"], prospective=None)
    (HERE / "PROJECTION_RESULTS.json").write_text(json.dumps(out, indent=1, default=float))
    (HERE / "PROJECTION_RESULTS.md").write_text(render_md(out))
    write_results_module(out)
    print("wrote PROJECTION_RESULTS.json and .md")
    for v in out["verdicts"]:
        print(" ", v)


def freeze(data):
    """The numbers frozen with PROJ_CONFIG: context multipliers (2022-23), the kNN feature scale (2022-23, under the
    config), the M1+mkt blend weight (2023-24 FanDuel lines). History and tuning data only."""
    rows = data["rows"]
    consts = NP.context_constants(rows)
    run = Run(rows, NP.PROJ_CONFIG, consts)
    w, ll = fit_blend(run, data, TUNE)
    print("PROJ_CONSTS =", json.dumps({k: [round(x, 5) for x in v] for k, v in consts.items()}))
    print("PROJ_SCALE =", json.dumps([round(float(x), 5) for x in run.scale]))
    print("PROJ_BLEND_W =", w, " (2023-24 log loss %.5f)" % ll)


def _ci(c, f="%+.4f"):
    return "–" if not c else (f % c[0]) + " [" + (f % c[1]) + ", " + (f % c[2]) + "]"


def render_md(out):
    L = ["# Projection engine — results (generated by `nba_proj_eval.py --final`)", "",
         f"Version `{out['version']}`, config `{out['config_hash']}` (tuned on 2023-24 only), generated {out['generated_at']}.",
         "Pre-registration: `NBA_PROJECTION_PREREG.md`. Brackets are date-clustered bootstrap 95% intervals "
         f"({BOOT} reps, seed {SEED}). Lower is better for MAE, RMSE, CRPS, log loss and Brier.", "",
         "## Verdicts (the prereg's decision lines, applied by `verdicts()`)", ""]
    L += [f"- {v}" for v in out.get("verdicts", [])]
    for season, P in out["periods"].items():
        if not P:
            continue
        role = {TUNE: "tuning (in-sample for every setting)", TEST_A: "held-out test A", TEST_B: "held-out test B"}.get(season, P.get("label", ""))
        L += ["", f"## {season} — {role}", "", f"{P['n']:,} player-games over {P['dates']} dates.", "",
              "| stat | MAE B1 | MAE B2 | MAE M1 mean | MAE M1 median | RMSE B2 | RMSE M1 | CRPS B1 | CRPS B2 | CRPS M1 | M1−B2 CRPS | 80% cover | PIT deciles (min–max) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for st, r in P["stats"].items():
            pit = r.get("pit_deciles") or [0]
            L.append(f"| {st} | {r['b1']['mae']:.3f} | {r['b2']['mae']:.3f} | {r['m1']['mae']:.3f} | {r['m1']['mae_median']:.3f} | "
                     f"{r['b2']['rmse']:.3f} | {r['m1']['rmse']:.3f} | {r['b1'].get('crps', float('nan')):.3f} | "
                     f"{r['b2']['crps']:.3f} | {r['m1']['crps']:.3f} | {_ci(r['m1_minus_b2_crps'])} | {r['cover80']:.3f} | {min(pit):.3f}–{max(pit):.3f} |")
        L += ["", f"Normalized CRPS (the tuning objective): M1 {P['norm_crps_m1']:.5f}, B2 {P['norm_crps_b2']:.5f}; "
              f"M1 − B2 {_ci(P['norm_crps_m1_minus_b2'], '%+.5f')}; M1 − B1 {_ci(P.get('norm_crps_m1_minus_b1'), '%+.5f')}."]
        M = P.get("market")
        if M:
            L += ["", f"### FanDuel lines ({M['n']:,} two-sided, {M['pushes']} pushes excluded)", "",
                  "| forecast | log loss | Brier |", "|---|---|---|"]
            for lab, nm in (("m1", "M1 (model only)"), ("market", "FanDuel close, de-vigged (B3)"), ("m1+mkt", "M1 + market blend")):
                L.append(f"| {nm} | {M[lab]['logloss']:.5f} | {M[lab]['brier']:.5f} |")
            L += ["", f"M1 − close: {_ci(M['m1_minus_market_ll'], '%+.5f')}. Blend − close: {_ci(M['blend_minus_market_ll'], '%+.5f')}. "
                  f"As a point forecast: the line's MAE {M['mae_line']:.3f}, the M1 mean's {M['mae_m1_mean']:.3f}.", "",
                  "| market | n | M1 | close | blend | M1 − close |", "|---|---|---|---|---|---|"]
            for mk, r in sorted(M["by_market"].items()):
                L.append(f"| {mk} | {r['n']:,} | {r['m1_ll']:.4f} | {r['market_ll']:.4f} | {r['blend_ll']:.4f} | {_ci(r['m1_minus_market'])} |")
            L += ["", "Reliability (bucket: n, mean forecast → observed over rate):", ""]
            for lab in ("reliability_m1", "reliability_blend", "reliability_market"):
                cells = [f"{n}: {m:.2f}→{o:.2f}" for n, m, o in M.get(lab, []) if n]
                L.append(f"- {lab.split('_')[1]}: " + "; ".join(cells))
            L += ["", "| segment | n | M1 | close | blend |", "|---|---|---|---|---|"]
            for k, r in M.get("segments", {}).items():
                L.append(f"| {k} | {r['n']:,} | {r['m1_ll']:.4f} | {r['market_ll']:.4f} | {r['blend_ll']:.4f} |")
            sim = M.get("sim")
            if sim:
                L += ["", f"Pre-specified simulation (blend − FanDuel ≥ 0.03, flat 1u at the snapshot price): {sim['bets']:,} bets, "
                      f"win rate {sim['win_rate']:.3f}, ROI {sim['roi']:+.4f} [{sim['roi_ci'][0]:+.4f}, {sim['roi_ci'][1]:+.4f}], "
                      f"max drawdown {sim['max_drawdown_units']:.1f} units."]
    L += ["", "## Limits", "", "The historical market (−29 min) knows injuries and lineups the historical model does not; the model "
          "has no injury input. Historical minutes are whole numbers; positions are static. 2025-26 has no historical lines. "
          "The 2026-27 replay is a point-in-time reconstruction over a few nights, not the prospective test.", ""]
    return "\n".join(L)


def write_results_module(out, path=None):
    """nba_proj_results.py: the headline numbers as a Python literal, for the page on the VM (code-only deploy)."""
    import pprint
    keep = {"version": out["version"], "generated_at": out["generated_at"], "config_hash": out["config_hash"],
            "verdicts": out.get("verdicts"), "periods": {}}
    for season, p in out["periods"].items():
        if not p:
            continue
        q = {"n": p["n"], "dates": p["dates"], "norm_crps_m1_minus_b2": p["norm_crps_m1_minus_b2"], "label": p.get("label"),
             "stats": {st: {"cover80": v["cover80"]} for st, v in p["stats"].items()}}
        if p.get("market"):
            m = p["market"]
            q["market"] = {k: m[k] for k in ("n", "m1", "market", "m1+mkt", "m1_minus_market_ll", "blend_minus_market_ll", "sim") if k in m}
        keep["periods"][season] = q
    (Path(path) if path else HERE / "nba_proj_results.py").write_text(
        '"""Generated by nba_proj_eval.py --final from PROJECTION_RESULTS.json (the VM deploy copies code only). '
        'Do not edit."""\nRESULTS = ' + pprint.pformat(keep, width=110, sort_dicts=False) + "\n")


def verdicts(P, prospective=None):
    """The prereg's decision lines, applied mechanically. Test C is the prospective record only (nba_proj_score.json
    from the VM's forecast log), never the 2026-27 replay."""
    A, B = P.get(TEST_A) or {}, P.get(TEST_B) or {}
    pr = prospective or {}
    C = {"market": {"n": pr.get("with_close", 0), "blend_minus_market_ll": pr.get("blend_minus_close"),
                    "m1_minus_market_ll": pr.get("model_minus_close")}}
    below = lambda c: c is not None and c[2] < 0
    out = []
    for base in ("b2", "b1"):
        k = f"norm_crps_m1_minus_{base}"
        ok = below(A.get(k)) and below(B.get(k))
        out.append(f"M1 projects stats better than {base.upper()} (CRPS, A and B): {'YES' if ok else 'NO'}.")
    rel = (A.get("market") or {}).get("reliability_m1") or []
    big = [(n, m, o) for n, m, o in rel if n >= 200 and m is not None]
    cal = bool(big) and all(abs(m - o) <= .03 for n, m, o in big)                  # no data is not a pass
    stats_a = list((A.get("stats") or {}).values())
    pit = bool(stats_a) and all(st.get("pit_deciles") and all(.10 <= x <= .12 for x in st["pit_deciles"]) for st in stats_a)
    out.append(f"M1 is calibrated (FanDuel-line reliability within 3 pts and PIT deciles 10-12% on A): "
               f"{'YES' if cal and pit else 'NO'} (reliability {'ok' if cal else 'fails'}, PIT {'ok' if pit else 'fails'}).")
    big_b = [(n, m, o) for n, m, o in (A.get("market") or {}).get("reliability_blend") or [] if n >= 200 and m is not None]
    out.append("M1+mkt reliability within 3 pts on A: " + ("YES." if big_b and all(abs(m - o) <= .03 for n, m, o in big_b) else "NO."))
    am, cm = A.get("market") or {}, C.get("market") or {}
    c_ok = cm.get("n", 0) >= 2000
    add = below(am.get("blend_minus_market_ll")) and (not c_ok or (cm.get("blend_minus_market_ll") or [1])[0] < 0)
    c_note = "" if c_ok else " (C has %d graded props of the 2,000 required)" % cm.get("n", 0)
    word = "YES" if add and c_ok else "NOT ESTABLISHED" if add else "NO"
    out.append("M1 adds information beyond FanDuel's close (blend - close log loss, A%s): %s%s." % (" and C" if c_ok else "", word, c_note))
    beat = below(am.get("m1_minus_market_ll")) and c_ok and below(cm.get("m1_minus_market_ll"))
    out.append("M1 beats FanDuel's close (model - close log loss, A and C): %s." % ("YES" if beat else "NO"))
    return out


# ── prospective test C (VM, nightly): the logged forecasts against results and the close ──────────────────
def prospective(log_db, lines_db, matchup_db, out_json):
    """Grade every 'cutoff' forecast (the last one made before tip − 30 min) whose game is final:
    log loss of the model, the blend and the close (no-vig at the same line, the board as of tip), and CLV of
    the 'first' forecast: no-vig close probability of the side the model favored minus the no-vig probability
    when it was made (positive = the close moved toward the model; not profit). Writes out_json."""
    import nba_research as R
    import sqlite3 as sq
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "version": NP.VERSION,
           "graded": 0, "note": "prospective test C (NBA_PROJECTION_PREREG.md); small samples are reported as they are"}
    lg, q, m = PD._ro(log_db), PD._ro(lines_db), PD._ro(matchup_db)
    if lg is None or q is None or m is None:
        out["error"] = "missing store"
        Path(out_json).write_text(json.dumps(out))
        return out
    fc = defaultdict(dict)
    for kind, gid, pid, mk, tip, line, book, o, u, po, pp, pb, mean in lg.execute(
            "SELECT kind, gid, pid, market, tip, line, book, over, under, p_over, p_push, p_blend, mean FROM forecasts "
            "WHERE version = ?", (NP.VERSION,)):
        fc[(gid, pid, mk)][kind] = {"tip": tip, "line": line, "book": book, "over": o, "under": u, "p": po, "pb": pb}
    box = {}
    for gid, pid, mn, pts, reb, ast, fg3m, stl, blk, tov in m.execute(
            "SELECT p.gid, p.pid, p.min, p.pts, p.reb, p.ast, p.fg3m, p.stl, p.blk, p.tov FROM player_games p JOIN games g "
            "ON g.gid = p.gid WHERE g.home_pts IS NOT NULL"):
        box[(gid, pid)] = {"min": mn, "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m, "stl": stl, "blk": blk, "tov": tov}
    gids = sorted({k[0] for k in fc if any(k[0] == g for g, _ in box)})
    close = {}
    if gids:
        tips = {g: t for g, t in q.execute(f"SELECT gid, MIN(tip_utc) FROM quotes WHERE gid IN ({','.join('?' * len(gids))}) "
                                           f"GROUP BY gid", gids)}
        rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN "
                         f"({','.join('?' * len(gids))}) AND pid IS NOT NULL ORDER BY seen_at", gids)
        for t, changed in R.replay(r for r in rows if r[4] in PD.MARKET_PARTS):
            for k, st in changed.items():
                if t < (tips.get(k[0]) or "")[:19]:
                    close[k] = dict(st)
    recs = []
    for (gid, pid, mk), kinds in fc.items():
        c = kinds.get("cutoff")
        b = box.get((gid, pid))
        if c is None or b is None or not b["min"]:
            continue                                           # not final yet, or he did not play (void)
        actual = sum(b[s] for s in PD.MARKET_PARTS[mk])
        if actual == c["line"]:
            continue                                           # push: void
        st = close.get((gid, pid, mk, c["book"])) or {}
        co, cu = st.get((c["line"], "over")), st.get((c["line"], "under"))
        p_close = float(NP.no_vig(co, cu)) if co and cu else None
        f = kinds.get("first")
        clv = None
        if f and p_close is not None and f["line"] == c["line"]:
            p_then = float(NP.no_vig(f["over"], f["under"]))
            side_over = f["p"] >= p_then
            clv = (p_close - p_then) if side_over else (p_then - p_close)
        recs.append({"y": float(actual > c["line"]), "p": c["p"], "pb": c["pb"], "pc": p_close, "clv": clv,
                     "date": c["tip"][:10], "market": mk})
    out["graded"] = len(recs)
    if recs:
        y = np.array([r["y"] for r in recs])
        out["model_logloss"] = float(logloss(np.array([r["p"] for r in recs]), y).mean())
        out["blend_logloss"] = float(logloss(np.array([r["pb"] for r in recs]), y).mean())
        wc = [r for r in recs if r["pc"] is not None]
        if wc:
            yc = np.array([r["y"] for r in wc])
            out["with_close"] = len(wc)
            out["close_logloss"] = float(logloss(np.array([r["pc"] for r in wc]), yc).mean())
            out["model_minus_close"] = list(boot_ci(logloss(np.array([r["p"] for r in wc]), yc) - logloss(np.array([r["pc"] for r in wc]), yc),
                                                    [r["date"] for r in wc], reps=1000))
            out["blend_minus_close"] = list(boot_ci(logloss(np.array([r["pb"] for r in wc]), yc) - logloss(np.array([r["pc"] for r in wc]), yc),
                                                    [r["date"] for r in wc], reps=1000))
        cl = [r["clv"] for r in recs if r["clv"] is not None]
        if cl:
            out["clv"] = {"n": len(cl), "mean": float(np.mean(cl)), "share_positive": float(np.mean(np.array(cl) > 0))}
        out["from"], out["to"] = min(r["date"] for r in recs), max(r["date"] for r in recs)
    tmp = Path(str(out_json) + ".tmp")
    tmp.write_text(json.dumps(out))
    import os
    os.replace(tmp, out_json)
    return out


if __name__ == "__main__":
    main()
