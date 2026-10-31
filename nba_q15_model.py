#!/usr/bin/env python3
"""NBA_Q15 E7: the market-anchored logistic model (nba_q15) with the engine's ROLE1 v3 projection added, unders only.

A bet: the under, when the model's EV at the better of FanDuel and DraftKings at the consensus line is >= TAU, and the
engine projects the player for 12+ minutes (bettable under the 2026-10-16 restriction).

    python3 nba_q15_proj.py CACHE/e7_proj.pkl          # step 1, the engine's projections
    python3 nba_q15_model.py validate [--json OUT]      # walk-forward by month, TRAIN / VALIDATE
    python3 nba_q15_model.py test-a [--json OUT]        # TEST A slots 4-5, graded once (NBA_Q15_LOG.md)

--proj picks the projection file (nba_q15_proj.py --mode; e7_proj.pkl is --mode box, which leaks the final margin,
NBA_Q15_LOG.md E8). --no-vacated drops the box-score "teammates out tonight" features too.
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

import nba_q15 as Q

MIN_AT = 12.0                      # projected minutes, the books' restriction
SLOTS = {"Q15_LR8": 0.08, "Q15_LR10": 0.10}
POSTS = {"2022-23": "2023", "2023-24": "2024", "2024-25": "2025"}


def with_engine(d, X, proj):
    """The engine's projection against the line, and its minutes, as three more features."""
    key = list(zip(d["date"], d["pid"].astype(int), d["market"]))
    d["e_proj"] = [proj.get(k, (np.nan, np.nan))[0] for k in key]
    d["e_min"] = [proj.get(k, (np.nan, np.nan))[1] for k in key]
    X["e_r"] = np.log((d["e_proj"] + 0.5) / (d["line"].astype(float) + 0.5))
    X["e_r_neg"] = X["e_r"].clip(upper=0)
    X["e_min"] = d["e_min"]
    return d, X


def load(proj=Q.CACHE / "e7_proj.pkl", vacated=True):
    d, X = Q.frame(Q.load())
    if not vacated:
        X = X.drop(columns=["vac_min", "vac_n"])
    with open(proj, "rb") as f:
        return with_engine(d, X, pickle.load(f))


def under_bets(d, p, tau):
    b = Q.bets(d, p, tau, sides=("under",))
    return b[b["e_min"] >= MIN_AT] if len(b) else b


def lower_bound(u, keys, q=0.01, boot=4000, seed=7):
    """One-sided bootstrap lower bound on ROI, resampling player-games (alpha 0.05 / 5 at q = 0.01)."""
    cl = pd.Series(np.asarray(u, float)).groupby(np.asarray(keys)).agg(["sum", "size"]).to_numpy()
    idx = np.random.default_rng(seed).integers(0, len(cl), size=(boot, len(cl)))
    return round(float(np.quantile(cl[idx, 0].sum(1) / cl[idx, 1].sum(1), q)), 4)


def summarize(b):
    if not len(b):
        return {"n": 0}
    keys = b["date"] + b["pid"].astype(str)
    s = Q.summary(b["u"], b["win"], b["price"], keys)
    s["lb_bonf"] = lower_bound(b["u"], keys)
    return s


def validate(**kw):
    d, X = load(**kw)
    tv = d["split"].isin(["TRAIN", "VALIDATE"])
    p = Q.walk_forward(d, X, Q.fit_logistic)
    out = {"scores": {sp: Q.scores(d, p, d["split"] == sp) for sp in ("TRAIN", "VALIDATE")}}
    for name, tau in SLOTS.items():
        b = under_bets(d[tv], p[tv], tau)
        out[name] = {sp: summarize(g) for sp, g in b.groupby("split")}
    return out


def test_a(**kw):
    """Each postseason predicted by a model fit on the regular-season props before it. The 2023 postseason has none
    (prices start 2023-05-03), so it uses the TRAIN fit, from games after it."""
    d, X = load(**kw)
    rs = d["split"].isin(["TRAIN", "VALIDATE"]) & d["y"].notna()
    post = d["split"] == "TEST_A"
    p = pd.Series(np.nan, index=d.index)
    fits = {}
    for s in POSTS:
        m = post & (d["season"] == s)
        first = d.loc[m, "date"].min()
        tr = rs & (d["date"] < first)
        if not tr.any():
            tr = rs & (d["split"] == "TRAIN")
        fits[s] = {"first": first, "fit_n": int(tr.sum()), "fit_until": d.loc[tr, "date"].max()}
        p[m] = Q.fit_logistic(X[tr], d.loc[tr, "y"])(X[m])
    out = {"fits": fits, "scores": Q.scores(d, p, post)}
    for name, tau in SLOTS.items():
        b = under_bets(d[post], p[post], tau)
        b["ratio"] = b["e_proj"] / b["line"].astype(float)
        out[name] = {"all": summarize(b),
                     "by_post": {POSTS[s]: summarize(g) for s, g in b.groupby("season")},
                     "fanduel": summarize(fd_only(d, b)),
                     "by_market": {m: summarize(g) for m, g in b.groupby("market")},
                     "ratio_lt80": summarize(b[b["ratio"] < 0.8]), "ratio_ge80": summarize(b[b["ratio"] >= 0.8])}
    return out


def fd_only(d, b):
    """The same bets at FanDuel's under price, where FanDuel posted the consensus line."""
    g = b[(b["fd_line"] == b["line"]) & b["fd_u"].notna()].copy()
    g["price"] = g["fd_u"]
    g["u"], g["win"] = Q.grade(g, "under", g["price"].to_numpy())
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=("validate", "test-a"))
    ap.add_argument("--json")
    ap.add_argument("--proj", default=str(Q.CACHE / "e7_proj.pkl"))
    ap.add_argument("--no-vacated", action="store_true")
    a = ap.parse_args()
    kw = {"proj": Path(a.proj), "vacated": not a.no_vacated}
    out = validate(**kw) if a.what == "validate" else test_a(**kw)
    s = json.dumps(out, indent=1, default=str)
    print(s)
    if a.json:
        Path(a.json).write_text(s)


if __name__ == "__main__":
    main()
