#!/usr/bin/env python3
"""NBA port · base rate on REAL tip lines (not the proxy).

WHY THIS EXISTS. nba_wowy.py --validate reports 66.8% PRA / 64.5% pts, but nba_wowy.py:45 says
those beat a "proxy line". The standing rule is REAL LINES ONLY — proxy lines inflate ~6-7pts.
Meanwhile basketball_nba_odds_hist.sqlite holds 2.0M REAL tip snapshots (2023-10..2025-04) that
the validation never touched. Any NBA edge claim must be judged against the real-line base rate,
not a proxy.

JOIN SAFETY (the name-collapse lesson): odds names are sometimes abbreviated ("A. Burks") while
logs are full. Matching on surname alone is catastrophic here -- 'Williams' maps to 14 players.
So: EXACT normalised full-name match only, suffixes stripped, and any odds row that does not
resolve to exactly ONE log player is DROPPED and counted, never guessed.
"""
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ODDS = HERE / "basketball_nba_odds_hist.sqlite"
LOGS = HERE / "nba_gamelogs.sqlite"
MARKET_STAT = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast",
               "player_points_rebounds_assists": "pra"}
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm(n):
    n = unicodedata.normalize("NFKD", str(n))
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    n = re.sub(r"[^a-z ]", " ", n)
    parts = [p for p in n.split() if p and p not in SUFFIX]
    return " ".join(parts)


def main():
    g = sqlite3.connect(f"file:{LOGS}?mode=ro", uri=True, timeout=60)
    o = sqlite3.connect(f"file:{ODDS}?mode=ro", uri=True, timeout=60)

    # actuals: (date, normalised name) -> stat dict.  Refuse to build an ambiguous key.
    actual, clash = {}, set()
    for d, p, mn, pts, reb, ast in g.execute(
            "SELECT date, player, min, pts, reb, ast FROM logs"):
        k = (d, norm(p))
        rec = {"pts": pts, "reb": reb, "ast": ast,
               "pra": (pts or 0) + (reb or 0) + (ast or 0), "min": mn}
        if k in actual and actual[k] != rec:
            clash.add(k)                      # two different players collapsed to one key
        actual[k] = rec
    print(f"actual keys: {len(actual):,}   ambiguous keys dropped: {len(clash)}")
    for k in clash:
        actual.pop(k, None)

    rows = o.execute(
        "SELECT game_date, player, market, line, side, price FROM props "
        "WHERE side='over' AND price IS NOT NULL AND line IS NOT NULL").fetchall()
    print(f"real over-quotes in the odds history: {len(rows):,}")

    graded = defaultdict(list)
    miss = defaultdict(int)
    for d, p, m, line, side, price in rows:
        stat = MARKET_STAT.get(m)
        if not stat:
            miss["market not mapped"] += 1; continue
        rec = actual.get((d, norm(p)))
        if rec is None:
            miss["player/date not in logs (DROPPED, never guessed)"] += 1; continue
        v = rec.get(stat)
        if v is None:
            miss["stat missing"] += 1; continue
        if float(v) == float(line):
            miss["push"] += 1; continue
        graded[stat].append((1 if float(v) > float(line) else 0, float(price)))
    print(f"  unmatched: {dict(miss)}")
    tot = sum(len(v) for v in graded.values())
    print(f"  GRADED on real lines: {tot:,}  ({tot/max(len(rows),1)*100:.1f}% of quotes)\n")

    print(f"{'stat':6s} {'n':>8s} {'over%':>8s} {'mean price':>11s} {'breakeven':>10s} {'ROI all-overs':>14s}")
    for stat in ("pts", "reb", "ast", "pra"):
        v = graded.get(stat) or []
        if len(v) < 500:
            print(f"{stat:6s} thin ({len(v)})"); continue
        hit = sum(w for w, _ in v) / len(v) * 100
        mp = st.mean([p for _, p in v])
        u = sum((p - 1.0) if w else -1.0 for w, p in v)
        print(f"{stat:6s} {len(v):8,} {hit:7.2f}% {mp:11.3f} {100/mp:9.1f}% {u/len(v)*100:+13.2f}%")
    print("\n  ^ this is the BASE RATE a real NBA edge must beat. Blindly betting every over is")
    print("    the null; nba_wowy's 66.8% is measured against a PROXY line and is not comparable.")


if __name__ == "__main__":
    main()
