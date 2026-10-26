#!/usr/bin/env python3
"""Arm S — NBA tracking stats inside the WNBA pricing model, on real lines. Executes
NBA_TRACKING_PREREG.md.

One change to Arm T: in the beneficiary's prior game rows (his log and his with/without split),
  reb -> reb_chances    x p_reb(B)      ast -> potential_ast x p_ast(B)
with combos rebuilt; points, minutes and shot columns untouched. p(B) is B's own conversion over
games strictly BEFORE the bet's date (400-day pool), shrunk toward the league rate with K = 40
pseudo-opportunities; the league rates come from 2022-23 only, before every test date. A game with
no tracking value keeps its real value and is counted. Arm T runs in the same pass as the control
and must reproduce its registered result (n = 1,186, -41.09u) or nothing is concluded.

    python nba_tracking_realline.py --selftest
    python nba_tracking_realline.py
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import sqlite3
import statistics as st
import sys
from collections import Counter, defaultdict

import nba_pricing as P
import nba_pricing_realline as PR
import nba_tracking as TK

K = 40
POOL_DAYS = 400
ARM_T_REGISTERED = (1186, -41.09)          # n, units — NBA_PRICING_PREREG.md result
MISSING = Counter()


def load():
    """trk[(date, pid)] = (reb_chances|None, potential_ast|None); per-player cumulative history
    for prior-only conversion; league rates from 2022-23."""
    con = sqlite3.connect(f"file:{TK.DB}?mode=ro", uri=True)
    con.execute(f"ATTACH DATABASE 'file:{TK.LOGS}?mode=ro' AS g")
    rows = con.execute("""SELECT t.date, t.player_id, t.reb_chances, t.potential_ast, l.reb, l.ast, l.season
                          FROM tracking t JOIN g.logs_full l ON l.date=t.date AND l.player_id=t.player_id
                          WHERE l.min > 0 ORDER BY t.date""").fetchall()
    con.close()
    trk, hist = {}, defaultdict(list)
    lr = [0.0, 0.0, 0.0, 0.0]                          # 2022-23: reb, chances, ast, potential
    for d, pid, ch, pot, reb, ast, season in rows:
        trk[(d, pid)] = (ch, pot)
        hist[pid].append((d, reb if ch is not None else 0.0, ch or 0.0,
                          ast if pot is not None else 0.0, pot or 0.0))
        if season == "2022-23":
            if ch is not None:
                lr[0] += reb; lr[1] += ch
            if pot is not None:
                lr[2] += ast; lr[3] += pot
    league = (lr[0] / lr[1], lr[2] / lr[3])
    cum = {}
    for pid, hs in hist.items():
        dates, c = [h[0] for h in hs], [(0.0, 0.0, 0.0, 0.0)]
        for _, r, ch, a, pot in hs:
            p = c[-1]
            c.append((p[0] + r, p[1] + ch, p[2] + a, p[3] + pot))
        cum[pid] = (dates, c)
    return trk, cum, league


def make_transform(trk, cum, league):
    cache = {}

    def conv(pid, asof):
        key = (pid, asof)
        if key not in cache:
            dates, c = cum.get(pid, ([], [(0.0,) * 4]))
            lo = (dt.date.fromisoformat(asof) - dt.timedelta(days=POOL_DAYS)).isoformat()
            i, j = bisect.bisect_left(dates, lo), bisect.bisect_left(dates, asof)   # strictly before
            r, ch, a, pot = (c[j][k] - c[i][k] for k in range(4))
            cache[key] = ((r + K * league[0]) / (ch + K), (a + K * league[1]) / (pot + K))
        return cache[key]

    def transform(pid, d, row, asof):
        t = trk.get((d, pid))
        if t is None:
            MISSING["no_tracking_row"] += 1
            return row
        ch, pot = t
        p_reb, p_ast = conv(pid, asof)
        reb = ch * p_reb if ch is not None else row["reb"]
        ast = pot * p_ast if pot is not None else row["ast"]
        MISSING["reb_kept_real"] += ch is None
        MISSING["ast_kept_real"] += pot is None
        MISSING["rows_smoothed"] += 1
        return P.row(row["min"], row["pts"], reb, ast, row["fga"], row["fta"], row["fg3a"])

    return transform, conv


def calibration(rows, label):
    print(f"  {label}:")
    for lo, hi in ((.10, .20), (.20, .35), (.35, 9)):
        b = [r for r in rows if lo <= r["ev"] < hi]
        if b:
            pm = st.mean((r["ev"] + 1) / r["odds"] for r in b)
            print(f"     EV {lo:+.2f}..{hi:+.2f}: n={len(b):4d}  model {pm:.3f}  realized "
                  f"{sum(r['won'] for r in b) / len(b):.3f}  ROI {PR.units(b) / len(b) * 100:+6.2f}%")


def selftest():
    trk = {("2024-01-10", 7): (10.0, 8.0), ("2024-01-12", 7): (None, 5.0)}
    cum = {7: (["2024-01-01", "2024-01-05"], [(0, 0, 0, 0), (6, 10, 4, 8), (12, 20, 8, 16)])}
    tf, conv = make_transform(trk, cum, (0.5, 0.5))
    p_reb, p_ast = conv(7, "2024-01-10")                 # prior: 12/20 reb, 8/16 ast, K=40 toward .5
    ok = abs(p_reb - (12 + 20) / (20 + 40)) < 1e-9 and abs(p_ast - (8 + 20) / (16 + 40)) < 1e-9
    row = P.row(30, 15, 9, 3, 12, 4, 5)
    a = tf(7, "2024-01-10", row, "2024-01-10")
    ok &= abs(a["reb"] - 10 * p_reb) < 1e-9 and abs(a["ast"] - 8 * p_ast) < 1e-9
    ok &= a["pts"] == 15 and abs(a["pra"] - (15 + a["reb"] + a["ast"])) < 1e-9
    b = tf(7, "2024-01-12", row, "2024-01-12")           # rebound chances missing -> real rebounds
    ok &= b["reb"] == 9
    c = tf(7, "2024-02-01", row, "2024-02-01")           # no tracking row at all -> unchanged
    ok &= c is row
    p_early, _ = conv(7, "2024-01-03")                    # only the 01-01 game is prior
    ok &= abs(p_early - (6 + 20) / (10 + 40)) < 1e-9
    print(f"selftest: conversion prior-only + shrink, smoothing, fallbacks -> {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    trk, cum, league = load()
    print(f"tracking rows {len(trk):,} · league conversion (2022-23): rebounds {league[0]:.3f} per "
          f"chance, assists {league[1]:.3f} per potential assist")
    transform, _ = make_transform(trk, cum, league)
    sel_t, null, margin, cnt = PR.collect()
    kept_t, _ = P.select(sel_t)
    sel_s, _, _, _ = PR.collect(transform=transform)
    kept_s, _ = P.select(sel_s)
    print(f"universe {cnt} · smoothing {dict(MISSING)}\n")
    n_t, u_t = len(kept_t), round(PR.units(kept_t), 2)
    if (n_t, u_t) != ARM_T_REGISTERED:
        print(f"!! ARM T DID NOT REPRODUCE: n={n_t}, units={u_t} vs registered {ARM_T_REGISTERED}. "
              "The harness changed; nothing is concluded.")
        return 1
    print(f"=== control: Arm T reproduces its registered result (n={n_t}, {u_t:+.2f}u) ===")
    t = PR.line_of("Arm T pooled", kept_t)
    print("\n=== ARM S — rebounds/assists from opportunities [PRIMARY] ===")
    pool = PR.line_of("Arm S pooled", kept_s)
    fit = PR.line_of(f"before {PR.SPLIT}", [r for r in kept_s if r["date"] < PR.SPLIT])
    hold = PR.line_of(f"from {PR.SPLIT}", [r for r in kept_s if r["date"] >= PR.SPLIT])
    print("\n=== baselines (same candidates, same books) ===")
    nul = PR.line_of("always-over null", null)
    mar = PR.line_of("shipped margin rule", margin)
    v = PR.verdict(pool, fit, hold, nul, mar)
    if v.startswith(("A", "B")) and pool["roi"] <= t["roi"]:
        v = "KILL (does not beat Arm T)"
    print(f"\n  -> PRE-REGISTERED VERDICT: {v}\n")
    print("=== secondary: calibration (the defect this targets) — information only ===")
    calibration(kept_t, "Arm T")
    calibration(kept_s, "Arm S")
    print("\n=== secondary: per stat, Arm T vs Arm S — information only ===")
    for s_ in PR.MKT:
        a = [r for r in kept_t if r["stat"] == s_]
        b = [r for r in kept_s if r["stat"] == s_]
        fa = f"n={len(a):4d} {PR.units(a) / len(a) * 100:+6.2f}%" if a else "      -"
        fb = f"n={len(b):4d} {PR.units(b) / len(b) * 100:+6.2f}%" if b else "      -"
        print(f"  {s_:<9} T {fa}   S {fb}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if selftest() else 1) if a.selftest else sys.exit(main())
