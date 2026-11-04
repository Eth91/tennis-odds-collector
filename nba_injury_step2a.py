#!/usr/bin/env python3
"""NBA_INJURY_REACTION_PREREG.md amendment 1 (Step 2a): what one line point is worth, then the full CLV of candidates C
(DraftKings stale after FanDuel moved its line) and B (FanDuel teammate overs still stale). Read-only, Mac only.

    python3 nba_injury_step2a.py --stores .projdata/vm_backup_20261103 --stamp 20261103
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import optimize, special

import nba_injury_reaction as R

MARKETS = ("points", "rebounds", "assists", "threes", "pra", "pts_reb", "pts_ast", "reb_ast")
PARTS = {"points": ("pts",), "rebounds": ("reb",), "assists": ("ast",), "threes": ("fg3m",), "pra": ("pts", "reb", "ast"),
         "pts_reb": ("pts", "reb"), "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast")}
FIT, CHECK = "2023-24", "2024-25"
GATE = 0.015                      # predicted vs realized step at d = ±1, per market
GATE_D, INFO_D = (-1, 1), (-2, 2)
BIG = ("points", "pra", "pts_reb", "pts_ast")
B_WITHIN = 15.0
SURVIVE_OVER_NULL = 0.03
BOOT, SEED = 4000, 7
GRID = np.exp(np.linspace(math.log(0.02), math.log(150.0), 1200))
LOG_GRID = np.log(GRID)


# ---- the conversion ----------------------------------------------------------------------------------------------
def k_of(mu, a, b):
    return np.exp(a + b * np.log(mu))


def nb_logpmf(y, mu, k):
    q = k / (k + mu)
    return special.gammaln(y + k) - special.gammaln(k) - special.gammaln(y + 1) + k * np.log(q) + y * np.log1p(-q)


def over_prob(line, mu, k):
    """P(over the line) for NB(mu, k); a whole-number line excludes the push."""
    mu, k = np.asarray(mu, float), np.asarray(k, float)
    q = k / (k + mu)
    if line < 0:
        return np.ones_like(mu)
    if line % 1:                       # P(X > n) = I_{1-q}(n + 1, k); special.nbdtrc would truncate a real k
        return special.betainc(math.floor(line) + 1, k, 1 - q)
    return special.betainc(line + 1, k, 1 - q) / (1 - np.exp(nb_logpmf(line, mu, k)))


class Conv:
    """One market's conversion: the mean that prices (line, no-vig over), and P(over) at any other line."""

    def __init__(self, a, b):
        self.a, self.b = float(a), float(b)
        self.k = k_of(GRID, a, b)
        self._rows = {}

    def row(self, line):
        if line not in self._rows:
            self._rows[line] = np.maximum.accumulate(over_prob(line, GRID, self.k))
        return self._rows[line]

    def mu(self, line, p):
        """The mean whose P(over line) is p, or None outside the grid."""
        r = self.row(line)
        if not (r[0] < p < r[-1]):
            return None
        return float(np.exp(np.interp(p, r, LOG_GRID)))

    def p_at(self, line, p, other):
        """P(over `other`) given P(over `line`) = p."""
        if other == line:
            return p
        m = self.mu(line, p)
        if m is None:
            return None
        return float(over_prob(other, np.array([m]), k_of(np.array([m]), self.a, self.b))[0])


def outcome(row, market):
    return sum(row[s] for s in PARTS[market])


def hist_props(market, season, hist, box):
    """(lines, no-vig overs, outcomes) for FanDuel and DraftKings main lines with a box score."""
    L, P, Y = [], [], []
    for h in hist:
        if h["market"] != market or h["book"] not in ("fd", "dk") or R_season(h["date"]) != season:
            continue
        r = box.get((h["gid"], h["pid"]))
        if r is None:
            continue
        L.append(h["line"])
        P.append(R.nv(h["over"], h["under"]))
        Y.append(outcome(r, market))
    return np.array(L), np.array(P), np.array(Y, float)


def R_season(date):
    y, m = int(date[:4]), int(date[5:7])
    y = y if m >= 8 else y - 1
    return f"{y}-{str(y + 1)[2:]}"


def mus_for(conv, L, P):
    mu = np.full(len(L), np.nan)
    for line in np.unique(L):
        idx = np.where(L == line)[0]
        r = conv.row(line)
        ok = (P[idx] > r[0]) & (P[idx] < r[-1])
        mu[idx[ok]] = np.exp(np.interp(P[idx[ok]], r, LOG_GRID))
    return mu


