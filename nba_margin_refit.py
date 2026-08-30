#!/usr/bin/env python3
"""NBA port · re-derive the per-stat MARGIN constants on REAL lines.

WHY. nba_wowy.py grades against `line = median(last 10 games)` — the player's own rolling median,
not a market line. That is (a) not what you can bet and (b) partly circular, since `proj` is built
from the same game logs. It reports PRA 66.8%; the real-line NBA base rate is ~48-49% over at a
~52-53% breakeven (nba_realline_base.py). The shipped MARGIN constants were fitted against that
proxy and must be re-derived.

METHOD
  * real MAIN line per (date, player, stat): the rung nearest even money (the base-rung lesson —
    value concentrates at the main line, not up the ladder), with the BEST over price across US
    books (line shopping is free once acquired).
  * grade on the actual box score, not the proxy.
  * objective is TOTAL UNITS, never hit% — raising hit% by dropping bets is the v1.6 trap.
  * chronological split: fit on the earlier half, report the later half untouched.
"""
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

import nba_wowy as N

HERE = Path(__file__).resolve().parent
ODDS = HERE / "basketball_nba_odds_hist.sqlite"
LOGS = HERE / "nba_gamelogs.sqlite"
MKT = {"pts": "player_points", "reb": "player_rebounds", "ast": "player_assists",
       "pra": "player_points_rebounds_assists", "fg3m": "player_threes"}
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm(n):
    n = unicodedata.normalize("NFKD", str(n))
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    n = re.sub(r"[^a-z ]", " ", n)
    return " ".join(p for p in n.split() if p and p not in SUFFIX)


def load_real_lines():
    """(date, norm_name, stat) -> (line, best_over_price). Main line = nearest even money."""
    o = sqlite3.connect(f"file:{ODDS}?mode=ro", uri=True, timeout=90)
    inv = {v: k for k, v in MKT.items()}
    best = {}
    for d, p, m, line, price in o.execute(
            "SELECT game_date, player, market, line, price FROM props "
            "WHERE side='over' AND price IS NOT NULL AND line IS NOT NULL"):
        stat = inv.get(m)
        if not stat:
            continue
        k = (d, norm(p), stat)
        gap = abs(float(price) - 2.0)
        cur = best.get(k)
        # nearest even money wins the rung; within a rung keep the best over price
        if cur is None or gap < cur[0] - 1e-9:
            best[k] = (gap, float(line), float(price))
        elif abs(float(line) - cur[1]) < 1e-9 and float(price) > cur[2]:
            best[k] = (cur[0], cur[1], float(price))
    return {k: (v[1], v[2]) for k, v in best.items()}


