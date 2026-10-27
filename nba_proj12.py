#!/usr/bin/env python3
"""proj-1.2 and market tests T1-T4 (NBA_PROJ12_PREREG.md), run once. Base B = proj-1.1.1 (amendment 1 passed).
    python3 nba_proj12.py        # writes PROJ12_RESULTS.json / .md
"""
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

import nba_proj11 as P
import nba_proj11_feat as FT
import nba_proj_audit as AU
import nba_proj_data as PD
import nba_proj_eval as E
import nba_project as NP

OUT_JSON, OUT_MD = E.HERE / "PROJ12_RESULTS.json", E.HERE / "PROJ12_RESULTS.md"
DEV, TEST = "2023-24", "2024-25"
FAMILY = {"points": "scoring", "pts_reb": "scoring", "pts_ast": "scoring", "pra": "scoring",
          "rebounds": "boards_assists", "assists": "boards_assists", "reb_ast": "boards_assists",
          "threes": "threes", "steals": "defense", "blocks": "defense"}
T3_MARKETS = ("rebounds", "assists", "threes", "steals", "blocks")
KS = np.round(np.arange(0.50, 1.6001, 0.01), 2)
T4_EDGE = 0.02


def ci(b):
    return [round(b["mean"], 5), round(b["lo"], 5), round(b["hi"], 5), round(b["p_ge0"], 4)]


def scaled(vals, k):
    """Draws with minutes and every count × k (per-minute production kept), k scalar or [n_k]."""
    k = np.asarray(k, float)
    return vals[None, :, :] * k[:, None, None] if k.ndim else vals * k


def dist_of(vals, mu):
    d = NP.Dist.__new__(NP.Dist)
    d.vals, d.mu = vals, mu
    return d


def season_detail(arm, data, season, need_t3=False):
    """score_season plus, for T3, the implied-minutes probabilities on the non-points markets."""
    s = P.score_season(arm, data, season)
    if not need_t3:
        return s
    idx_all = np.where(arm.season == season)[0]
    fd_pts = {}
    lines = defaultdict(list)
    for i, ln in E.fd_join(arm, data["hist"], set(idx_all.tolist())):
        if ln["market"] == "points":
            fd_pts[i] = ln["line"]
        elif ln["market"] in T3_MARKETS:
            lines[i].append(ln)
    rec = []
    for m in sorted({d[:7] for d in arm.date[idx_all]}):
        idx = idx_all[np.char.startswith(arm.date[idx_all].astype(str), m)]
        idx = idx[[i in fd_pts and i in lines for i in idx]]
        if not len(idx):
            continue
        d = arm.dist(idx)
        for j, i in enumerate(idx):
            v = d.vals[j]                                          # [K, 8]
            vk = scaled(v, KS)                                     # [n_k, K, 8]
            po, pu, _ = dist_of(vk, np.repeat(d.mu[j:j + 1], len(KS), 0)).probs("points", np.full(len(KS), fd_pts[i]))
            k = KS[np.argmin(np.abs(po / np.clip(po + pu, 1e-9, None) - 0.5))]
            dk_ = dist_of(scaled(v, k)[None], d.mu[j:j + 1])
            for ln in lines[i]:
                actual = sum(arm.Y[i, NP.STATS.index(s_)] for s_ in PD.MARKET_PARTS[ln["market"]])
                if actual == ln["line"]:
                    continue
                o_, u_, _ = dk_.probs(ln["market"], [ln["line"]])
                rec.append((i, ln["market"], float(o_[0] / max(o_[0] + u_[0], 1e-9)), float(NP.no_vig(ln["over"], ln["under"])),
                            float(actual > ln["line"]), k))
        del d
    s["t3"] = rec
    return s


def t4(data, rows):
    """The fixed cross-book rule: bet side S at book X when p_FD(S) × odds_X(S) − 1 > 0.02. Flat 1 unit."""
    key = {(r["gid"], r["pid"]): i for i, r in enumerate(rows)}
    by = defaultdict(dict)
    for ln in data["hist"]:
        by[(ln["gid"], ln["pid"], ln["market"], ln["line"])][ln["book"]] = ln
    bets = []
    for (gid, pid, mk, line), books in by.items():
        fd = books.get("fd")
        i = key.get((gid, pid))
        if fd is None or i is None or not fd["over"] or not fd["under"] or mk not in PD.MARKET_PARTS:
            continue
        pf = float(NP.no_vig(fd["over"], fd["under"]))
        actual = sum(rows[i][s_] for s_ in PD.MARKET_PARTS[mk])
        for bk in ("dk", "mgm", "czr"):
            x = books.get(bk)
            if not x:
                continue
            for side, p_side, odds in (("over", pf, x["over"]), ("under", 1 - pf, x["under"])):
                if odds and p_side * odds - 1 > T4_EDGE:
                    if actual == line:
                        profit = 0.0
                    else:
                        won = (actual > line) == (side == "over")
                        profit = odds - 1 if won else -1.0
                    bets.append({"season": rows[i]["season"], "date": rows[i]["date"], "book": bk, "market": mk, "side": side,
                                 "ev_fd": p_side * odds - 1, "profit": profit})
    return bets