def fit(L, P, Y):
    """Maximum-likelihood (a, b) of the outcomes, the mean solved from each prop's line and no-vig over."""
    def nll(x):
        c = Conv(*x)
        mu = mus_for(c, L, P)
        ok = ~np.isnan(mu)
        if not ok.any():
            return 1e9
        return -float(np.sum(nb_logpmf(Y[ok], mu[ok], k_of(mu[ok], *x)))) / ok.sum() + 10.0 * (1 - ok.mean())
    best = min((optimize.minimize(nll, x0, method="L-BFGS-B", bounds=((-3.0, 9.0), (-2.0, 2.0)))
                for x0 in ((math.log(10), 0.0), (math.log(3), 0.5))), key=lambda r: r.fun)
    return tuple(float(v) for v in best.x), float(best.fun)


def steps(conv, L, P, Y, ds):
    """Per offset d: (predicted step, realized step, n): mean P(X > L + d) − p vs share(X > L + d) − share(X > L)."""
    out = {}
    mu = mus_for(conv, L, P)
    ok = ~np.isnan(mu)
    L, P, Y, mu = L[ok], P[ok], Y[ok], mu[ok]
    k = k_of(mu, conv.a, conv.b)
    base = float(np.mean(Y > L))
    for d in ds:
        pred = np.empty(len(L))
        for line in np.unique(L):
            idx = np.where(L == line)[0]
            pred[idx] = over_prob(line + d, mu[idx], k[idx])
        out[d] = (float(np.mean(pred - P)), float(np.mean(Y > L + d)) - base, int(len(L)))
    out[0] = (float(np.mean(P)), base, int(len(L)))
    return out


def alt_check(boards, convs):
    """INFORMATION: where the 2026-27 log has a second two-sided rung, the conversion vs the book's own no-vig there."""
    acc = defaultdict(list)
    for (book, gid, pid, stat), seq in boards.states.items():
        if stat not in convs:
            continue
        for _t, st in seq:
            if not st or len(st[4]) < 2:
                continue
            for ln, o, u in st[4]:
                if ln == st[0]:
                    continue
                c = convs[stat].p_at(st[0], st[1], ln)
                if c is not None:
                    acc[(stat, "above" if ln > st[0] else "below")].append(c - R.nv(o, u))
    return {f"{m} {s}": {"n": len(v), "mean_diff": float(np.mean(v)), "mean_abs_diff": float(np.mean(np.abs(v)))}
            for (m, s), v in sorted(acc.items())}


# ---- CLV and the candidates --------------------------------------------------------------------------------------
def full_clv(conv, close, line, side, odds):
    """P_conv(side at the bet line | the close main line and its no-vig over) × odds − 1; None if not computable."""
    if close is None or conv is None:
        return None
    p = conv.p_at(close[0], close[1], line)
    if p is None:
        return None
    return (p if side == "over" else 1 - p) * odds - 1


def candidates_c(us, boards, price_moves=False):
    """C: FanDuel's first check after the report with a two-sided main line off its baseline line (tF); DraftKings'
    first check after tF stale against its baseline -> DraftKings at that check, on FanDuel's side. With price_moves
    (information only) tF is FanDuel's first moved check and a same-line move picks the side by the no-vig."""
    by = {(id(u["ev"]), u["pid"], u["stat"], u["book"]): u for u in us}
    out = []
    for fu in us:
        if fu["book"] != "fd":
            continue
        du = by.get((id(fu["ev"]), fu["pid"], fu["stat"], "dk"))
        if du is None:
            continue
        gid, base = fu["ev"]["gid"], fu["base"]
        tf = side = None
        for t, c in fu["path"]:
            st = boards.state("fd", gid, fu["pid"], fu["stat"], t)
            if st is None:
                continue
            if st[0] != base[0]:
                tf, side, kind = t, ("over" if st[0] > base[0] else "under"), "line"
                break
            if price_moves and c == "moved":
                tf, side, kind = t, ("over" if st[1] > base[1] else "under"), "price"
                break
        if tf is None:
            continue
        nxt = [(t, c) for t, c in du["path"] if t > tf]
        if not nxt or nxt[0][1] != "stale":
            continue
        s = nxt[0][0]
        gs = boards.state("dk", gid, du["pid"], du["stat"], s)
        fst = boards.state("fd", gid, fu["pid"], fu["stat"], tf)
        out.append({"cand": "C" if not price_moves else "C+price", "kind": kind, "u": du, "gid": gid, "at": s, "tf": tf,
                    "book": "dk", "stat": du["stat"], "pid": du["pid"], "player": du["player"], "side": side,
                    "line": gs[0], "odds": gs[2] if side == "over" else gs[3], "fd_move": abs(fst[0] - base[0]),
                    "close": du["close"], "close_t": du["close_t"]})
    return out


