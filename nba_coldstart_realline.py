#!/usr/bin/env python3
"""NBA cold-start tier, graded on REAL lines. Executes NBA_COLDSTART_PREREG.md exactly.

Nothing here is fitted: the rule's constants live in nba_coldstart.py and predate real
lines. The verdict is printed mechanically from the pre-registered decision lines on the
two primary cells (PTS >= 5, PRA >= 5). Everything else is printed for information only.

    python nba_coldstart_realline.py
"""
import datetime as dt
import random
from collections import defaultdict

import nba_coldstart as C
import nba_margin_refit as R
import nba_wowy as N

SPLIT = "2024-10-29"          # pre-registered replication split (nba_margin_refit's date)
PRIMARY = (("pts", 5.0), ("pra", 5.0))
SECONDARY = (("reb", 2.0),)
MIN_CELL_N = 100
BOOT_N, SEED = 4000, 7


def collect():
    tg, names = N.load_team_games(True)
    lines = R.load_real_lines()
    print(f"real main lines loaded: {len(lines):,}")
    out, n_cand, n_noline = [], 0, 0
    for team, games in tg.items():
        first_app = {}
        for i, (date, gid, box) in enumerate(games):
            for pid in box:
                first_app.setdefault(pid, date)
            if i < 12:
                continue
            today = N._d(date)
            cut = (today - dt.timedelta(days=N.POOL_DAYS)).isoformat()
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

            def active(pid):
                apps = played_by[pid]
                return (len(apps) >= N.MIN_PRIOR_APPS
                        and (today - N._d(apps[-1][0])).days <= N.ACTIVE_DAYS)

            def base_min(pid):
                last = played_by[pid][-10:]
                return sum(a[1] for a in last) / len(last)

            absents = [p for p in played_by if p not in box and len(played_by[p]) >= 10
                       and active(p) and base_min(p) >= N.STAR_MIN]
            if not absents:
                continue
            X = max(absents, key=base_min)
            aidx = 1                                   # absence game index (1 = first miss)
            for pd, pg, pbox in reversed(prior):
                if X in pbox:
                    break
                aidx += 1
            if aidx > 2:
                continue
            # rotation from PRIOR games only (prereg) — tonight's box does not build it
            bm = {p: base_min(p) for p in played_by if active(p)}
            proj_min = C.redistribute(bm, X, base_min(X))
            if not proj_min:
                continue
            x_first = first_app.get(X, "0000")
            x_out_games = [pbox for pd, pg, pbox in prior if pd >= x_first and X not in pbox]
            tseason = C.season_of(date)
            for B, pmin in proj_min.items():
                if B not in box:                       # props void on a DNP
                    continue
                if sum(1 for pbox in x_out_games if B in pbox) >= C.MIN_WOWY:
                    continue                           # has a WOWY prior -> not cold-start
                rate = C.per_min_rate(played_by[B], C.season_of, tseason)
                if not rate:
                    continue
                nm = R.norm(names.get(B, ""))
                actual = box[B][1]
                for stat in ("pts", "reb", "pra"):
                    n_cand += 1
                    real = lines.get((date, nm, stat))
                    if real is None:
                        n_noline += 1
                        continue
                    line, price = real
                    out.append({"date": date, "stat": stat, "proj": rate[stat] * pmin,
                                "line": line, "price": price, "actual": actual[stat],
                                "won": 1 if actual[stat] > line else 0,
                                "aidx": aidx, "b": names.get(B), "x": names.get(X)})
    print(f"cold-start candidate stat-rows: {n_cand:,}   with a REAL line: {len(out):,}   "
          f"(no line, dropped: {n_noline:,})")
    return out


def units(v):
    return sum((r["price"] - 1.0) if r["won"] else -1.0 for r in v)


def boot_ci(sel):
    byd = defaultdict(list)
    for r in sel:
        byd[r["date"]].append(r)
    ds = list(byd)
    if len(ds) < 10:
        return None
    rnd = random.Random(SEED)
    res = []
    for _ in range(BOOT_N):
        pick = [r for _ in ds for r in byd[rnd.choice(ds)]]
        res.append(units(pick) / len(pick) * 100)
    res.sort()
    return res[int(.025 * BOOT_N)], res[int(.975 * BOOT_N)], len(ds)


def line_of(label, sel):
    if not sel:
        print(f"  {label:<26} (none)")
        return None
    roi = units(sel) / len(sel) * 100
    hit = sum(r["won"] for r in sel) / len(sel) * 100
    ci = boot_ci(sel)
    cis = f"[{ci[0]:+6.2f}%, {ci[1]:+6.2f}%]" if ci else "n/a"
    print(f"  {label:<26} n={len(sel):5d} dates={ci[2] if ci else 0:4d} hit={hit:5.1f}% "
          f"units={units(sel):+8.2f} ROI={roi:+7.2f}%  CI {cis}")
    return {"n": len(sel), "roi": roi, "ci": ci}


def verdict(pool, fit, hold):
    if not pool or pool["n"] < MIN_CELL_N:
        return "THIN -> KILL for wiring (n < 100)"
    if pool["roi"] <= 0:
        return "KILL (pooled ROI <= 0)"
    if not fit or not hold or (fit["roi"] > 0) != (hold["roi"] > 0):
        return "KILL (halves disagree in sign)"
    if pool["ci"] and pool["ci"][0] > 0:
        return "A — actionable to PAPER"
    return "B — informative, shadow only"


def main():
    rows = collect()
    if not rows:
        print("no rows")
        return
    print(f"\nreplication split at {SPLIT} (pre-registered; nothing is fit on either half)\n")
    decided = {}
    for stat, m in PRIMARY + SECONDARY:
        tag = "PRIMARY" if (stat, m) in PRIMARY else "secondary"
        cell = [r for r in rows if r["stat"] == stat and r["proj"] - r["line"] >= m]
        print(f"=== {stat.upper()} >= {m}  [{tag}] ===")
        pool = line_of("pooled", cell)
        fit = line_of(f"before {SPLIT}", [r for r in cell if r["date"] < SPLIT])
        hold = line_of(f"from {SPLIT}", [r for r in cell if r["date"] >= SPLIT])
        v = verdict(pool, fit, hold)
        print(f"  -> {v}\n")
        if tag == "PRIMARY":
            decided[stat] = v

    print("=== the null on the SAME cold-start universe (bet every over, no margin) ===")
    for stat in ("pts", "pra", "reb"):
        line_of(f"always-over {stat}", [r for r in rows if r["stat"] == stat])

    print("\n=== margin sweep — INFORMATION ONLY, not a refit, not decisive ===")
    for stat in ("pts", "pra"):
        for m in (3.0, 5.0, 8.0):
            line_of(f"{stat} >= {m}", [r for r in rows if r["stat"] == stat
                                         and r["proj"] - r["line"] >= m])

    print("\n=== absence game 1 vs 2 at the primary cells — information only ===")
    for stat, m in PRIMARY:
        for a in (1, 2):
            line_of(f"{stat}>={m} absence game {a}", [r for r in rows if r["stat"] == stat
                    and r["proj"] - r["line"] >= m and r["aidx"] == a])

    print("\n=== PRE-REGISTERED VERDICT ===")
    for stat, v in decided.items():
        print(f"  {stat.upper()} >= {C.COLD_MARGIN}: {v}")


if __name__ == "__main__":
    main()
