#!/usr/bin/env python3
"""The WNBA pricing machinery, run UNCHANGED on NBA real lines. Executes NBA_PRICING_PREREG.md.

Calls the WNBA's own functions — wnba_tonight.prop_edges, wnba_alert.position_compat,
wnba_slip.current_selection — with NBA inputs. The four NBA departures listed in the prereg are
module-global overrides in THIS process only; no frozen file is edited.

    python nba_pricing_realline.py --selftest   # controls: feed the WNBA functions correctly?
    python nba_pricing_realline.py              # the pre-registered test
    python nba_pricing_realline.py --secondary  # pre-registered info-only analyses
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import nba_margin_refit as RF
import nba_pricing as P            # the shared binding: NBA overrides + the WNBA functions
import nba_wowy as N
import wnba_slip as SL
import wnba_tonight as T

HERE = Path(__file__).resolve().parent
ODDS = HERE / "basketball_nba_odds_hist.sqlite"
LOGS = HERE / "nba_gamelogs.sqlite"
BOOKS = ("fanduel", "draftkings")
SPLIT = "2024-10-29"
BOOT_N, SEED, MIN_CELL_N = 4000, 7, 100
MKT = {"points": "player_points", "rebounds": "player_rebounds", "assists": "player_assists",
       "pra": "player_points_rebounds_assists", "pts_reb": "player_points_rebounds",
       "pts_ast": "player_points_assists", "reb_ast": "player_rebounds_assists"}
NBA_MARGIN = {"points": 3.0, "rebounds": 2.0, "pra": 5.0}          # the shipped margin rule

# The four pre-registered NBA departures are applied by importing nba_pricing.
_row = lambda r: P.row(*r)


def load_games():
    """{team: [(date, gid, {pid: row})]} from logs_full, franchise-pooled; names; positions."""
    con = sqlite3.connect(f"file:{LOGS}?mode=ro", uri=True)
    tg, cur, names = defaultdict(list), {}, {}
    for gid, date, team, pid, nm, mn, p, r, a, fga, fta, fg3a in con.execute(
            "SELECT game_id, date, team, player_id, player, min, pts, reb, ast, fga, fta, fg3a "
            "FROM logs_full ORDER BY date, game_id"):
        k = (team, gid)
        if k not in cur:
            cur[k] = {}
            tg[team].append((date, gid, cur[k]))
        cur[k][pid] = _row((float(mn), p, r, a, fga, fta, fg3a))
        names[pid] = nm
    pos = {pid: (p or "").replace("-", "").upper()
           for pid, p in con.execute("SELECT player_id, position FROM positions")}
    con.close()
    for k in tg:
        tg[k].sort(key=lambda g: g[0])
    return tg, names, pos


def load_lines():
    """{(date, norm(player)): {stat: {line: (best_over, best_under)}}} — FD + DK only, two-sided."""
    inv = {v: k for k, v in MKT.items()}
    o = sqlite3.connect(f"file:{ODDS}?mode=ro", uri=True, timeout=90)
    raw = defaultdict(lambda: [0.0, 0.0])
    q = (f"SELECT game_date, player, market, line, side, price FROM props WHERE book IN "
         f"({','.join('?' * len(BOOKS))}) AND market IN ({','.join('?' * len(inv))}) "
         "AND price IS NOT NULL AND line IS NOT NULL")
    for d, p, m, line, side, price in o.execute(q, (*BOOKS, *inv)):
        i = 0 if side == "over" else 1 if side == "under" else None
        if i is None:
            continue
        k = (d, RF.norm(p), inv[m], round(float(line), 1))
        raw[k][i] = max(raw[k][i], float(price))
    out = defaultdict(lambda: defaultdict(dict))
    for (d, nm, stat, line), (ov, un) in raw.items():
        if ov and un:
            out[(d, nm)][stat][line] = (ov, un)
    return out





def walk(tg, names, lines, cnt):
    """THE universe — one definition for every test on it. Yields one context per WOWY-tier
    candidate (absence game 1-2, X >= 28 min trailing-10, B with >= 2 games without X and >= 3
    with) that has real FanDuel/DraftKings lines that night. `cnt` collects the counts."""
    for team, games in tg.items():
        first_app = {}
        for i, (date, gid, box) in enumerate(games):
            for pid in box:
                first_app.setdefault(pid, date)
            if i < 12:
                continue
            cut = (N._d(date) - dt.timedelta(days=N.POOL_DAYS)).isoformat()
            lo = 0
            while lo < i and games[lo][0] < cut:
                lo += 1
            prior = games[lo:i]
            if len(prior) < 12:
                continue
            played_by = defaultdict(list)
            for pd, pg, pbox in prior:
                for pid, row in pbox.items():
                    played_by[pid].append((pd, pg, row))
            absents = [p for p, apps in played_by.items()
                       if p not in box and len(apps) >= 10
                       and sum(a[2]["min"] for a in apps[-10:]) / 10 >= N.STAR_MIN
                       and (N._d(date) - N._d(apps[-1][0])).days <= N.ACTIVE_DAYS]
            if not absents:
                continue
            X = max(absents, key=lambda p: sum(a[2]["min"] for a in played_by[p][-10:]))
            aidx = 1
            for pd, pg, pbox in reversed(prior):
                if X in pbox:
                    break
                aidx += 1
            if aidx > 2:
                continue
            x_first = first_app.get(X, "0000")
            out_g = [pbox for pd, pg, pbox in prior if pd >= x_first and X not in pbox]
            in_g = [pbox for pd, pg, pbox in prior if pd >= x_first and X in pbox]
            x_dates = {a[0]: a[2]["min"] for a in played_by[X]}
            for B, brow in box.items():
                if B == X or len(played_by.get(B, [])) < N.MIN_PRIOR_APPS:
                    continue
                b_out = [pb[B] for pb in out_g if B in pb]
                b_in = [pb[B] for pb in in_g if B in pb]
                if len(b_out) < N.MIN_WOWY or len(b_in) < 3:
                    continue
                cnt["candidates"] += 1
                nm = names.get(B, "")
                best = lines.get((date, RF.norm(nm)))
                if not best:
                    cnt["no_real_line"] += 1
                    continue
                cnt["with_lines"] += 1
                yield {"date": date, "team": team, "gid": gid, "box": box, "X": X, "B": B,
                       "brow": brow, "aidx": aidx, "prior": prior, "played_by": played_by,
                       "out_g": out_g, "in_g": in_g, "b_out": b_out, "b_in": b_in,
                       "x_first": x_first, "x_dates": x_dates, "best": best, "nm": nm}


def collect(ev_floor=None, transform=None):
    """Walk the WOWY-tier universe; return (selection rows, null rows, margin rows, counts).

    transform(B, game_date, row, as_of) -> row: an optional rewrite of the beneficiary's PRIOR game
    rows before pricing (NBA_TRACKING_PREREG.md, Arm S). It feeds only the pricing inputs — the log
    and the with/without split; the null and margin baselines and the graded outcome always use the
    real rows, so both arms are compared against the same yardstick. None = Arm T, unchanged."""
    if ev_floor is not None:
        T.OVER_EV_MIN = ev_floor
    tg, names, pos = load_games()
    lines = load_lines()
    print(f"real two-sided rungs (FD+DK) for {len(lines):,} player-dates")
    sel_rows, null_rows, margin_rows = [], [], []
    cnt = defaultdict(int)
    for c in walk(tg, names, lines, cnt):
        date, team, X, B, brow = c["date"], c["team"], c["X"], c["B"], c["brow"]
        prior, played_by, x_first, x_dates = c["prior"], c["played_by"], c["x_first"], c["x_dates"]
        b_out, b_in, best, nm = c["b_out"], c["b_in"], c["best"], c["nm"]
        if transform is None:
            log = [dict(row, date=d, game_id=g, matchup="")
                   for d, g, row in reversed(played_by[B])]      # NEWEST-first, as WNBA
            w = P.wowy(b_in, b_out)
        else:
            tf = lambda d, row, _B=B, _asof=date: transform(_B, d, row, _asof)
            log = [dict(tf(d, row), date=d, game_id=g, matchup="")
                   for d, g, row in reversed(played_by[B])]
            w = P.wowy([tf(pd, pb[B]) for pd, pg, pb in prior
                        if pd >= x_first and X in pb and B in pb],
                       [tf(pd, pb[B]) for pd, pg, pb in prior
                        if pd >= x_first and X not in pb and B in pb])
        spots, proj = P.price(nm, log, w, pos.get(B, ""), pos.get(X, ""), x_dates, best)
        # baselines on the SAME candidate and SAME two books: the main (base) rung
        for stat, ladder in best.items():
            ml = T._main_line(ladder)
            if ml is None:
                continue
            ov = ladder[ml][0]
            won = 1 if brow[T.PROP_STATS[stat]] > ml else 0
            null_rows.append({"date": date, "stat": stat, "price": ov, "won": won})
            if stat in NBA_MARGIN:
                base_min = sum(a[2]["min"] for a in played_by[B][-10:]) / min(10, len(played_by[B]))
                min_out = sum(r["min"] for r in b_out)
                d_min = (min_out / len(b_out) - sum(r["min"] for r in b_in) / len(b_in))
                d_min *= len(b_out) / (len(b_out) + N.K_DMIN)
                key = T.PROP_STATS[stat]
                tot_out = sum(r[key] for r in b_out)
                b10 = played_by[B][-10:]
                base_rate = sum(a[2][key] for a in b10) / max(1e-9, sum(a[2]["min"] for a in b10))
                rate = (tot_out + base_rate * N.K_MIN) / (min_out + N.K_MIN)
                if rate * (base_min + d_min) - ml >= NBA_MARGIN[stat]:
                    margin_rows.append({"date": date, "stat": stat, "price": ov, "won": won})
        for s in P.base_rung_overs(spots):
            key = T.PROP_STATS[s["stat"]]
            sel_rows.append({"pred_date": date, "team": team, "player": nm,
                             "stat": s["stat"], "line": s["line"], "side": "over",
                             "ev": s["ev"], "odds": s["dec"], "d_min": s.get("d_min"),
                             "n_elev": s["n"], "hit": s["hit"], "basis": s.get("basis"),
                             "date": date, "price": s["dec"],
                             "won": 1 if brow[key] > s["line"] else 0,
                             "elev": s.get("elev_avg"), "season_avg": s.get("season_avg"),
                             "actual": brow[key]})
    return sel_rows, null_rows, margin_rows, dict(cnt)


# ── statistics ───────────────────────────────────────────────────────────────────

def units(v):
    return sum((r["price"] - 1.0) if r["won"] else -1.0 for r in v)


def boot(sel):
    byd = defaultdict(list)
    for r in sel:
        byd[r["date"]].append(r)
    ds = list(byd)
    if len(ds) < 10:
        return None
    rnd = random.Random(SEED)
    res = sorted(units(p) / len(p) * 100
                 for p in ([r for _ in ds for r in byd[rnd.choice(ds)]] for _ in range(BOOT_N)))
    return res[int(.025 * BOOT_N)], res[int(.975 * BOOT_N)], len(ds)


def line_of(label, sel):
    if not sel:
        print(f"  {label:<34} (none)")
        return None
    roi = units(sel) / len(sel) * 100
    ci = boot(sel)
    print(f"  {label:<34} n={len(sel):5d} dates={ci[2] if ci else 0:4d} "
          f"hit={100 * sum(r['won'] for r in sel) / len(sel):5.1f}% units={units(sel):+8.2f} "
          f"ROI={roi:+7.2f}%  CI " + (f"[{ci[0]:+6.2f}%, {ci[1]:+6.2f}%]" if ci else "n/a"))
    return {"n": len(sel), "roi": roi, "ci": ci}


def verdict(pool, fit, hold, null, margin):
    if not pool or pool["n"] < MIN_CELL_N:
        return "THIN -> KILL for wiring (n < 100)"
    if pool["roi"] <= 0:
        return "KILL (pooled ROI <= 0)"
    if not fit or not hold or (fit["roi"] > 0) != (hold["roi"] > 0):
        return "KILL (halves disagree in sign)"
    if pool["roi"] <= max(null["roi"], margin["roi"] if margin else -1e9):
        return "KILL (does not beat the null / margin baselines)"
    if pool["ci"] and pool["ci"][0] > 0:
        return "A — actionable to PAPER"
    return "B — informative, shadow only"


def selftest():
    """Positive and negative controls: is the harness feeding the WNBA functions correctly?"""
    import copy
    base = [{"date": f"2025-01-{30 - i:02d}", "game_id": str(i), "matchup": "", **_row(
        (34.0, 24, 6, 5, 18, 6, 6))} for i in range(14)]           # an established 34-min role
    best = {"points": {17.5: (1.91, 1.91)}}                         # a line far below the role
    def wblock(mn, fga):
        rows = [_row((mn, 20, 6, 5, fga, 5, 6)) for _ in range(6)]
        return P.wowy_block(rows)
    w_up = {"n_with": 6, "n_without": 6, "with": wblock(28.0, 13), "without": wblock(34.0, 18)}
    s1, p1 = P.price("Control Up", base, w_up, "G", "G", {}, best)
    w_flat = {"n_with": 6, "n_without": 6, "with": wblock(34.0, 18), "without": wblock(34.0, 18)}
    s2, p2 = P.price("Control Flat", copy.deepcopy(base), w_flat, "G", "G", {}, best)
    ok1 = any(s["side"] == "over" and s["stat"] == "points" for s in s1)
    ok2 = not s2
    print(f"positive control (role expands +6 min / +5 FGA, line 17.5 vs ~24): "
          f"{len(s1)} spot(s), proj_min {p1:.1f} -> {'PASS' if ok1 else 'FAIL'}"
          + (f"  ev {s1[0]['ev']:+.3f} hit {s1[0]['hit']:.2f} n {s1[0]['n']}" if s1 else ""))
    print(f"negative control (flat role -> conviction gate must refuse): "
          f"{len(s2)} spot(s), proj_min {p2:.1f} -> {'PASS' if ok2 else 'FAIL'}")
    rows = [dict(pred_date="2025-01-31", team="AAA", player=f"P{i}", stat=s, line=10.5,
                 side="over", ev=0.2, odds=1.9, d_min=4.0, n_elev=12)
            for i, s in enumerate(("points", "rebounds", "assists", "pra"))]
    kept, dropped = P.select(rows)
    ok3 = len(kept) <= 2
    print(f"selection control (4 same-team overs -> top-2 disjoint): kept {len(kept)} "
          f"{[(r['player'], r['stat']) for r in kept]} -> {'PASS' if ok3 else 'FAIL'}")
    return ok1 and ok2 and ok3


def main():
    sel, null, margin, cnt = collect()
    print(f"universe: {cnt}")
    kept, dropped = P.select(sel)
    print(f"priced base-rung overs: {len(sel)} -> after current_selection: {len(kept)}"
          f" (dropped {len(dropped)})\n")
    print(f"=== ARM T — the WNBA machinery, transferred, nothing fitted [PRIMARY] ===")
    pool = line_of("pooled", kept)
    fit = line_of(f"before {SPLIT}", [r for r in kept if r["date"] < SPLIT])
    hold = line_of(f"from {SPLIT}", [r for r in kept if r["date"] >= SPLIT])
    print("\n=== baselines — same candidates, same two books, main rung ===")
    nul = line_of("always-over null (7 stats)", null)
    mar = line_of("shipped margin rule (pts/reb/pra)", margin)
    print(f"\n  -> PRE-REGISTERED VERDICT: {verdict(pool, fit, hold, nul, mar)}\n")
    print("=== per stat — information only ===")
    for s in MKT:
        line_of(s, [r for r in kept if r["stat"] == s])
    print("\n=== by basis — information only ===")
    for b in sorted({r.get("basis") for r in kept}, key=str):
        line_of(str(b), [r for r in kept if r.get("basis") == b])




def secondary():
    """Pre-registered SECONDARY analyses — information only, never decisive."""
    sel, _, _, _ = collect(ev_floor=-1.0)                # every priced base rung, any EV
    print(f"all priced base-rung overs (EV bar removed): {len(sel)}")

    def picked(rows, bar, k=None):
        out = []
        for r in rows:
            ev = r["ev"]
            if k is not None:
                n, h, d = r["n_elev"], r["hit"], r["odds"]
                ev = ((h * n + k / d) / (n + k)) * d - 1
            if ev >= bar:
                out.append(dict(r, ev=ev))
        return P.select(out)[0]

    print("\n=== calibration of the shipped model (k as shipped, bar 0.10) ===")
    kept = picked(sel, 0.10)
    bins = [(-1, .10), (.10, .20), (.20, .35), (.35, 9)]
    for lo, hi in bins:
        b = [r for r in kept if lo <= r["ev"] < hi]
        if b:
            pm = st.mean((r["ev"] + 1) / r["odds"] for r in b)
            print(f"  EV {lo:+.2f}..{hi:+.2f}: n={len(b):4d}  model P(over) {pm:.3f}  "
                  f"realized {sum(r['won'] for r in b) / len(b):.3f}  ROI {units(b) / len(b) * 100:+6.2f}%")

    print("\n=== EV-bar sweep: chosen on the FIRST half by units, read on the SECOND ===")
    fit_rows = [r for r in sel if r["date"] < SPLIT]
    hold_rows = [r for r in sel if r["date"] >= SPLIT]
    best = None
    for bar in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.45):
        f, h = picked(fit_rows, bar), picked(hold_rows, bar)
        uf = units(f)
        print(f"  bar {bar:4.2f}: fit n={len(f):4d} {uf:+8.2f}u ({uf / max(1, len(f)) * 100:+6.2f}%)"
              f"   hold n={len(h):4d} {units(h):+8.2f}u ({units(h) / max(1, len(h)) * 100:+6.2f}%)")
        if best is None or uf > best[1]:
            best = (bar, uf)
    print(f"  -> fit-half choice: bar {best[0]}; judge it on its HOLD column above")

    print("\n=== shrink-k sensitivity at bar 0.10 (k=11 elevated / 14 breakout as shipped) ===")
    for k in (11, 20, 40, 80):
        kk = picked(sel, 0.10, k=k)
        line_of(f"k={k}", kk)



if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--secondary", action="store_true", help="pre-registered info-only analyses")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    secondary() if a.secondary else main()