def collect():
    """Every beneficiary candidate in the production cell, with proj, REAL line, price, actual."""
    g = sqlite3.connect(f"file:{LOGS}?mode=ro", uri=True, timeout=60)
    pid2name = {pid: nm for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs")}
    lines = load_real_lines()
    print(f"real main lines loaded: {len(lines):,}")
    cfg = {"tenure": 1, "shrink": 1, "pooled": 1}
    tg, _ = N.load_team_games(cfg["pooled"])
    out = []
    nolines = 0
    for key, games in tg.items():
        first_app = {}
        for i, (date, gid, box) in enumerate(games):
            for pid in box:
                first_app.setdefault(pid, date)
            if i < 12:
                continue
            cut = (N._d(date) - __import__("datetime").timedelta(days=N.POOL_DAYS)).isoformat()
            lo = 0
            while lo < i and games[lo][0] < cut:
                lo += 1
            prior = games[lo:i]
            if len(prior) < 12:
                continue
            played_by = defaultdict(list)
            for pd, pg, pbox in prior:
                for pid, (mn, stt) in pbox.items():
                    played_by[pid].append((pd, mn, stt))
            absents = [pid for pid, apps in played_by.items()
                       if pid not in box and len(apps) >= 10
                       and sum(a[1] for a in apps[-10:]) / 10 >= N.STAR_MIN
                       and (N._d(date) - N._d(apps[-1][0])).days <= N.ACTIVE_DAYS]
            if not absents:
                continue
            X = max(absents, key=lambda p: sum(a[1] for a in played_by[p][-10:]))
            aidx = 1
            for pd, pg, pbox in reversed(prior):
                if X in pbox:
                    break
                aidx += 1
            if aidx > 2:
                continue
            x_first = first_app.get(X, "0000")
            out_g, in_g = [], []
            for pd, pg, pbox in prior:
                if pd < x_first:
                    continue
                (out_g if X not in pbox else in_g).append(pbox)
            for B, (bmn, bst) in box.items():
                if B == X:
                    continue
                apps = played_by.get(B, [])
                if len(apps) < N.MIN_PRIOR_APPS:
                    continue
                b_out = [pbox[B] for pbox in out_g if B in pbox]
                b_in = [pbox[B] for pbox in in_g if B in pbox]
                if len(b_out) < N.MIN_WOWY or len(b_in) < 3:
                    continue
                base_min = sum(a[1] for a in apps[-10:]) / min(10, len(apps))
                min_out = sum(m for m, _ in b_out)
                d_min = (min_out / len(b_out) - sum(m for m, _ in b_in) / len(b_in))
                d_min *= len(b_out) / (len(b_out) + N.K_DMIN)
                nm = norm(pid2name.get(B, ""))
                for stat in N.STATS:
                    tot_out = sum(s[stat] for _, s in b_out)
                    base_rate = (sum(a[2][stat] for a in apps[-10:])
                                 / max(1e-9, sum(a[1] for a in apps[-10:])))
                    rate = (tot_out + base_rate * N.K_MIN) / (min_out + N.K_MIN)
                    proj = rate * (base_min + d_min)
                    real = lines.get((date, nm, stat))
                    if real is None:
                        nolines += 1
                        continue
                    line, price = real
                    out.append({"date": date, "stat": stat, "proj": proj, "line": line,
                                "price": price, "actual": bst[stat],
                                "won": 1 if bst[stat] > line else 0})
    print(f"candidates with a REAL line: {len(out):,}   (no real line, dropped: {nolines:,})")
    return out


def main():
    rows = collect()
    if not rows:
        print("no rows"); return
    dates = sorted({r["date"] for r in rows})
    mid = dates[len(dates) // 2]
    print(f"chronological split at {mid}  ({len(dates)} dates)\n")
    for stat in N.STATS:
        s = [r for r in rows if r["stat"] == stat]
        if len(s) < 200:
            print(f"{stat}: thin ({len(s)})"); continue
        print(f"=== {stat}  (shipped MARGIN = {N.MARGIN[stat]}) ===")
        print(f"  {'margin':>7} {'n_fit':>7} {'hit%':>7} {'units':>9} {'ROI':>8}   "
              f"{'n_hold':>7} {'hit%':>7} {'units':>9} {'ROI':>8}")
        best = None
        for m10 in range(0, 101, 5):
            m = m10 / 10.0
            fit = [r for r in s if r["proj"] - r["line"] >= m and r["date"] < mid]
            hold = [r for r in s if r["proj"] - r["line"] >= m and r["date"] >= mid]
            if len(fit) < 40:
                continue
            def u(v): return sum((r["price"] - 1.0) if r["won"] else -1.0 for r in v)
            uf, uh = u(fit), u(hold)
            hf = sum(r["won"] for r in fit) / len(fit) * 100
            hh = sum(r["won"] for r in hold) / len(hold) * 100 if hold else 0
            if best is None or uf > best[1]:
                best = (m, uf)
            print(f"  {m:7.1f} {len(fit):7d} {hf:6.1f}% {uf:+9.2f} {uf/len(fit)*100:+7.2f}%   "
                  f"{len(hold):7d} {hh:6.1f}% {uh:+9.2f} "
                  f"{(uh/len(hold)*100 if hold else 0):+7.2f}%")
        if best:
            print(f"  -> best-units margin on the FIT half: {best[0]} ({best[1]:+.2f}u)."
                  f"  Judge it on the HOLD column, not this one.\n")


if __name__ == "__main__":
    main()
