#!/usr/bin/env python3
"""NBA_MINUTES_PREREG.md amendment 6: minutes for backups whose position-mate is out.

Fix S (position slots: a share of an absent X's minutes to his position-mates) and fix H (his minutes in past team games
X sat, this season and last) against V3, fit on 2023-24 and read on 2024-25; then gate 2, UNDER20's ping set with the
pick's minutes. Mac only (.projdata).

    python3 nba_minutes_v4.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

import nba_boost as BOOST
import nba_role as ROLE

ALPHAS = tuple(round(0.1 * i, 1) for i in range(11))
KS = (1, 2, 3, 5, 8)
HIST_N = 10
GROUPS = ("G", "F", "C")
GATE_MIN, GATE_ALL, GATE_ROI = 0.3, 0.05, 0.01
OUT = Path(__file__).resolve().parent / ".projdata" / "minutes_v4_result.json"


def project_s(season, priors, groups, team, date, active, absent, slots=None, letters=None, wt=None):
    """Fix S: {pid: minutes} from ROLE.project's v3 path (its minutes only) with a share a = slots[X's group] of each
    absent X's minutes to the active players sharing a position letter with him, by base x V3's share factor. Kept here
    so nba_role.py, and the side-by-side's fingerprints, stay as registered; slots None is V3's minutes exactly.
    wt (gid -> weight): amendment 7's fix B, the base as a weighted mean (the plain mean if every weight is 0)."""
    prior = season.before(team, date)
    if not prior or not active:
        return {}
    played = lambda b, q: q in b and b[q]["min"]
    base, share = {}, {}
    for p in active:
        last = [(g_, b) for _d, g_, b in prior if played(b, p)][-ROLE.LAST_N:]
        base[p] = sum(b[p]["min"] for _g, b in last) / len(last) if last else 0.0
        ws = [wt(g_) for g_, _b in last] if wt and last else []
        if sum(ws):
            base[p] = sum(w * b[p]["min"] for w, (_g, b) in zip(ws, last)) / sum(ws)
        for x in absent:
            share[(p, x)] = sum(1 for _g, b in last if played(b, x)) / len(last) if last else 1.0
    x_min = {x: ROLE.ewma([b[x]["min"] for _d, _g, b in prior if played(b, x)]) or 0.0 for x in absent}
    bump = dict.fromkeys(active, 0.0)
    for x, mx in x_min.items():
        w = {p: base[p] * (ROLE.SAME_W if groups.get(p) and groups.get(p) == groups.get(x) else 1.0) for p in active}
        tw = sum(w.values())
        same = {p: base[p] for p in active if letters(p) & letters(x)} if slots else {}
        ts = sum(same.values())
        a = slots.get(groups.get(x), 0.0) if ts else 0.0
        for p in active:
            if a:
                bump[p] += mx * ((1 - a) * (w[p] / tw if tw else 0.0) + a * same.get(p, 0.0) / ts) * share[(p, x)]
            else:
                bump[p] += (mx * w[p] / tw if tw else 0.0) * share[(p, x)]
    rot = set()
    for q in active:
        m_ = [b[q]["min"] for _d, _g, b in prior if played(b, q)]
        if len(m_) >= ROLE.X_GAMES and sum(m_) / len(m_) >= ROLE.X_MIN:
            rot.add(q)
    match = [b for _d, _g, b in prior if not any(played(b, x) for x in absent) and all(played(b, q) for q in rot)]
    mins = {}
    for p in active:
        mins[p] = min(ROLE.CAP, max(0.0, base[p] + bump[p]))
        g_ = [b[p]["min"] for b in match if played(b, p)]
        if g_:
            w_ = len(g_) / (len(g_) + ROLE.K_WOWY)
            mins[p] = min(ROLE.CAP, max(0.0, (1 - w_) * mins[p] + w_ * sum(g_) / len(g_)))
    tot = sum(mins.values())
    return {p: m * ROLE.ROSTER_MIN / tot for p, m in mins.items()} if tot > 0 else mins


def hist(bd, p, team, date, absent):
    """Fix H: (n, mean minutes) over his last HIST_N team games before the date (this season and last) in which every
    absent X was on the team and sat, and he played."""
    ms = [b[p]["min"] for d, _g, _s, b in bd.before(team, date)
          if p in b and b[p]["min"] and all(not (x in b and b[x]["min"]) and bd.on_team_at(x, team, d, date) for x in absent)]
    ms = ms[-HIST_N:]
    return (len(ms), sum(ms) / len(ms)) if ms else (0, 0.0)


def with_hist(m, h, k):
    """Fix H's blend: (1 - w) x the model's minutes + w x his mean without X, w = n / (n + k)."""
    n, mean = h
    w = n / (n + k) if n else 0.0
    return (1 - w) * m + w * mean


