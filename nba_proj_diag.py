#!/usr/bin/env python3
"""Where does proj-1.0 lose to FanDuel's close? A DIAGNOSTIC for NBA_STATS_FEASIBILITY.md, not a model change.

Development after exposure: 2023-24 (tuning) and 2024-25 (held-out A, already spent for proj-1.0). Nothing here
is a confirmatory test, nothing is tuned, and no result changes proj-1.0 or its record.

D1  The model − close log-loss gap split by whether a regular teammate was missing (a player who appeared in
    7+ of his team's previous 10 games averaging 24+ minutes, and is not in this game's box score). Absences
    are mostly known before tip, so this asks whether the gap is concentrated where late information matters.
D2  Known minutes (an upper bound, uses the outcome's minutes): every analog draw keeps its per-minute
    production but is scaled to the minutes the player actually played. If this beats the close, the market's
    edge over the model is mostly minutes/role information, which per-minute production stats (tracking,
    hustle, play types) do not supply.
    python3 nba_proj_diag.py            # prints the tables, writes .projdata/diag.json
"""
import json
from collections import defaultdict, deque

import numpy as np

import nba_proj_eval as E
import nba_project as NP

SEASONS = ("2023-24", "2024-25")
REG_GAMES, REG_MIN = 7, 24.0


def absence_rows(rows):
    """Row indices whose own team was missing at least one regular (pre-game definition, from earlier games)."""
    by_game = defaultdict(list)
    for i, r in enumerate(rows):
        by_game[(r["date"], r["gid"], r["team"])].append(i)
    hist = defaultdict(lambda: deque(maxlen=10))                # team -> last 10 games' {pid: min}
    out = set()
    for (d, gid, team), ii in sorted(by_game.items()):
        last = hist[team]
        played = defaultdict(list)
        for g in last:
            for pid, mn in g.items():
                played[pid].append(mn)
        regulars = {p for p, m in played.items() if len(m) >= REG_GAMES and np.mean(m) >= REG_MIN}
        here = {rows[i]["pid"] for i in ii}
        if len(last) == 10 and regulars - here:
            out.update(ii)
        last.append({rows[i]["pid"]: rows[i]["min"] for i in ii})
    return out


def known_minutes(run, d, idx):
    """d with every draw's counts scaled by actual minutes / draw minutes (minutes set to the actual)."""
    out = NP.Dist.__new__(NP.Dist)
    v = d.vals.copy()
    act = run.Y[idx, 0][:, None]
    m = np.maximum(v[:, :, 0], 1.0)
    v[:, :, 1:] *= (act / m)[:, :, None]
    v[:, :, 0] = act
    out.vals, out.mu = v, d.mu
    return out


def ci(x, dates):
    m, lo, hi = E.boot_ci(x, dates, reps=2000)
    return [round(m, 4), round(lo, 4), round(hi, 4)]


def main():
    data = E.load()
    rows = data["rows"]
    run = E.Run(rows, NP.PROJ_CONFIG, NP.context_constants(rows))
    absent = absence_rows(rows)
    report = {}
    for season in SEASONS:
        idx = np.where(run.season == season)[0]
        d = run.dist(idx)
        joined = E.fd_join(run, data["hist"], set(idx.tolist()))
        mp = E.market_probs(run, d, idx, joined)
        mk = E.market_probs(run, known_minutes(run, d, idx), idx, joined)
        keep = ~mp["push"]
        y, rws = mp["over"][keep], mp["row"][keep]
        dates = run.date[rws]
        ll = lambda p: E.logloss(p[keep], y)
        close = ll(mp["p_mkt"])
        gap = ll(mp["p_m1"]) - close
        gap_km = ll(mk["p_m1"]) - close
        blend = E.logloss(NP.blend(mp["p_m1"][keep], mp["p_mkt"][keep], NP.PROJ_BLEND_W), y) - close
        ab = np.array([r in absent for r in rws])
        seg = {}
        for name, sel in (("all", np.ones(len(y), bool)), ("teammate regular out", ab), ("no regular out", ~ab)):
            seg[name] = {"n": int(sel.sum()), "dates": int(len(set(dates[sel]))),
                         "close_ll": round(float(close[sel].mean()), 4),
                         "model_minus_close": ci(gap[sel], dates[sel]),
                         "blend_minus_close": ci(blend[sel], dates[sel]),
                         "known_minutes_minus_close": ci(gap_km[sel], dates[sel])}
        report[season] = seg
        print(f"\n{season} (FanDuel lines, pushes excluded)")
        print(f"{'segment':24s} {'n':>7s} {'close ll':>9s}  {'model − close':>30s}  {'known-minutes model − close':>30s}")
        for name, s in seg.items():
            f = lambda c: f"{c[0]:+.4f} [{c[1]:+.4f}, {c[2]:+.4f}]"
            print(f"{name:24s} {s['n']:7d} {s['close_ll']:9.4f}  {f(s['model_minus_close']):>30s}  "
                  f"{f(s['known_minutes_minus_close']):>30s}")
    (E.DATA / "diag.json").write_text(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    main()