def candidates_b(us, boards):
    """B: a points/PRA/P+R/P+A teammate prop stale at FanDuel's first check after the report (within 15 min) -> the
    FanDuel over at that check."""
    out = []
    for u in us:
        if u["book"] != "fd" or u["stat"] not in BIG or not u["path"]:
            continue
        t, c = u["path"][0]
        if c != "stale" or R.mins(u["ev"]["pub"], t) > B_WITHIN:
            continue
        st = boards.state("fd", u["ev"]["gid"], u["pid"], u["stat"], t)
        out.append({"cand": "B", "u": u, "gid": u["ev"]["gid"], "at": t, "book": "fd", "stat": u["stat"], "pid": u["pid"],
                    "player": u["player"], "side": "over", "line": st[0], "odds": st[2], "close": u["close"],
                    "close_t": u["close_t"]})
    return out


def null_b(ctl, boards):
    out = []
    for u in ctl:
        if u["book"] != "fd" or u["stat"] not in BIG or not u["path"]:
            continue
        t, c = u["path"][0]
        if c != "stale" or R.mins(u["pub"], t) > B_WITHIN:
            continue
        st = boards.state("fd", u["gid"], u["pid"], u["stat"], t)
        out.append({"gid": u["gid"], "stat": u["stat"], "close": u["close"], "close_t": u["close_t"],
                    "legs": [("over", st[0], st[2])]})
    return out


def null_c(ctl, boards, flags):
    """Control DraftKings props stale at each check time where C flagged (for that report): over and under, averaged."""
    times = defaultdict(set)
    for f in flags:
        times[(f["u"]["ev"]["mark"], f["u"]["ev"]["date"])].add(f["at"])
    out = []
    for u in ctl:
        if u["book"] != "dk":
            continue
        ats = times.get((u.get("mark"), u.get("date")), set())
        for t, c in u["path"]:
            if t in ats and c == "stale":
                st = boards.state("dk", u["gid"], u["pid"], u["stat"], t)
                out.append({"gid": u["gid"], "stat": u["stat"], "close": u["close"], "close_t": u["close_t"],
                            "legs": [("over", st[0], st[2]), ("under", st[0], st[3])]})
    return out


def score(rows, convs, usable):
    """Attach full CLV; count exclusions."""
    drops = defaultdict(int)
    kept = []
    for r in rows:
        if not r["close_t"]:
            drops["no close"] += 1
            continue
        if r["close"] is None:
            drops["pulled at the close"] += 1
            continue
        if r["stat"] not in usable:
            drops["market failed the gate"] += 1
            continue
        legs = r.get("legs") or [(r["side"], r["line"], r["odds"])]
        vals = [full_clv(convs[r["stat"]], r["close"], ln, sd, od) for sd, ln, od in legs]
        if any(v is None for v in vals):
            drops["outside the conversion grid"] += 1
            continue
        r["clv"] = sum(vals) / len(vals)
        kept.append(r)
    return kept, dict(drops)


