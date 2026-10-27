#!/usr/bin/env python3
"""Empirical audit of the projection engine against FanDuel's lines (NBA_PROJECTION_AUDIT.md). Diagnostic only:
development after exposure on 2023-24 and 2024-25, nothing tuned, no model changed.

A1  Where the model disagrees with FanDuel: realized over rate by (model P − FanDuel no-vig P) bucket.
A2  Does the model add information beyond the line? Logistic regression of the outcome on logit(FanDuel) and
    logit(model), fitted on 2023-24 and scored on 2024-25.
A3  Mean bias: actual − projected mean (the market's stat) by segment.
A4  FanDuel's own calibration: realized over rate against its no-vig probability, by market (an over/under lean).
A5  Other books vs FanDuel at the same line and moment (−29 min): DraftKings, BetMGM and Caesars, de-vigged
    and averaged, against FanDuel's de-vigged price. Who predicts better, and what happens where they disagree.
    python3 nba_proj_audit.py           # prints tables, writes .projdata/audit.json
"""
import json
import pickle
from collections import defaultdict

import numpy as np

import nba_proj11 as P
import nba_proj_eval as E
import nba_project as NP

SEASONS = ("2023-24", "2024-25")


def ci(x, dates, reps=1000):
    m, lo, hi = E.boot_ci(x, dates, reps=reps)
    return [round(m, 4), round(lo, 4), round(hi, 4)]


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit_logit(X, y, iters=50):
    """Newton-Raphson logistic regression with intercept; returns coefficients."""
    X = np.c_[np.ones(len(X)), X]
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (y - p)
        H = (X * (p * (1 - p))[:, None]).T @ X + 1e-6 * np.eye(X.shape[1])
        w += np.linalg.solve(H, g)
    return w