def main():
    t0 = time.time()
    data = E.load()
    rows = data["rows"]
    run = E.Run(rows, NP.PROJ_CONFIG, NP.context_constants(rows))
    X, names, fams, _ = FT.build(rows, families=("F0",), f0_rule="1.1.1")
    R = P.residual_targets(run)
    mu_b = P.apply_residual(run.mu["m1"], P.residual_walk(run.date, X.astype(float), R, 10))
    B = P.arm_run(run, mu_b)
    res = {"base": "proj-1.1.1", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tests": {}}
    sB = {s: season_detail(B, data, s, need_t3=True) for s in (DEV, TEST)}
    # T1: Mincer-Zarnowitz per stat on 2023-24 (B's means), applied everywhere; the ensemble rebuilt around μ″
    dev = run.season == DEV
    ab = []
    for j in range(NP.NS):
        A_ = np.c_[np.ones(dev.sum()), mu_b[dev, j]]
        ab.append(np.linalg.lstsq(A_, run.Y[dev, j], rcond=None)[0])
    ab = np.array(ab)
    mu_c = np.maximum(ab[:, 0] + ab[:, 1] * mu_b, 0)
    T1 = P.arm_run(run, mu_c)
    s1 = P.score_season(T1, data, TEST)
    fb, f1 = sB[TEST]["fd"], s1["fd"]
    assert np.array_equal(fb["row"], f1["row"])
    d_ll = E.logloss(f1["p_m1"], f1["over"]) - E.logloss(fb["p_m1"], fb["over"])
    dates = run.date[fb["row"]]
    quint = {}
    for m in ("points", "pra", "rebounds", "assists"):
        k = f1["market"] == m
        act = np.array([sum(run.Y[i, NP.STATS.index(s_)] for s_ in PD.MARKET_PARTS[m]) for i in f1["row"][k]])
        for tag, mu_ in (("B", fb["mu"][k]), ("T1", f1["mu"][k])):
            q = np.digitize(mu_, np.quantile(mu_, [.2, .4, .6, .8]))
            quint[f"{m}:{tag}"] = [round(float((act - mu_)[q == b].mean()), 3) for b in range(5)]
    res["tests"]["T1"] = {"mz": [[round(float(a), 4), round(float(b), 4)] for a, b in ab], "fd_ll_T1_minus_B": ci(P.boot(d_ll, dates)),
                          "ncrps_T1_minus_B": ci(P.boot(s1["ncrps"] - sB[TEST]["ncrps"], run.date[s1["idx"]])),
                          "bias_by_quintile_2024_25": quint, "p": P.boot(d_ll, dates)["p_ge0"]}
    # T2: blend with a gap term per family x side, fitted on 2023-24, applied on 2024-25
    def cells(f):
        fam = np.array([FAMILY.get(m, "other") for m in f["market"]])
        side = np.where(f["p_m1"] >= f["p_mkt"], "model_over", "model_under")
        return np.char.add(np.char.add(fam.astype(str), "|"), side.astype(str))
    fd_dev, fd_te = sB[DEV]["fd"], sB[TEST]["fd"]
    c_dev, c_te = cells(fd_dev), cells(fd_te)
    p2 = np.array(fd_te["p_mkt"], float)
    coefs = {}
    for c in sorted(set(c_dev)):
        k = c_dev == c
        lf, lm = AU.logit(fd_dev["p_mkt"][k]), AU.logit(fd_dev["p_m1"][k])
        w = AU.fit_logit(np.c_[lf, lm - lf], fd_dev["over"][k])
        coefs[c] = [round(float(x), 4) for x in w]
        kt = c_te == c
        lf2, lm2 = AU.logit(fd_te["p_mkt"][kt]), AU.logit(fd_te["p_m1"][kt])
        p2[kt] = 1 / (1 + np.exp(-(w[0] + w[1] * lf2 + w[2] * (lm2 - lf2))))
    d2 = E.logloss(p2, fd_te["over"]) - E.logloss(fd_te["p_mkt"], fd_te["over"])
    res["tests"]["T2"] = {"coef_by_cell": coefs, "ll_T2_minus_fd": ci(P.boot(d2, run.date[fd_te["row"]])),
                          "by_cell": {c: {"n": int((c_te == c).sum()), "diff": round(float(d2[c_te == c].mean()), 5)} for c in sorted(set(c_te))},
                          "p": P.boot(d2, run.date[fd_te["row"]])["p_ge0"]}
    # T3: FanDuel-implied minutes, pricing the non-points markets (2024-25 primary; 2023-24 reported)
    for season in (DEV, TEST):
        rec = sB[season]["t3"]
        if not rec:
            continue
        ii = np.array([r[0] for r in rec]); p3 = np.array([r[2] for r in rec]); pf3 = np.array([r[3] for r in rec]); y3 = np.array([r[4] for r in rec])
        d3 = E.logloss(p3, y3) - E.logloss(pf3, y3)
        mk3 = np.array([r[1] for r in rec])
        res["tests"].setdefault("T3", {})[season] = {"n": int(len(rec)), "ll_T3_minus_fd": ci(P.boot(d3, run.date[ii])),
                                                      "k_median": float(np.median([r[5] for r in rec])),
                                                      "by_market": {m: round(float(d3[mk3 == m].mean()), 5) for m in T3_MARKETS if (mk3 == m).any()},
                                                      "p": P.boot(d3, run.date[ii])["p_ge0"]}
    res["tests"]["T3"]["p"] = res["tests"]["T3"][TEST]["p"]
    # T4: the fixed cross-book rule (both seasons are out of sample for it)
    bets = t4(data, rows)
    bets = [b for b in bets if b["season"] in (DEV, TEST)]
    pr, bd = np.array([b["profit"] for b in bets]), np.array([b["date"] for b in bets])
    neg = P.boot(-pr, bd)
    out4 = {"n": int(len(bets)), "roi": round(float(pr.mean()), 5), "ci": [round(-neg["mean"], 5), round(-neg["hi"], 5), round(-neg["lo"], 5)],
            "p": neg["p_ge0"], "by_season": {}, "by_book": {}, "by_market": {}, "by_side": {}}
    for keyname, grp in (("by_season", "season"), ("by_book", "book"), ("by_market", "market"), ("by_side", "side")):
        for g in sorted({b[grp] for b in bets}):
            k = np.array([b[grp] == g for b in bets])
            out4[keyname][g] = {"n": int(k.sum()), "roi": round(float(pr[k].mean()), 5), "win_rate": round(float((pr[k] > 0).mean()), 4)}
    out4["season_points_positive"] = all(v["roi"] > 0 for v in out4["by_season"].values())
    res["tests"]["T4"] = out4
    # Holm across the four (one-sided)
    pv = {t: res["tests"][t]["p"] for t in ("T1", "T2", "T3", "T4")}
    rej = P.holm(pv)
    res["holm"] = rej
    res["pass"] = {"T1": rej["T1"], "T2": rej["T2"], "T3": rej["T3"], "T4": rej["T4"] and out4["season_points_positive"]}
    # H7 (descriptive): FanDuel's over premium under four de-vig methods
    res["H7"] = h7(sB)
    res["runtime_min"] = round((time.time() - t0) / 60, 1)
    OUT_JSON.write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: res[k] for k in ("holm", "pass", "runtime_min")}, indent=1))
    return res


def h7(sB):
    """FanDuel's mean over premium (implied − realized over rate) under multiplicative, additive, power and Shin."""
    out = {}
    for season, s in sB.items():
        f = s["fd"]
        qo, qu = 1 / f["po"], 1 / f["pu"]
        m = qo + qu - 1
        mult = qo / (qo + qu)
        add = qo - m / 2
        lo, hi = np.full(len(qo), .5), np.full(len(qo), 2.0)            # power: qo^k + qu^k = 1
        for _ in range(60):
            k = (lo + hi) / 2
            gt = qo ** k + qu ** k > 1
            lo, hi = np.where(gt, k, lo), np.where(gt, hi, k)
        pw = qo ** ((lo + hi) / 2)
        z = np.clip(m / (1 + m), 0, .5)                                 # Shin, two outcomes (approximate z)
        shin = (np.sqrt(z ** 2 + 4 * (1 - z) * qo ** 2 / (qo + qu)) - z) / (2 * (1 - z))
        y = f["over"]
        out[season] = {name: round(float(np.mean(p) - y.mean()), 4) for name, p in
                       (("multiplicative", mult), ("additive", add), ("power", pw), ("shin", shin))}
    return out


if __name__ == "__main__":
    main()
