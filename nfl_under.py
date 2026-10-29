#!/usr/bin/env python3
"""NFL_UNDER_PREREG.md: does the NBA under finding hold in the NFL? The under when his per-game average (last season
worth 4 games) is far below the main line near kickoff, graded on nflverse's weekly stats. Mac only.

    NFL_CACHE=.projdata/nfl_cache python3 nfl_under.py
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import nfl_common as C
import nfl_stats as S

ODDS = Path.home() / "tennis-odds-collector" / "americanfootball_nfl_odds_hist.sqlite"
OUT = Path(__file__).resolve().parent / ".projdata" / "nfl_under_result.json"
SEASONS = (2023, 2024, 2025)
K_LAST, MIN_GAMES = 4.0, 3
RATIO_AT, PING_LO, PING_HI, PRICE_MIN = 0.80, 0.50, 0.70, 1 / 0.6
L5_ZONE = (1.0564788482047636, 1.4166666666666667)          # the NBA's line filter (NBA_UNDER_PREREG.md amendment 9)
HEADLINE = {"player_pass_yds": ("passing_yards",), "player_pass_attempts": ("attempts",),
            "player_pass_completions": ("completions",), "player_rush_yds": ("rushing_yards",),
            "player_rush_attempts": ("carries",), "player_receptions": ("receptions",),
            "player_reception_yds": ("receiving_yards",), "player_rush_reception_yds": ("rushing_yards", "receiving_yards")}
SMALL = {"player_pass_tds": ("passing_tds",), "player_pass_interceptions": ("passing_interceptions",)}
MARKETS = {**HEADLINE, **SMALL}
rng = np.random.default_rng(5)


def season_of(date):
    y, m = int(date[:4]), int(date[5:7])
    return y if m >= 8 else y - 1


def key_of(name):
    return C.nosfx(C.fold(name))


def load_stats():
    """({game_id: {name key: row}}, {player_id: [(season, week, row)]}, {(season, away, home): [game_id by week]})."""
    by_game, mine, games = defaultdict(dict), defaultdict(list), defaultdict(set)
    for s in (2022,) + SEASONS:
        for r in S.weekly(s, 2026):
            gid = r.get("game_id") or ""
            parts = gid.split("_")
            if len(parts) != 4:
                continue
            season, week, away, home = int(parts[0]), int(parts[1]), C.team(parts[2]), C.team(parts[3])
            r["_s"], r["_w"] = season, week
            for k in {k for v in MARKETS.values() for k in v}:
                try:
                    r[k] = float(r.get(k) or 0)
                except ValueError:
                    r[k] = 0.0
            by_game[gid][key_of(r.get("player_display_name") or r.get("player_name") or "")] = r
            mine[r["player_id"]].append((season, week, r))
            games[(season, away, home)].add((week, gid))
    for v in mine.values():
        v.sort(key=lambda x: (x[0], x[1]))
    return by_game, mine, {k: [g for _w, g in sorted(v)] for k, v in games.items()}


def main_rungs(snap):
    """{(event, player key, market): (date, home, away, line, best under, no-vig over, {line: (over, under) per book})}."""
    o = sqlite3.connect(f"file:{ODDS}?immutable=1", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    meta = {}
    q = ("SELECT event_id, game_date, commence_time, home_team, away_team, book, market, player, side, line, price FROM props "
         "WHERE snap_kind = ? AND book IN ('fanduel', 'draftkings') AND price IS NOT NULL AND line IS NOT NULL AND market IN (%s)"
         % ",".join("?" * len(MARKETS)))
    for ev, d, ct, home, away, book, mk, pl, side, line, price in o.execute(q, (snap,) + tuple(MARKETS)):
        k = (ev, key_of(pl), mk)
        raw[k][float(line)].setdefault(book, [None, None])[0 if side == "over" else 1] = float(price)
        meta[ev] = (d, ct, C.team_of_name(home), C.team_of_name(away))
    out = {}
    for k, lb in raw.items():
        best = None
        for line, bk in lb.items():
            two = {b: v for b, v in bk.items() if v[0] and v[1]}
            if two:
                gap = min(abs(v[0] - 2.0) for v in two.values())
                if best is None or gap < best[0] - 1e-9:
                    best = (gap, line, two)
        if best:
            _g, line, two = best
            pair = two.get("fanduel") or two.get("draftkings")
            out[k] = (*meta[k[0]], line, max(v[1] for v in two.values()), (1 / pair[0]) / (1 / pair[0] + 1 / pair[1]),
                      {ln: {b: tuple(v) for b, v in bk.items() if v[0] and v[1]} for ln, bk in lb.items()})
    return out


def event_games(rungs, games):
    """{event: game_id}: by season and teams; a repeated pairing in a season goes by date order."""
    evs = defaultdict(list)
    for (ev, _p, _m), v in rungs.items():
        evs[(season_of(v[0]), v[3], v[2])].append((v[1], ev))       # (season, away, home)
    out = {}
    for k, lst in evs.items():
        gids = games.get(k, [])
        for (_ct, ev), gid in zip(sorted(set(lst)), gids):
            out[ev] = gid
    return out


def projection(hist, season, week, parts):
    """(projection, last-5 average): this season's per-game average before the week with last season's counted as K_LAST
    games; None under MIN_GAMES games across the two."""
    this = [r for s, w, r in hist if s == season and w < week]
    last = [r for s, w, r in hist if s == season - 1]
    if len(this) + len(last) < MIN_GAMES:
        return None
    st = lambda r: sum(r[p] for p in parts)
    tot, n = sum(st(r) for r in this), len(this)
    if last:
        tot, n = tot + K_LAST * sum(st(r) for r in last) / len(last), n + K_LAST
    before = [r for s, w, r in hist if (s, w) < (season, week)][-5:]
    return tot / n, (sum(st(r) for r in before) / len(before) if before else None)


def bets(snap, by_game, mine, games, tip=None):
    """Every graded prop at the snapshot: market, season, line, under price, no-vig over, projection ratio, l5, win."""
    rungs = main_rungs(snap)
    ev_gid = event_games(rungs, games)
    out = []
    for (ev, pk, mk), (d, _ct, home, away, line, under, q, ladder) in rungs.items():
        gid = ev_gid.get(ev)
        row = by_game.get(gid, {}).get(pk) if gid else None
        if row is None:
            continue
        parts = MARKETS[mk]
        act = sum(row[p] for p in parts)
        if act == line:
            continue
        pr = projection(mine[row["player_id"]], row["_s"], row["_w"], parts)
        b = {"ev": ev, "pk": pk, "mk": mk, "season": row["_s"], "date": d, "line": line, "under": under, "q": q, "over_won": act > line,
             "u": under - 1 if act < line else -1.0, "win": act < line, "ratio": pr[0] / line if pr and line else None,
             "l5": (line / pr[1]) if pr and pr[1] else None}
        if tip is not None:                                   # CLV against the near-kickoff no-vig at the same line
            t = tip.get((ev, pk, mk))
            same = t[7].get(line) if t else None
            pair = (same or {}).get("fanduel") or (same or {}).get("draftkings")
            b["clv"] = (1 - (1 / pair[0]) / (1 / pair[0] + 1 / pair[1])) * under - 1 if pair else None
        out.append(b)
    return out, rungs


def boot(v):
    v = np.array(v)
    if len(v) < 20:
        return f"n {len(v)}"
    bs = np.sort([rng.choice(v, len(v)).mean() for _ in range(2000)])
    return f"n {len(v):5d}  hit {np.mean(v > 0):.1%}  ROI {v.mean():+.3f} [{bs[100]:+.3f},{bs[1900]:+.3f}]"


def sets(bs, markets=HEADLINE):
    u20 = [b for b in bs if b["ratio"] is not None and b["ratio"] < RATIO_AT and b["mk"] in markets]
    elig = [b for b in u20 if b["under"] >= PRICE_MIN - 1e-9]
    ping = [b for b in elig if PING_LO <= b["ratio"] < PING_HI]
    return u20, elig, ping


def main():
    by_game, mine, games = load_stats()
    tip, tip_rungs = bets("tip", by_game, mine, games)
    res = {"n_props": len(tip)}
    head = [b for b in tip if b["mk"] in HEADLINE]
    print(f"graded props near kickoff: {len(tip)} ({len(head)} headline); events matched {len({b['ev'] for b in tip})}")
    print("\n== the book's no-vig over against the actual over rate (headline props)")
    for s in SEASONS:
        h = [b for b in head if b["season"] == s]
        print(f"  {s}: n {len(h)}  no-vig over {np.mean([b['q'] for b in h]):.4f}  actual over {np.mean([b['over_won'] for b in h]):.4f}")
    print("\n== the rules (headline markets)")
    u20, elig, ping = sets(tip)
    res["ping"] = {}
    for name, bs in (("UNDER20 (any price)", u20), ("20%+ set (-150 or better)", elig), ("ping set (30-50% below)", ping)):
        print(f"  {name}")
        for s in SEASONS:
            print(f"    {s}: {boot([b['u'] for b in bs if b['season'] == s])}")
        print(f"    pooled: {boot([b['u'] for b in bs])}")
    v = np.array([b["u"] for b in ping])
    bs_ = np.sort([rng.choice(v, len(v)).mean() for _ in range(2000)]) if len(v) else np.array([math.nan])
    pos = sum(np.mean([b["u"] for b in ping if b["season"] == s]) > 0 for s in SEASONS if any(b["season"] == s for b in ping))
    holds = bool(len(v) and v.mean() > 0 and bs_[100] > 0 and pos >= 2)
    res.update(ping_pooled=(len(v), float(v.mean()) if len(v) else None, float(bs_[100])), seasons_positive=int(pos), holds=holds)
    print(f"\n  -> pooled ping ROI {v.mean():+.3f}, 90% low {bs_[100]:+.3f}, positive in {pos} of 3 seasons: "
          f"{'HOLDS' if holds else 'DOES NOT HOLD'}")
    print("\n== ping set by market (pooled)")
    for mk in HEADLINE:
        print(f"  {mk:28s} {boot([b['u'] for b in ping if b['mk'] == mk])}")
    print("\n== 20%+ set by market (pooled)")
    for mk in HEADLINE:
        print(f"  {mk:28s} {boot([b['u'] for b in elig if b['mk'] == mk])}")
    print("\n== information")
    zone = lambda b: b["l5"] is not None and L5_ZONE[0] < b["l5"] <= L5_ZONE[1]
    print(f"  NBA line filter on the ping set: kept {boot([b['u'] for b in ping if not zone(b)])} | dropped {boot([b['u'] for b in ping if zone(b)])}")
    _u, e_s, p_s = sets(tip, SMALL)
    print(f"  passing TDs and interceptions: 20%+ set {boot([b['u'] for b in e_s])}; ping set {boot([b['u'] for b in p_s])}")
    op, _r = bets("opener", by_game, mine, games, tip=tip_rungs)
    _u, e_o, p_o = sets(op)
    for name, bs in (("20%+ set", e_o), ("ping set", p_o)):
        c = [b["clv"] for b in bs if b.get("clv") is not None]
        print(f"  two days out, {name}: {boot([b['u'] for b in bs])}; CLV vs near-kickoff {np.mean(c):+.3f} (n {len(c)})" if c else
              f"  two days out, {name}: {boot([b['u'] for b in bs])}")
    OUT.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
