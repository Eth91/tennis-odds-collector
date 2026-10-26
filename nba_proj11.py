#!/usr/bin/env python3
"""proj-1.1 (NBA_PROJ11_PREREG.md): a residual ridge layer on proj-1.0's means, the pre-registered arms, and
their walk-forward evaluation against proj-1.0 and FanDuel's close.
    python3 nba_proj11.py --features      # build and cache the feature matrix (needs nba_stats_fetch.py data)
    python3 nba_proj11.py --run           # λ choice, the 2023-24 keep rule, then every arm once on 2024-25, 2025-26
"""
import argparse
import copy
import json
import pickle
import time

import numpy as np

import nba_proj_diag as DG
import nba_proj_eval as E
import nba_project as NP

DATA = E.DATA
FEAT = DATA / "p11_features.pkl"
OUT_JSON = E.HERE / "PROJ11_RESULTS.json"
OUT_MD = E.HERE / "PROJ11_RESULTS.md"
FAMS = ("F0", "F1", "F2", "F3", "F4", "F5", "F6")
LAMS = (1, 10, 100, 1000)
DEV, EXPOSED, STATS_ONLY = "2023-24", "2024-25", "2025-26"
FIRST_FIT = "2022-11-01"
REPS, SEED = 4000, 7


def residual_targets(run):
    """[n, 8]: r_min = log((min+1)/(μ_min+1)); r_s = log((s+.5)/(μ_s+.5)) − r_min (per-minute residual)."""
    mu, Y = run.mu["m1"], run.Y
    r = np.zeros_like(mu)
    r[:, 0] = np.log((Y[:, 0] + 1) / (np.maximum(mu[:, 0], 0) + 1))
    r[:, 1:] = np.log((Y[:, 1:] + .5) / (np.maximum(mu[:, 1:], 0) + .5)) - r[:, :1]
    return r


def _next_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y + (mo == 12)}-{(mo % 12) + 1:02d}"


def residual_walk(date, X, R, lam_mult):
    """Monthly walk-forward ridge: for each month from FIRST_FIT, fit on every earlier row, predict that month.
    Standardized features, no intercept in the prediction (prereg implementation note 1). Returns [n, 8]."""
    pred = np.zeros_like(R)
    if X.shape[1] == 0:
        return pred
    for m in sorted({d[:7] for d in date}):
        start = m + "-01"
        if start < FIRST_FIT:
            continue
        tr = date < start
        te = (date >= start) & (date < _next_month(m) + "-01")
        if not tr.any() or not te.any():
            continue
        mu_, sd_, W = fit_weights(X, R, tr, lam_mult)
        pred[te] = ((X[te] - mu_) / sd_) @ W
    return pred


def fit_weights(X, R, tr, lam_mult):
    """(feature means, sds, W [p, 8]) of the ridge fit on rows `tr`: standardized features, centred targets."""
    p = X.shape[1]
    mu_, sd_ = X[tr].mean(0), X[tr].std(0)
    sd_ = np.where(sd_ > 1e-9, sd_, 1.0)
    Z = (X[tr] - mu_) / sd_
    y = R[tr] - R[tr].mean(0)
    return mu_, sd_, np.linalg.solve(Z.T @ Z + lam_mult * p * np.eye(p), Z.T @ y)


def apply_residual(mu, f):
    """μ' from proj-1.0's μ and the fitted feature effects (prereg, Model)."""
    out = np.empty_like(mu)
    out[:, 0] = (np.maximum(mu[:, 0], 0) + 1) * np.exp(f[:, 0]) - 1
    out[:, 1:] = (np.maximum(mu[:, 1:], 0) + .5) * np.exp(f[:, :1] + f[:, 1:]) - .5
    return np.maximum(out, 0)


def arm_run(run, mu_new):
    """A copy of proj-1.0's Run whose M1 means are μ' (the analog ensemble rebuilt around them)."""
    a = copy.copy(run)
    a.mu = dict(run.mu, m1=mu_new)
    hist = run.season == "2022-23"
    f = NP.features(mu_new[hist], run.n_hist[hist], run.rest[hist], run.cfg)
    a.scale = np.where(f.std(0) > 0, f.std(0), 1.0)
    return a