def boot(rows, n=BOOT, seed=SEED):
    """(mean, low, high, games) with games resampled."""
    if not rows:
        return None
    g = defaultdict(list)
    for r in rows:
        g[r["gid"]].append(r["clv"])
    ks = sorted(g)
    rnd = random.Random(seed)
    ms = []
    for _ in range(n):
        s = [x for k in (rnd.choice(ks) for _ in ks) for x in g[k]]
        ms.append(sum(s) / len(s))
    ms.sort()
    return {"n": len(rows), "games": len(ks), "mean": sum(r["clv"] for r in rows) / len(rows),
            "low": ms[int(0.025 * n)], "high": ms[int(0.975 * n) - 1]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stores", required=True)
    ap.add_argument("--stamp", required=True)
    ap.add_argument("--out", default="audit/inj_step2a")
    a = ap.parse_args()
    import nba_proj_eval as PE
    obj = PE.load()
    box = {(r["gid"], r["pid"]): r for r in obj["rows"]}
    res = {"stamp": a.stamp, "fit_season": FIT, "check_season": CHECK, "conversion": {}, "gate": {}}
    convs, usable = {}, set()
    for m in MARKETS:
        L, P, Y = hist_props(m, FIT, obj["hist"], box)
        (ca, cb), nll = fit(L, P, Y)
        convs[m] = Conv(ca, cb)
        Lc, Pc, Yc = hist_props(m, CHECK, obj["hist"], box)
        st = steps(convs[m], Lc, Pc, Yc, GATE_D + INFO_D)
        ok = all(abs(st[d][0] - st[d][1]) <= GATE for d in GATE_D)
        if ok:
            usable.add(m)
        res["conversion"][m] = {"a": ca, "b": cb, "fit_n": int(len(L)), "nll_per_prop": nll,
                                "k_at": {str(x): float(k_of(np.array([x]), ca, cb)[0]) for x in (1, 3, 5, 10, 20, 35)}}
        res["gate"][m] = {"pass": ok, "check_n": st[0][2], "no_vig_mean": st[0][0], "realized_over": st[0][1],
                          **{f"d{d:+d}": {"predicted": st[d][0], "realized": st[d][1], "gap": st[d][0] - st[d][1]}
                             for d in GATE_D + INFO_D}}
        print(m, "a=%.3f b=%.3f" % (ca, cb), "gate", "PASS" if ok else "FAIL",
              {d: (round(100 * st[d][0], 2), round(100 * st[d][1], 2)) for d in GATE_D + INFO_D}, flush=True)

    d = Path(a.stores)
    boards = R.Boards(d / f"nba_lines.{a.stamp}.sqlite")
    res["alt_rungs"] = alt_check(boards, convs)
    events, fresh, fresh_teams, team_of = R.load_events(d / f"nba_news.{a.stamp}.sqlite", d / f"nba_matchup.{a.stamp}.sqlite", boards)
    us, _ = R.units(events, boards, team_of)
    ctl = R.controls(events, boards, fresh_teams, team_of)
    fc, fb = candidates_c(us, boards), candidates_b(us, boards)
    nc_rows, nb_rows = null_c(ctl, boards, fc), null_b(ctl, boards)
    sc, dc = score(fc, convs, usable)
    sb, db = score(fb, convs, usable)
    snc, dnc = score(nc_rows, convs, usable)
    snb, dnb = score(nb_rows, convs, usable)
    out = {}
    for name, flags, kept, drops, nkept, ndrops in (("C", fc, sc, dc, snc, dnc), ("B", fb, sb, db, snb, dnb)):
        bs, bn = boot(kept), boot(nkept)
        failed_share = drops.get("market failed the gate", 0) / len(flags) if flags else 0
        evaluable = failed_share <= 0.5 and bs is not None
        survive = bool(evaluable and bn is not None and bs["mean"] > 0 and bs["mean"] >= bn["mean"] + SURVIVE_OVER_NULL)
        out[name] = {"flags": len(flags), "drops": drops, "clv": bs, "null": bn, "null_drops": ndrops,
                     "evaluable": evaluable, "survives": survive,
                     "dates": len({f["u"]["ev"]["date"] for f in kept})}
    info = {}
    info["C by FanDuel line move 1"] = boot([r for r in sc if r["fd_move"] < 2])
    info["C by FanDuel line move 2+"] = boot([r for r in sc if r["fd_move"] >= 2])
    fcp = [f for f in candidates_c(us, boards, price_moves=True) if f["kind"] == "price"]
    scp, dcp = score(fcp, convs, usable)
    info["C+price (price-only FanDuel moves)"] = boot(scp)
    info["B no news before the report"] = boot([r for r in sb if not r["u"]["ev"]["news_first"]])
    info["B news before the report"] = boot([r for r in sb if r["u"]["ev"]["news_first"]])
    out["information"] = info
    res["candidates"] = out
    o = Path(a.out)
    o.mkdir(parents=True, exist_ok=True)
    with open(o / f"flags.{a.stamp}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cand", "report", "gid", "team", "player", "stat", "book", "flag_at", "fd_move_at", "fd_move", "side",
                    "line", "odds", "close_t", "close_line", "close_p", "full_clv"])
        for f in fc + fb + fcp:
            ev = f["u"]["ev"]
            w.writerow([f["cand"], ev["mark"], f["gid"], ev["team"], f["player"], f["stat"], f["book"], f["at"].isoformat(),
                        f["tf"].isoformat() if f.get("tf") else "", f.get("fd_move", ""), f["side"], f["line"], f["odds"],
                        f["close_t"].isoformat() if f["close_t"] else "", f["close"][0] if f["close"] else "",
                        round(f["close"][1], 4) if f["close"] else "", round(f["clv"], 4) if "clv" in f else ""])
    (o / f"result.{a.stamp}.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res[k] for k in ("gate", "candidates")}, indent=1, default=str))


if __name__ == "__main__":
    main()