def nights(season):
    """One record per team-game: what re-projecting needs, and who played (minutes, target night)."""
    bd, role, s = season.bd, season.role, season.s
    out = []
    for team, games in sorted(bd.games.items()):
        for d, _gid, gs, box in games:
            if gs != s:
                continue
            played = {p for p, x in box.items() if x["min"]}
            starters = bd.usual_five(team, d) or bd.starters(team, d)
            out_all = (bd.on_team_tonight(team, d) - played) & (bd.roster(team, d) | starters)
            absent = set(role.absences(team, d, set(out_all)))
            active = role.roster(team, d) - set(out_all)
            v3 = ROLE.project(role, season.priors, season.groups, team, d, active, absent, mode="v3")
            ps = [p for p in sorted(played) if p in v3]
            if not ps:
                continue
            out.append({"team": team, "date": d, "absent": absent, "active": active, "v3": {p: v3[p]["min"] for p in ps},
                        "act": {p: box[p]["min"] for p in ps}, "starter": {p: p in starters for p in ps},
                        "target": {p: p not in starters and any(bd.letters(x) & bd.letters(p) for x in absent) for p in ps},
                        "hist": {p: hist(bd, p, team, d, absent) if absent else (0, 0.0) for p in ps},
                        "xg": tuple(sorted({season.groups.get(x) or "" for x in absent}))})
    return out


class Slots:
    """Fix S's minutes per night for a given {group: a}, cached by the a's of the groups absent that night."""

    def __init__(self, season, ns):
        self.season, self.ns, self.cache = season, ns, {}

    def minutes(self, i, alphas):
        n = self.ns[i]
        if not n["absent"]:
            return n["v3"]
        key = (i, tuple(alphas.get(g, 0.0) for g in n["xg"]))
        if key not in self.cache:
            s = self.season
            pr = project_s(s.role, s.priors, s.groups, n["team"], n["date"], n["active"], n["absent"], slots=alphas,
                           letters=s.bd.letters)
            self.cache[key] = {p: pr[p] for p in n["v3"]}
        return self.cache[key]


def mae(ns, pick, sel=lambda n, p: True):
    err = [abs(pick(i, p) - n["act"][p]) for i, n in enumerate(ns) for p in n["act"] if sel(n, p)]
    return (float(np.mean(err)) if err else float("nan")), len(err)


def fit_slots(sl):
    """Coordinate descent (two passes over G, F, C) on the MAE over every player-game on nights with an absent X."""
    alphas = {g: 0.0 for g in GROUPS}
    absent_night = lambda n, p: bool(n["absent"])
    for _ in range(2):
        for g in GROUPS:
            best = None
            for a in ALPHAS:
                trial = {**alphas, g: a}
                e = mae(sl.ns, lambda i, p: sl.minutes(i, trial)[p], absent_night)[0]
                if best is None or e < best[0] - 1e-12:
                    best = (e, a)
            alphas[g] = best[1]
    return alphas


def fit_k(ns, base):
    absent_night = lambda n, p: bool(n["absent"])
    return min(KS, key=lambda k: mae(ns, lambda i, p: with_hist(base(i, p), ns[i]["hist"][p], k), absent_night)[0])


def under_set(rows, lines, markets, ns, f):
    """(n, ROI) of UNDER20's ping set (30-50% below, under -150 or better, not threes, best FD/DK at tip) with the
    projection = f(night index, pid) minutes x the backtest row's rates."""
    idx = {(n["date"], n["team"]): i for i, n in enumerate(ns)}
    us = []
    for r in rows:
        i = idx.get((r["date"], r["team"]))
        if i is None or r["pid"] not in ns[i]["act"]:
            continue
        m = f(i, r["pid"])
        for mk in markets:
            ln = lines.get((r["date"], r["pid"], mk))
            if not ln or mk == "threes":
                continue
            line, _o, under, _q = ln
            act = BOOST.stat_of(r["box"], mk)
            below = 1 - m * sum(r["rt"][x] for x in BOOST.PARTS[mk]) / line
            if act != line and under >= 1 / 0.6 - 1e-9 and 0.30 <= below < 0.50:
                us.append(under - 1 if act < line else -1.0)
    return len(us), (float(np.mean(us)) if us else float("nan"))