def boot(diff, dates, reps=REPS, seed=SEED):
    """Date-clustered bootstrap: mean, 95% interval, one-sided p (share of resampled means >= 0)."""
    diff, dates = np.asarray(diff, float), np.asarray(dates)
    ud, inv = np.unique(dates, return_inverse=True)
    s, n = np.bincount(inv, weights=diff), np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(ud), size=(reps, len(ud)))
    means = s[pick].sum(1) / n[pick].sum(1)
    return {"mean": float(diff.mean()), "lo": float(np.quantile(means, .025)), "hi": float(np.quantile(means, .975)),
            "p_ge0": float((means >= 0).mean())}


def holm(pvals, alpha=0.05):
    """{name: reject} by Holm's step-down procedure."""
    order = sorted(pvals, key=pvals.get)
    out, m = {}, len(order)
    still = True
    for k, name in enumerate(order):
        still = still and pvals[name] <= alpha / (m - k)
        out[name] = still
    return out


def score_season(arm, data, season, w_blend=None):
    """Per-row normalized CRPS, per-stat CRPS and log score, and the FanDuel-line arrays for one season."""
    idx = np.where(arm.season == season)[0]
    d = arm.dist(idx)
    crps = E.crps_by_stat(arm, idx, d)
    ncrps = np.mean([crps[s] / arm.sd[j] for j, s in enumerate(NP.STATS)], 0)
    out = {"idx": idx, "ncrps": ncrps, "crps": {s: float(crps[s].mean()) for s in NP.STATS},
           "mae": {s: float(np.abs(d.mean(s) - arm.Y[idx, j]).mean()) for j, s in enumerate(NP.STATS)}}
    joined = E.fd_join(arm, data["hist"], set(idx.tolist()))
    if joined:
        mp = E.market_probs(arm, d, idx, joined)
        ok = ~mp["push"]
        out["fd"] = {k: v[ok] for k, v in mp.items()}
    del d
    return out


def ll(p, y):
    return E.logloss(p, y)


def fit_w(fd):
    grid = np.round(np.arange(0, 1.01, 0.05), 2)
    return float(min(grid, key=lambda w: ll(NP.blend(fd["p_m1"], fd["p_mkt"], w), fd["over"]).mean()))


def reliability(p, y):
    return E.reliability(p, y)


def compare(a, b, run):
    """Arm a vs arm b (same season): CRPS and FanDuel-line log-loss differences with intervals."""
    dates = run.date[a["idx"]]
    res = {"ncrps": float(a["ncrps"].mean()), "ncrps_minus_ref": boot(a["ncrps"] - b["ncrps"], dates)}
    if "fd" in a:
        fa, fb = a["fd"], b["fd"]
        assert np.array_equal(fa["row"], fb["row"]) and np.array_equal(fa["line"], fb["line"])
        fd_dates = run.date[fa["row"]]
        la, lb, lc = ll(fa["p_m1"], fa["over"]), ll(fb["p_m1"], fb["over"]), ll(fa["p_mkt"], fa["over"])
        res.update(n_lines=int(len(la)), model_ll=float(la.mean()), close_ll=float(lc.mean()),
                   model_minus_ref_ll=boot(la - lb, fd_dates), model_minus_close_ll=boot(la - lc, fd_dates))
    return res


def build_features(rows):
    import nba_proj11_feat as FT
    t0 = time.time()
    X, names, fams, report = FT.build(rows)
    FEAT.write_bytes(pickle.dumps({"X": X, "names": names, "fams": fams, "report": report, "n": len(rows)}))
    print(f"features: {X.shape[1]} columns over {X.shape[0]} rows in {time.time() - t0:.0f}s; "
          f"coverage {report['coverage']}; missing columns {report['missing_columns']}")
    return X, names, fams, report


