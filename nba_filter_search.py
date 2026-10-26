#!/usr/bin/env python3
"""The filter search of NBA_FILTER_SEARCH_PREREG.md — research, search, noise benchmark, verdict.

    python nba_filter_search.py --research   # factor-by-factor ROI on TRAIN only (information)
    python nba_filter_search.py              # the pre-registered search -> VALIDATE -> HOLDOUT

Stages, exactly as registered:
  1. Conditions: each feature in its lowest or highest third (cut points from TRAIN), plus each stat.
  2. Rules: 1-3 conditions on distinct features; objective = TRAIN total units, n >= 150, >= 40 dates.
  3. NOISE BENCHMARK: outcomes shuffled among the bets of each date (prices kept), the identical search
     re-run 100 times; a real rule must beat the 95th percentile of the 100 noise-best values.
  4. The top 20 TRAIN rules that beat it are scored on VALIDATE; survivors need ROI > 0.
  5. Final set = the single best survivor or the union of the top three — whichever earns more on
     VALIDATE — scored ONCE on HOLDOUT.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FEAT = HERE / "nba_features.sqlite"
OUT = HERE / "nba_filter_search_result.json"
MIN_N, MIN_DATES, N_NOISE, TOP_VALIDATE, KEEP = 150, 40, 100, 20, 400
KEYS = {"date", "block", "gid", "team", "opp", "x_pid", "b_pid", "b_name", "stat", "actual", "won",
        "units"}
PT = ["Isolation", "Transition", "PRBallHandler", "PRRollman", "Postup", "Spotup", "Handoff", "Cut",
      "OffScreen"]
# the direction each factor was EXPECTED to help, as written in the prereg (+ = high is better)
EXPECT = {"opp_pace": +1, "opp_def_rtg": +1, "opp_reb_ag": +1, "opp_ast_ag": +1, "opp_dvp": +1,
          "opp_blk": -1, "opp_oreb_rate_ag": +1, "pw": +1, "x_fga_share": +1, "x_ast_share": +1,
          "x_reb_share": +1, "m_rim": +1, "m_paint": +1, "m_three": +1, "m_3pa": +1, "m_ft": +1,
          "m_pnr": +1, "m_spot": +1, "m_post": +1, "m_iso": +1, "m_roll": +1, "m_trans": +1,
          "m_usage_def": +1, "m_min_pace": +1, "rest": +1, "b2b": -1, "abs_net_gap": -1,
          "line_vs_avg": -1, "line_vs_l10": -1, "wowy_margin": +1, "d_min": +1, "d_fga": +1,
          "d_stat": +1}
FAMILY = [("1 opponent defense", ["opp_pace", "opp_def_rtg", "opp_reb_ag", "opp_ast_ag", "opp_dvp",
                                  "opp_blk", "opp_fg3a_rate_ag", "opp_fta_rate_ag", "opp_oreb_rate_ag"]),
          ("2 how B scores", ["b_ra", "b_paint", "b_mid", "b_c3", "b_ab3", "b_3pa_rate", "b_fta_rate",
                              "b_usage_share"] + [f"b_pt_{t}" for t in PT]),
          ("3 what X vacates", ["x_min_l10", "x_fga_share", "x_ast_share", "x_reb_share", "pw"]),
          ("4 style vs weakness", ["m_rim", "m_paint", "m_three", "m_3pa", "m_ft", "m_pnr", "m_spot",
                                   "m_post", "m_iso", "m_roll", "m_trans"]),
          ("5 usage bump vs defense", ["d_min", "d_fga", "d_stat", "m_usage_def", "m_min_pace"]),
          ("6 game context", ["home", "rest", "opp_rest", "b2b", "net_gap", "abs_net_gap", "aidx"]),
          ("7 the line", ["line_vs_avg", "line_vs_l10", "wowy_margin", "implied", "line"])]


def load():
    df = pd.read_sql("SELECT * FROM features", sqlite3.connect(f"file:{FEAT}?mode=ro", uri=True))
    for t in PT:                                      # prereg addendum 1: missing play type = 0
        df[f"b_pt_{t}"] = df[f"b_pt_{t}"].fillna(0.0)
    for t, m in (("PRBallHandler", "m_pnr"), ("Spotup", "m_spot"), ("Postup", "m_post"),
                 ("Isolation", "m_iso"), ("PRRollman", "m_roll"), ("Transition", "m_trans")):
        df[m] = df[f"b_pt_{t}"] * df[f"opp_pt_{t}"]
    feats = [c for c in df.columns if c not in KEYS]
    return df, feats


def conditions(df, feats):
    tr = df[df.block == "TRAIN"]
    names, masks, fid = [], [], []
    for k, f in enumerate(feats):
        x = pd.to_numeric(tr[f], errors="coerce").dropna()
        if x.nunique() < 3:
            if x.nunique() == 2:                       # binary: each value is a condition
                for v in sorted(x.unique()):
                    names.append(f"{f} == {v:g}")
                    masks.append((pd.to_numeric(df[f], errors="coerce") == v).to_numpy())
                    fid.append(k)
            continue
        lo, hi = x.quantile(1 / 3), x.quantile(2 / 3)
        col = pd.to_numeric(df[f], errors="coerce")
        names += [f"{f} <= {lo:.4g} (low third)", f"{f} >= {hi:.4g} (high third)"]
        masks += [(col <= lo).fillna(False).to_numpy(), (col >= hi).fillna(False).to_numpy()]
        fid += [k, k]
    for s in sorted(df.stat.unique()):
        names.append(f"stat == {s}")
        masks.append((df.stat == s).to_numpy())
        fid.append(len(feats))                         # one shared id: two stats never combine
    return names, np.array(masks, dtype=bool), np.array(fid)


def search(Mb, u, dates, fid, keep=KEEP, per_k=60):
    """Every rule of 1-3 conditions on distinct features, scored with matrix products (counts and
    unit sums for all pairs at once; triples one anchor condition at a time). Only the top `per_k`
    candidates per anchor are kept, then the merged list is walked best-first and the >= MIN_DATES
    requirement checked. Returns the top `keep` valid rules as (units, n, (i, j, k...))."""
    M = Mb.astype(np.float64)                 # double precision: unit sums exact to ~1e-12
    uf = u.astype(np.float64)
    Mu = M * uf
    m = len(M)
    same = fid[:, None] == fid[None, :]
    upper = np.triu(np.ones((m, m), dtype=bool), 1)
    cand = []
    n1, u1 = M.sum(1), M @ uf
    for i in np.nonzero(n1 >= MIN_N)[0]:
        cand.append((float(u1[i]), int(n1[i]), (int(i),)))

    def top(U, Nm, valid, k_extra=()):
        U = np.where(valid & (Nm >= MIN_N), U, -np.inf)
        flat = U.ravel()
        k = min(per_k, int(np.isfinite(flat).sum()))
        if k <= 0:
            return
        idx = np.argpartition(-flat, k - 1)[:k]
        for f in idx:
            a_, b_ = divmod(int(f), m)
            cand.append((float(flat[f]), int(Nm[a_, b_]), (*k_extra, a_, b_)))

    top(Mu @ M.T, M @ M.T, upper & ~same)
    for k in range(m):
        Mk = M * M[k]
        valid = upper & ~same & ~same[k][:, None] & ~same[k][None, :]
        valid[:k + 1, :] = False                          # j > k, so each triple is counted once
        top((Mk * uf) @ M.T, Mk @ M.T, valid, (k,))
    cand.sort(key=lambda c: -c[0])
    out = []
    for c in cand:
        mask = np.logical_and.reduce([Mb[i] for i in c[2]])
        if len(np.unique(dates[mask])) >= MIN_DATES:
            out.append(c)
            if len(out) >= keep:
                break
    return out


def selftest():
    """Plant a known edge in synthetic data: the search must find it, its matrix arithmetic must equal
    direct computation, and on pure noise nothing may beat the benchmark."""
    rng = np.random.default_rng(1)
    n, m = 6000, 40
    dates = np.repeat(np.arange(150), n // 150).astype(str)
    Mb = rng.random((m, n)) < 1 / 3
    fid = np.arange(m)
    price = np.full(n, 1.91)
    planted = Mb[3] & Mb[17]                                   # the true edge: conditions 3 AND 17
    p_win = np.where(planted, 0.70, 0.50)
    won = (rng.random(n) < p_win).astype(int)
    u = np.where(won == 1, price - 1, -1.0)
    res = search(Mb, u, dates, fid, keep=5)
    found = res[0][2] in ((3, 17), (17, 3))
    ok_math = all(abs(c[0] - u[np.logical_and.reduce([Mb[i] for i in c[2]])].sum()) < 1e-6 for c in res)
    noise = [search(Mb, shuffle_within_date(won, price, dates, rng), dates, fid, keep=1)[0][0]
             for _ in range(20)]
    beats = res[0][0] > np.percentile(noise, 95)
    won0 = (rng.random(n) < 0.5).astype(int)                    # no edge anywhere
    u0 = np.where(won0 == 1, price - 1, -1.0)
    null_best = search(Mb, u0, dates, fid, keep=1)[0][0]
    noise0 = [search(Mb, shuffle_within_date(won0, price, dates, rng), dates, fid, keep=1)[0][0]
              for _ in range(20)]
    false_alarm = null_best > np.percentile(noise0, 95)
    print(f"planted rule found first: {found} (top {res[0][2]}, {res[0][0]:+.1f}u)")
    print(f"matrix units == direct units for the top 5: {ok_math}")
    print(f"planted edge beats its noise benchmark: {beats} (best {res[0][0]:+.1f}u vs 95th pct "
          f"{np.percentile(noise, 95):+.1f}u)")
    print(f"NO-EDGE data: best rule {null_best:+.1f}u vs benchmark {np.percentile(noise0, 95):+.1f}u -> "
          f"false alarm: {false_alarm}")
    return found and ok_math and beats and not false_alarm


def shuffle_within_date(won, price, dates, rng):
    w = won.copy()
    order = np.argsort(dates, kind="stable")
    d_sorted = dates[order]
    starts = np.r_[0, np.nonzero(d_sorted[1:] != d_sorted[:-1])[0] + 1, len(d_sorted)]
    for a, b in zip(starts[:-1], starts[1:]):
        idx = order[a:b]
        w[idx] = w[rng.permutation(idx)]
    return np.where(w == 1, price - 1.0, -1.0)


def score(mask, df):
    sub = df[mask]
    if not len(sub):
        return {"n": 0, "units": 0.0, "roi": None, "dates": 0}
    return {"n": int(len(sub)), "units": float(sub.units.sum()), "roi": float(sub.units.mean() * 100),
            "dates": int(sub.date.nunique()), "hit": float(sub.won.mean() * 100)}


def ci(mask, df, reps=4000, seed=7):
    sub = df[mask]
    by = [g.units.to_numpy() for _, g in sub.groupby("date")]
    if len(by) < 10:
        return None
    rng = random.Random(seed)
    res = []
    for _ in range(reps):
        pick = [by[rng.randrange(len(by))] for _ in by]
        res.append(np.concatenate(pick).mean() * 100)
    res.sort()
    return res[int(.025 * reps)], res[int(.975 * reps)]


def research():
    df, feats = load()
    tr = df[df.block == "TRAIN"]
    base = tr.units.mean() * 100
    print(f"TRAIN only (2023-24): {len(tr):,} candidate overs, ROI {base:+.2f}% — every number below is "
          f"information, from ONE season, with ~{len(feats) * 2} cuts looked at: expect a few big ones by chance.\n")
    for fam, fs in FAMILY:
        print(f"── {fam}")
        for f in fs:
            x = pd.to_numeric(tr[f], errors="coerce")
            if x.notna().sum() < 300 or x.nunique() < 2:
                continue
            if x.nunique() <= 2:
                parts = [(f"={v:g}", tr[x == v]) for v in sorted(x.dropna().unique())]
            else:
                lo, hi = x.quantile(1 / 3), x.quantile(2 / 3)
                parts = [("low", tr[x <= lo]), ("mid", tr[(x > lo) & (x < hi)]), ("high", tr[x >= hi])]
            cells = "  ".join(f"{lab} {p.units.mean() * 100:+6.1f}% (n={len(p):,})" for lab, p in parts)
            e = EXPECT.get(f)
            hint = "" if e is None else ("   expected: high better" if e > 0 else "   expected: low better")
            print(f"   {f:<18} {cells}{hint}")
    print("\n── by stat")
    for s, g in tr.groupby("stat"):
        print(f"   {s:<9} {g.units.mean() * 100:+6.1f}% (n={len(g):,})")


def main():
    t0 = time.time()
    df, feats = load()
    names, Mall, fid = conditions(df, feats)
    trm = (df.block == "TRAIN").to_numpy()
    tr = df[trm]
    Mb, dates, won, price = Mall[:, trm], tr.date.to_numpy(), tr.won.to_numpy(), tr.price.to_numpy()
    u = tr.units.to_numpy()
    print(f"{len(names)} conditions -> searching every 1-3 condition rule on {trm.sum():,} TRAIN rows")
    real = search(Mb, u, dates, fid)
    best = real[0] if real else None
    print(f"real search: best TRAIN rule {best[0]:+.1f}u on n={best[1]} "
          f"({100 * best[0] / best[1]:+.1f}%) [{time.time() - t0:.0f}s]")
    rng = np.random.default_rng(7)
    noise = []
    for r in range(N_NOISE):
        un = shuffle_within_date(won, price, dates, rng)
        top = search(Mb, un, dates, fid, keep=1)
        noise.append(top[0][0] if top else 0.0)
        if (r + 1) % 10 == 0:
            print(f"   noise searches {r + 1}/{N_NOISE} · 95th pct so far {np.percentile(noise, 95):+.1f}u "
                  f"[{time.time() - t0:.0f}s]", flush=True)
    bar = float(np.percentile(noise, 95))
    beat = [c for c in real if c[0] > bar]
    print(f"\nNOISE BENCHMARK: best rule on shuffled outcomes — median {np.median(noise):+.1f}u, "
          f"95th percentile {bar:+.1f}u. Real rules above it: {len(beat)}")
    res = {"conditions": len(names), "real_best_units": best[0], "noise_median": float(np.median(noise)),
           "noise_p95": bar, "noise": noise, "n_beat": len(beat)}
    if not beat:
        res["verdict"] = "KILL — no rule beats the noise benchmark; no VALIDATE or HOLDOUT look"
        print(f"\n-> PRE-REGISTERED VERDICT: {res['verdict']}")
        res["top_train"] = [{"rule": [names[i] for i in c[2]], "units": c[0], "n": c[1]} for c in real[:10]]
        OUT.write_text(json.dumps(res, indent=1))
        return
    vm = (df.block == "VALIDATE").to_numpy()
    surv = []
    for c in beat[:TOP_VALIDATE]:
        mask = np.logical_and.reduce([Mall[i] for i in c[2]])
        v = score(mask & vm, df)
        print(f"   VALIDATE  {v['units']:+7.1f}u  n={v['n']:4d}  ROI {v['roi'] if v['roi'] is not None else 0:+6.1f}%"
              f"   <- TRAIN {c[0]:+.1f}u n={c[1]}  {' AND '.join(names[i] for i in c[2])}")
        if v["n"] and v["roi"] > 0:
            surv.append((v["units"], c, mask))
    if not surv:
        res["verdict"] = "KILL — no benchmark-beating rule survives VALIDATE"
        print(f"\n-> PRE-REGISTERED VERDICT: {res['verdict']}")
        OUT.write_text(json.dumps(res, indent=1))
        return
    surv.sort(key=lambda s: -s[0])
    single = surv[0][2]
    union = np.logical_or.reduce([s[2] for s in surv[:3]])
    pick = single if score(single & vm, df)["units"] >= score(union & vm, df)["units"] else union
    which = "single best survivor" if pick is single else "union of the top three"
    hm = (df.block == "HOLDOUT").to_numpy()
    h = score(pick & hm, df)
    hci = ci(pick & hm, df)
    verdict = ("KILL — HOLDOUT ROI <= 0" if not h["n"] or h["roi"] <= 0 else
               "A — HOLDOUT CI lower bound > 0" if hci and hci[0] > 0 else "B — HOLDOUT ROI > 0, CI includes 0")
    print(f"\nFINAL SET ({which}) on HOLDOUT, one look: n={h['n']} · {h['units']:+.1f}u · ROI "
          f"{h['roi'] or 0:+.2f}% · CI {hci}")
    print(f"\n-> PRE-REGISTERED VERDICT: {verdict}")
    res.update({"verdict": verdict, "final": which, "holdout": h, "holdout_ci": hci,
                "survivors": [{"rule": [names[i] for i in s[1][2]], "validate_units": s[0],
                               "train_units": s[1][0], "train_n": s[1][1]} for s in surv]})
    OUT.write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--research", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    research() if a.research else main()