def main():
    sys.path.insert(0, ".")
    g = {}
    exec(open("nba_tests4_checks.py").read().split("NAMES = [")[0], g)   # seasons, rows (V3 x rates), tip lines
    seasons, rows, lines, T = g["seasons"], g["rows"], g["lines"], g["T"]
    ns = {s: nights(seasons[s]) for s in seasons}
    sl = {s: Slots(seasons[s], ns[s]) for s in seasons}
    # sanity: the nights' V3 equals the backtest rows'
    v3_rows = {(r["date"], r["team"], r["pid"]): r["min"] for s in rows for r in rows[s]}
    diff = max(abs(v3_rows[(n["date"], n["team"], p)] - m) for s in ns for n in ns[s] for p, m in n["v3"].items()
               if (n["date"], n["team"], p) in v3_rows)
    assert diff < 1e-9, f"V3 differs from the backtest rows by {diff}"

    alphas = fit_slots(sl["2023-24"])
    k_h = fit_k(ns["2023-24"], lambda i, p: ns["2023-24"][i]["v3"][p])
    s23 = sl["2023-24"]
    k_sh = fit_k(ns["2023-24"], lambda i, p: s23.minutes(i, alphas)[p])
    print(f"fit on 2023-24: S alphas {alphas}; H K {k_h}; S+H K {k_sh}")

    def picks(s):
        n_, s_ = ns[s], sl[s]
        return {"V3": lambda i, p: n_[i]["v3"][p],
                "S": lambda i, p: s_.minutes(i, alphas)[p],
                "H": lambda i, p: with_hist(n_[i]["v3"][p], n_[i]["hist"][p], k_h),
                "S+H": lambda i, p: with_hist(s_.minutes(i, alphas)[p], n_[i]["hist"][p], k_sh)}

    cuts = {"all": lambda n, p: True, "absence nights": lambda n, p: bool(n["absent"]),
            "target (Capela-type)": lambda n, p: n["target"][p], "starters": lambda n, p: n["starter"][p]}
    res = {"alphas": alphas, "k_h": k_h, "k_sh": k_sh, "mae": {}}
    for s in ("2023-24", "2024-25"):
        print(f"\n{s} minutes MAE")
        res["mae"][s] = {}
        for name, f in picks(s).items():
            row = {c: mae(ns[s], f, sel) for c, sel in cuts.items()}
            res["mae"][s][name] = row
            print(f"  {name:4s} " + "  ".join(f"{c} {v[0]:.3f} (n {v[1]})" for c, v in row.items()))
    m25 = res["mae"]["2024-25"]
    pick = min(("S", "H", "S+H"), key=lambda k: m25[k]["target (Capela-type)"][0])
    gain = m25["V3"]["target (Capela-type)"][0] - m25[pick]["target (Capela-type)"][0]
    worse = m25[pick]["all"][0] - m25["V3"]["all"][0]
    gate1 = gain >= GATE_MIN and worse <= GATE_ALL
    print(f"\npick {pick}: 2024-25 target MAE {gain:+.3f} better than V3 (need >= {GATE_MIN}); overall {worse:+.3f} "
          f"(need <= {GATE_ALL}) -> gate 1 {'PASS' if gate1 else 'FAIL'}")

    # gate 2: UNDER20's ping set with each candidate's minutes x the same rates
    unders = {}
    for s in ("2023-24", "2024-25"):
        unders[s] = {name: under_set(rows[s], lines, T.MARKETS, ns[s], f) for name, f in picks(s).items()}
        print(f"\n{s} UNDER20 ping set (30-50% below, -150 or better, not threes): " +
              "  ".join(f"{k} n {v[0]} ROI {v[1]:+.3f}" for k, v in unders[s].items()))
    gate2 = unders["2024-25"][pick][1] >= unders["2024-25"]["V3"][1] - GATE_ROI
    print(f"gate 2 ({pick}): 2024-25 ROI {unders['2024-25'][pick][1]:+.3f} vs V3 {unders['2024-25']['V3'][1]:+.3f} - "
          f"{GATE_ROI:.2f} -> {'PASS' if gate2 else 'FAIL'}")
    res.update(pick=pick, gate1=gate1, gate2=gate2, unders=unders, diag={})

    # after the result (information): backups with a 25+ mpg player of his exact group out, V3's bias against all-to-position
    for s in ("2023-24", "2024-25"):
        se, cut = seasons[s], {}
        for i, n in enumerate(ns[s]):
            big = [x for x in n["absent"] if (pg := se.bd.per_game(x, n["team"], n["date"])) and pg["min"] >= 25]
            for p in n["act"]:
                if not n["starter"][p] and any(se.groups.get(x) and se.groups.get(x) == se.groups.get(p) for x in big):
                    m1 = sl[s].minutes(i, {g_: 1.0 for g_ in GROUPS})[p]
                    cut.setdefault(se.groups.get(p), []).append((n["act"][p] - n["v3"][p], n["act"][p] - m1))
        print(f"\n{s} backups, a 25+ mpg player of his group out (actual - projected):")
        for grp, v in sorted(cut.items()):
            a_ = np.array(v)
            res["diag"][f"{s} {grp}"] = {"n": len(a_), "v3_bias": float(a_[:, 0].mean()), "v3_mae": float(np.abs(a_[:, 0]).mean()),
                                         "all_bias": float(a_[:, 1].mean()), "all_mae": float(np.abs(a_[:, 1]).mean()),
                                         "v3_low_8": float((a_[:, 0] >= 8).mean())}
            print(f"  {grp}: n {len(a_)} | V3 bias {a_[:, 0].mean():+.2f} MAE {np.abs(a_[:, 0]).mean():.2f} | all to position bias "
                  f"{a_[:, 1].mean():+.2f} MAE {np.abs(a_[:, 1]).mean():.2f} | V3 8+ low {(a_[:, 0] >= 8).mean():.0%}")
    OUT.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