def main():
    data = E.load()
    rows = data["rows"]
    run = E.Run(rows, NP.PROJ_CONFIG, NP.context_constants(rows))
    F = pickle.loads(P.FEAT.read_bytes())
    fams = np.array(F["fams"])
    X0 = F["X"][:, fams == "F0"].astype(float)
    arm11 = P.arm_run(run, P.apply_residual(run.mu["m1"], P.residual_walk(run.date, X0, P.residual_targets(run), 10)))
    other = defaultdict(list)                               # (gid, pid, market, line) -> [no-vig P(over)] of DK/MGM/CZR
    for ln in data["hist"]:
        if ln["book"] != "fd" and ln["over"] and ln["under"]:
            other[(ln["gid"], ln["pid"], ln["market"], ln["line"])].append(float(NP.no_vig(ln["over"], ln["under"])))
    home = np.array([r.get("home") for r in rows], dtype=object)
    out = {}
    for season in SEASONS:
        s10, s11 = P.score_season(run, data, season), P.score_season(arm11, data, season)
        fd, f11 = s10["fd"], s11["fd"]
        y, pf, pm, pm11 = fd["over"], fd["p_mkt"], fd["p_m1"], f11["p_m1"]
        rws, dates = fd["row"], run.date[fd["row"]]
        res = {"n": int(len(y))}
        # A1
        edges = [-1, -.15, -.08, -.03, .03, .08, .15, 1]
        for key, mp_ in (("A1", pm), ("A1_proj11", pm11)):
            dis = mp_ - pf
            res[key] = []
            for lo_, hi_ in zip(edges, edges[1:]):
                k = (dis >= lo_) & (dis < hi_)
                if k.sum():
                    res[key].append({"model_minus_fd": f"[{lo_:+.2f},{hi_:+.2f})", "n": int(k.sum()), "model_p": round(float(mp_[k].mean()), 3),
                                     "fd_p": round(float(pf[k].mean()), 3), "over_rate": round(float(y[k].mean()), 3)})
        # A2 (coefficients fitted on this season; scoring on the other is done below)
        res["A2_coef"] = {"proj-1.0": [round(float(c), 3) for c in fit_logit(np.c_[logit(pf), logit(pm)], y)],
                          "proj-1.1": [round(float(c), 3) for c in fit_logit(np.c_[logit(pf), logit(pm11)], y)]}
        res["_arrays"] = (pf, pm, pm11, y, dates, rws, fd["market"], fd["line"])
        # A3 mean bias: actual − model mean (market stat), by segment
        mu = fd["mu"]
        Yd = {m: np.array([sum(run.Y[i, NP.STATS.index(s)] for s in E.PD.MARKET_PARTS[m]) for i in rws[fd["market"] == m]])
              for m in sorted(set(fd["market"]))}
        res["A3"], res["A3_proj11"] = {}, {}
        for m in sorted(set(fd["market"])):
            k = fd["market"] == m
            r11 = Yd[m] - f11["mu"][k]
            q11 = np.quantile(f11["mu"][k], [.2, .4, .6, .8])
            b11 = np.digitize(f11["mu"][k], q11)
            res["A3_proj11"][m] = {"bias_model": round(float(r11.mean()), 3),
                                   "by_projection_quintile": [round(float(r11[b11 == b].mean()), 3) for b in range(5)]}
            resid = Yd[m] - mu[k]
            line_resid = Yd[m] - fd["line"][k]
            q = np.quantile(mu[k], [.2, .4, .6, .8])
            band = np.digitize(mu[k], q)
            res["A3"][m] = {"bias_model": round(float(resid.mean()), 3), "bias_line": round(float(line_resid.mean()), 3),
                            "by_projection_quintile": [round(float(resid[band == b].mean()), 3) for b in range(5)],
                            "home": round(float(resid[home[rws[k]] == 1].mean()), 3), "away": round(float(resid[home[rws[k]] == 0].mean()), 3),
                            "b2b": round(float(resid[run.rest[rws[k]] == 1].mean()), 3) if (run.rest[rws[k]] == 1).any() else None,
                            "oct_nov": round(float(resid[np.char.startswith(run.date[rws[k]].astype(str), (season[:4] + "-1"))].mean()), 3)}
        # A4 FanDuel calibration
        res["A4"] = {"all": {"fd_p_over": round(float(pf.mean()), 4), "over_rate": round(float(y.mean()), 4),
                             "fd_minus_realized": ci(pf - y, dates)}}
        for m in sorted(set(fd["market"])):
            k = fd["market"] == m
            res["A4"][m] = {"n": int(k.sum()), "fd_p_over": round(float(pf[k].mean()), 4), "over_rate": round(float(y[k].mean()), 4),
                            "fd_minus_realized": ci(pf[k] - y[k], dates[k])}
        # A5 other books at the same line and moment
        po = np.array([np.mean(other.get((rows[i]["gid"], rows[i]["pid"], m, l), [np.nan])) for i, m, l in zip(rws, fd["market"], fd["line"])])
        nb = np.array([len(other.get((rows[i]["gid"], rows[i]["pid"], m, l), [])) for i, m, l in zip(rws, fd["market"], fd["line"])])
        k = np.isfinite(po)
        lf, lo_ = E.logloss(pf[k], y[k]), E.logloss(po[k], y[k])
        lmix = E.logloss((pf[k] + po[k]) / 2, y[k])
        res["A5"] = {"n_with_other_books": int(k.sum()), "mean_books": round(float(nb[k].mean()), 2),
                     "fd_ll": round(float(lf.mean()), 5), "others_ll": round(float(lo_.mean()), 5), "avg_ll": round(float(lmix.mean()), 5),
                     "others_minus_fd": ci(lo_ - lf, dates[k]), "avg_minus_fd": ci(lmix - lf, dates[k])}
        gap = po[k] - pf[k]
        res["A5"]["by_gap"] = []
        for lo2, hi2 in zip([-1, -.06, -.03, -.01, .01, .03, .06], [-.06, -.03, -.01, .01, .03, .06, 1]):
            g = (gap >= lo2) & (gap < hi2)
            if g.sum():
                res["A5"]["by_gap"].append({"others_minus_fd": f"[{lo2:+.2f},{hi2:+.2f})", "n": int(g.sum()), "fd_p": round(float(pf[k][g].mean()), 3),
                                            "others_p": round(float(po[k][g].mean()), 3), "over_rate": round(float(y[k][g].mean()), 3)})
        out[season] = res
    # A2 out of sample: fit on 2023-24, score 2024-25
    pf0, pm0, pm110, y0, *_ = out["2023-24"]["_arrays"]
    pf1, pm1, pm111, y1, d1, *_ = out["2024-25"]["_arrays"]
    for name, a, b in (("proj-1.0", pm0, pm1), ("proj-1.1", pm110, pm111)):
        w = fit_logit(np.c_[logit(pf0), logit(a)], y0)
        p1 = 1 / (1 + np.exp(-(w[0] + w[1] * logit(pf1) + w[2] * logit(b))))
        out.setdefault("A2_oos", {})[name] = {"coef_fit_2023_24": [round(float(c), 3) for c in w],
                                             "combined_minus_fd_2024_25": ci(E.logloss(p1, y1) - E.logloss(pf1, y1), d1)}
    for s in SEASONS:
        out[s].pop("_arrays")
    (E.DATA / "audit.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