def run_all():
    data = E.load()
    rows = data["rows"]
    t0 = time.time()
    run = E.Run(rows, NP.PROJ_CONFIG, NP.context_constants(rows))
    print(f"proj-1.0 walk: {time.time() - t0:.0f}s")
    F = pickle.loads(FEAT.read_bytes())
    assert F["n"] == len(rows)
    X, names, fams = F["X"].astype(float), F["names"], np.array(F["fams"])
    R = residual_targets(run)
    import nba_proj11_feat as FT
    proxy = np.array([n in FT.F0_PROXY for n in names])
    cache = {}

    def arm(cols, lam):
        key = (tuple(np.where(cols)[0]), lam)
        if key not in cache:
            f = residual_walk(run.date, X[:, cols], R, lam)
            cache[key] = arm_run(run, apply_residual(run.mu["m1"], f))
        return cache[key]

    a0 = run
    res = {"version": "proj-1.1-dev", "base": NP.VERSION, "base_config": NP.cfg_hash(NP.PROJ_CONFIG),
           "features": {"n": int(X.shape[1]), "report": F["report"], "by_family": {k: int((fams == k).sum()) for k in FAMS}},
           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    # 1) λ: A_all on 2023-24 normalized CRPS
    s0 = {DEV: score_season(a0, data, DEV)}
    lam_scores = {}
    allc = np.ones(X.shape[1], bool)
    for lam in LAMS:
        sc = score_season(arm(allc, lam), data, DEV)
        lam_scores[lam] = float(sc["ncrps"].mean())
        print(f"λ {lam}×p: 2023-24 normalized CRPS {lam_scores[lam]:.5f} (A0 {s0[DEV]['ncrps'].mean():.5f})", flush=True)
    lam = min(lam_scores, key=lam_scores.get)
    res["lambda"] = {"grid": lam_scores, "chosen": lam}
    # 2) arms
    arms = {"A0": None}
    for k in FAMS:
        arms[f"A_{k}"] = fams == k
    arms["A_all"] = allc
    for k in FAMS:
        arms[f"A_all-{k}"] = fams != k
    # 3) keep rule on 2023-24
    dev = {"A0": s0[DEV]}
    for name, cols in arms.items():
        if cols is not None and name not in dev:
            dev[name] = score_season(arm(cols, lam), data, DEV)
            print(f"  2023-24 {name}: ncrps {dev[name]['ncrps'].mean():.5f}", flush=True)
    single = {k: compare(dev[f"A_{k}"], dev["A0"], run) for k in FAMS}
    rej = holm({k: single[k]["ncrps_minus_ref"]["p_ge0"] for k in FAMS})
    keep = [k for k in FAMS if rej[k] and single[k].get("model_minus_ref_ll", {"mean": 0})["mean"] <= 0]
    res["keep_rule"] = {k: {"holm_reject": rej[k], "ncrps": single[k]["ncrps_minus_ref"],
                            "fd_ll": single[k].get("model_minus_ref_ll")} for k in FAMS}
    res["kept"] = keep
    kc = np.isin(fams, keep)
    arms["A_keep"] = kc
    arms["A_keep-proxy"] = kc & ~proxy
    print(f"kept families: {keep}", flush=True)
    # 4) blend weights on 2023-24, per arm
    for name in ("A_keep", "A_keep-proxy"):
        if arms[name].any():
            dev[name] = score_season(arm(arms[name], lam), data, DEV)
        else:
            dev[name] = dev["A0"]
    wb = {name: fit_w(s["fd"]) for name, s in dev.items() if "fd" in s}
    res["blend_w"] = wb
    # 5) every arm once on 2023-24 (dev), 2024-25 (exposed), 2025-26 (stats only)
    res["seasons"] = {}
    for season in (DEV, EXPOSED, STATS_ONLY):
        sc = dev if season == DEV else {}
        if season != DEV:
            sc["A0"] = score_season(a0, data, season)
            for name, cols in arms.items():
                if cols is not None:
                    sc[name] = score_season(arm(cols, lam), data, season) if cols.any() else sc["A0"]
                    print(f"  {season} {name}: ncrps {sc[name]['ncrps'].mean():.5f}", flush=True)
        out = {}
        for name, s in sc.items():
            c = compare(s, sc["A0"], run)
            c["crps"], c["mae"] = s["crps"], s["mae"]
            if "fd" in s:
                fd = s["fd"]
                pb = NP.blend(fd["p_m1"], fd["p_mkt"], wb.get(name, 0.85))
                lc = ll(fd["p_mkt"], fd["over"])
                c["blend_minus_close_ll"] = boot(ll(pb, fd["over"]) - lc, run.date[fd["row"]])
                c["reliability_model"] = reliability(fd["p_m1"], fd["over"])
                c["reliability_blend"] = reliability(pb, fd["over"])
            out[name] = c
        # breakdowns for A_keep vs A0 vs close
        if "fd" in sc["A_keep"]:
            fa, f0 = sc["A_keep"]["fd"], sc["A0"]["fd"]
            absent = DG.absence_rows(rows)
            seg = {}
            hist_n = run.n_hist[fa["row"]]
            mins = run.mu["m1"][fa["row"], 0]
            ab = np.array([r in absent for r in fa["row"]])
            masks = {"teammate regular out": ab, "no regular out": ~ab, "hist<40": hist_n < 40, "hist40+": hist_n >= 40,
                     "min<25": mins < 25, "min25-32": (mins >= 25) & (mins < 32), "min32+": mins >= 32}
            masks.update({f"market:{m}": fa["market"] == m for m in sorted(set(fa["market"]))})
            for nm, mk in masks.items():
                if mk.sum() < 50:
                    continue
                dd = run.date[fa["row"][mk]]
                la, l0, lc = ll(fa["p_m1"][mk], fa["over"][mk]), ll(f0["p_m1"][mk], f0["over"][mk]), ll(fa["p_mkt"][mk], fa["over"][mk])
                seg[nm] = {"n": int(mk.sum()), "keep_minus_A0": boot(la - l0, dd, reps=1000),
                           "keep_minus_close": boot(la - lc, dd, reps=1000), "A0_minus_close": boot(l0 - lc, dd, reps=1000)}
            out["_segments_A_keep"] = seg
        res["seasons"][season] = out
        if season != DEV:
            sc.clear()
    OUT_JSON.write_text(json.dumps(res, indent=1, default=float))
    OUT_MD.write_text(render(res))
    print(f"wrote {OUT_JSON.name}, {OUT_MD.name} in {(time.time() - t0) / 60:.0f} min")
    return res


def _ci(b, f="%+.4f"):
    return "–" if not b else f"{f % b['mean']} [{f % b['lo']}, {f % b['hi']}]"


def render(res):
    L = ["# proj-1.1 — results (generated by `nba_proj11.py --run`)", "",
         f"Pre-registration: `NBA_PROJ11_PREREG.md`. Base `{res['base']}` ({res['base_config']}). "
         f"{res['features']['n']} features: {res['features']['by_family']}. "
         f"Generated {res['generated_at']}. Intervals: date-clustered bootstrap 95% ({REPS} reps, seed {SEED}).", "",
         "**Status:** development results only. 2023-24 is development; 2024-25 is development after exposure; "
         "2025-26 has no lines. No claim about the books comes from these; the prospective test decides.", "",
         f"λ = {res['lambda']['chosen']} × p (2023-24 normalized CRPS by λ: {res['lambda']['grid']}).", "",
         "## Keep rule (2023-24: family alone vs proj-1.0; Holm across 7, one-sided α = .05; FanDuel log loss not worse)", "",
         "| family | normalized CRPS diff | p (≥ 0) | Holm | FanDuel log loss diff | kept |", "|---|---|---|---|---|---|"]
    for k, v in res["keep_rule"].items():
        L.append(f"| {k} | {_ci(v['ncrps'], '%+.5f')} | {v['ncrps']['p_ge0']:.4f} | {'reject' if v['holm_reject'] else '–'} | "
                 f"{_ci(v['fd_ll'])} | {'**yes**' if k in res['kept'] else 'no'} |")
    L += ["", f"Kept: {res['kept'] or 'none'}.", ""]
    for season, out in res["seasons"].items():
        role = {DEV: "development", EXPOSED: "development after exposure", STATS_ONLY: "stats only (no lines)"}[season]
        L += [f"## {season} — {role}", "", "| arm | normalized CRPS | − proj-1.0 | FanDuel n | model log loss | − proj-1.0 | − close | blend − close |",
              "|---|---|---|---|---|---|---|---|"]
        for name, c in out.items():
            if name.startswith("_"):
                continue
            L.append(f"| {name} | {c['ncrps']:.5f} | {_ci(c['ncrps_minus_ref'], '%+.5f')} | {c.get('n_lines', '–')} | "
                     f"{c.get('model_ll', float('nan')):.5f} | {_ci(c.get('model_minus_ref_ll'))} | {_ci(c.get('model_minus_close_ll'))} | "
                     f"{_ci(c.get('blend_minus_close_ll'))} |")
        seg = out.get("_segments_A_keep")
        if seg:
            L += ["", "A_keep by segment (FanDuel log loss differences):", "", "| segment | n | A_keep − proj-1.0 | A_keep − close | proj-1.0 − close |", "|---|---|---|---|---|"]
            for nm, s in seg.items():
                L.append(f"| {nm} | {s['n']:,} | {_ci(s['keep_minus_A0'])} | {_ci(s['keep_minus_close'])} | {_ci(s['A0_minus_close'])} |")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.features:
        build_features(E.load()["rows"])
    if a.run:
        run_all()


if __name__ == "__main__":
    main()
