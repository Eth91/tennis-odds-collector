#!/usr/bin/env python3
"""The two price leads on postseason games no test has graded. Executes NBA_PLAYOFF_HOLDOUT_PREREG.md.

Lead 1: P1 bets (nba_price_edge, unchanged) with EV >= 3% where the outlier book is BetMGM.
Lead 2: P1's best-outlier bets with EV >= 6%, any book. One look, after three data gates pass.

    python nba_price_playoffs.py --fetch      # postseason box scores -> nba_postseason.sqlite (MAC-ONLY)
    python nba_price_playoffs.py --selftest   # the gates' and the verdict's own guards
    python nba_price_playoffs.py              # gates, then the one look
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import nba_price_edge as E
import nba_pricing_realline as R

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_postseason.sqlite"
SEASONS = ("2022-23", "2023-24", "2024-25")
TYPES = ("Playoffs", "PlayIn")
CUP_FINALS = {"2023-12-09", "2024-12-17"}       # ungraded too, but not postseason: excluded
CHECK = ("player", "pts", "reb", "ast", "fg3m", "stl", "blk")
LEAD1_EV, LEAD1_BOOK, LEAD2_EV = 0.03, "betmgm", 0.06
GATE_SAME, GATE_ROWS, GATE_COVER, GATE_NAMES, MIN_N = 0.995, 0.005, 0.95, 0.95, 50


def postseason(d):
    """The postseason a date belongs to, by calendar year ('2023' = the 2022-23 playoffs)."""
    return d[:4] + " postseason"


# ── fetch ────────────────────────────────────────────────────────────────────────

def pull(season, stype):
    import nba_logs_full as LF                    # curl_cffi: Mac only, so imported here
    rs = LF._get("https://stats.nba.com/stats/leaguegamelog?Counter=1000&DateFrom=&DateTo="
                 f"&Direction=DESC&LeagueID=00&PlayerOrTeam=P&Season={season}"
                 f"&SeasonType={quote(stype)}&Sorter=DATE")
    ix = {c: i for i, c in enumerate(rs["headers"])}
    missing = [v for v in LF.SRC.values() if v not in ix]
    if missing:
        raise SystemExit(f"{season} {stype}: leaguegamelog no longer returns {missing}")
    return [(season, *[(r[ix[LF.SRC[c]]] if r[ix[LF.SRC[c]]] is not None else 0)
                                for c in LF.COLS[1:]], stype) for r in rs["rowSet"]]


def fetch():
    import nba_logs_full as LF
    con = sqlite3.connect(DB)
    ddl = ", ".join(c + (" INTEGER" if c == "player_id" else " TEXT" if c in
                         ("season", "game_id", "date", "team", "player") else " REAL") for c in LF.COLS)
    for table in ("logs_post", "check_regular"):
        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(f"CREATE TABLE {table} ({ddl}, season_type TEXT, PRIMARY KEY (game_id, player_id))")
    ins = lambda t, rows: con.executemany(
        f"INSERT OR REPLACE INTO {t} VALUES ({','.join('?' * (len(LF.COLS) + 1))})", rows)
    for season in SEASONS:
        for stype in TYPES:
            rows = pull(season, stype)
            ins("logs_post", rows)
            print(f"{season} {stype}: {len(rows):,} player-game rows", flush=True)
    rows = pull("2024-25", "Regular Season")   # gate 1: same code against logs_full
    ins("check_regular", rows)
    print(f"2024-25 Regular Season (gate 1 check): {len(rows):,} rows")
    con.commit()
    con.close()


# ── gates (pure functions; each mutation-tested) ─────────────────────────────────

def gate_same_source(new, ref):
    """new/ref: {(game_id, pid): (player, pts, reb, ast, fg3m, stl, blk)}. The fresh pull must match
    the stored regular season on >= 99.5% of its player-games, with row counts within 0.5%."""
    same = sum(1 for k, v in ref.items() if new.get(k) == v)
    ok = bool(ref) and abs(len(new) - len(ref)) <= GATE_ROWS * len(ref) and same >= GATE_SAME * len(ref)
    return ok, f"rows {len(new):,} vs stored {len(ref):,}; identical {same:,} ({100 * same / max(1, len(ref)):.2f}%)"


def postseason_nights(games_by_night, reg_dates):
    """The ungraded odds nights that are postseason: not a regular-season date, not a Cup final."""
    return {d: n for d, n in games_by_night.items() if d not in reg_dates and d not in CUP_FINALS}


def gate_coverage(odds_games, box_games):
    """{night: games}. On >= 95% of the postseason odds nights the box holds the same game count."""
    hit = sum(1 for d, n in odds_games.items() if box_games.get(d, 0) == n)
    ok = bool(odds_games) and hit >= GATE_COVER * len(odds_games)
    short = sorted(d for d, n in odds_games.items() if box_games.get(d, 0) != n)
    return ok, f"{hit} of {len(odds_games)} nights match" + (f"; differ: {short[:8]}" if short else "")


def gate_names(keys, box):
    """keys: the (date, norm) of postseason lines with >= 3 books. >= 95% must be in that night's box."""
    found = sum(1 for k in keys if k in box)
    ok = bool(keys) and found >= GATE_NAMES * len(keys)
    return ok, f"{found:,} of {len(keys):,} ({100 * found / max(1, len(keys)):.1f}%)"


def lead1(rows):
    return [r for r in rows if r["ev"] >= LEAD1_EV and r["book"] == LEAD1_BOOK]


def lead2(rows):
    return [r for r in rows if r["ev"] >= LEAD2_EV]


def verdict(c):
    if not c or c["n"] < MIN_N:
        return "inconclusive (n < 50)"
    if c["roi"] <= 0:
        return "KILL (holdout ROI <= 0) -> the lead is dropped"
    if c["ci"] and c["ci"][0] > 0:
        return "CONFIRMED (CI lower bound > 0)"
    return "NOT REFUTED (ROI > 0, CI includes 0) -> still only a lead"


# ── the run ──────────────────────────────────────────────────────────────────────

def load_gate_inputs():
    reg = sqlite3.connect(f"file:{R.LOGS}?mode=ro", uri=True)
    post = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    odds = sqlite3.connect(f"file:{R.ODDS}?mode=ro", uri=True)
    sel = "SELECT game_id, player_id, " + ", ".join(CHECK) + " FROM "
    ref = {(g, p): tuple(v) for g, p, *v in reg.execute(sel + "logs_full WHERE season = '2024-25'")}
    new = {(g, p): tuple(v) for g, p, *v in post.execute(sel + "check_regular")}
    reg_dates = {r[0] for r in reg.execute("SELECT DISTINCT date FROM logs_full")}
    odds_games = postseason_nights(dict(odds.execute(
        "SELECT game_date, COUNT(DISTINCT event_id) FROM props GROUP BY game_date")), reg_dates)
    box_games = dict(post.execute("SELECT date, COUNT(DISTINCT game_id) FROM logs_post GROUP BY date"))
    for c in (reg, post, odds):
        c.close()
    return new, ref, odds_games, box_games


def main():
    new, ref, odds_games, box_games = load_gate_inputs()
    quotes, amb = E.load_quotes()
    box, bamb = E.load_box(DB, table="logs_post", seasons=SEASONS)
    keys = {(d, nm) for (d, nm, stat, line), bk in quotes.items()
            if d in odds_games and E.best_outlier(bk) is not None}
    print("=== gates (all must pass before any grading) ===")
    gates = (("1 same source as logs_full", gate_same_source(new, ref)),
             ("2 postseason coverage", gate_coverage(odds_games, box_games)),
             ("3 name match", gate_names(keys, box)))
    for name, (ok, detail) in gates:
        print(f"  {'PASS' if ok else 'FAIL'}  gate {name}: {detail}")
    if not all(ok for _, (ok, _d) in gates):
        print("A gate failed: nothing is graded.")
        sys.exit(1)

    rows, cnt = E.p1_rows({k: v for k, v in quotes.items() if k[0] in odds_games}, box)
    rows = [dict(r, season=postseason(r["date"])) for r in rows]
    print(f"\npostseason nights {len(odds_games)}; ambiguous names dropped: odds {len(amb)}, box {len(bamb)}; {cnt}")
    print("\n=== THE ONE LOOK ===")
    for label, sub in (("Lead 1 — BetMGM is the outlier, EV >= 3%", lead1(rows)),
                       ("Lead 2 — EV >= 6%, any book", lead2(rows))):
        print(label)
        c = R.line_of("  holdout", sub)
        if sub:
            print(f"      claimed EV {100 * st.mean(r['ev'] for r in sub):+.2f}%; p_fair "
                  f"{st.mean(r['p_fair'] for r in sub):.3f} vs realised {st.mean(r['won'] for r in sub):.3f}")
        print(f"  VERDICT: {verdict(c)}\n")

    print("--- information only ---")
    p1 = [r for r in rows if r["ev"] >= E.EV_MIN]
    R.line_of("P1, EV >= 3%, all books", p1)
    R.line_of("  control: same bets at the reference avg price", [dict(r, price=r["avg_price"]) for r in p1])
    if p1:
        print(f"      p_fair {st.mean(r['p_fair'] for r in p1):.3f} vs realised {st.mean(r['won'] for r in p1):.3f}")
    for s in sorted({r["season"] for r in rows}):
        R.line_of(f"  {s}", [r for r in p1 if r["season"] == s])
        R.line_of(f"    Lead 1", [r for r in lead1(rows) if r["season"] == s])
        R.line_of(f"    Lead 2", [r for r in lead2(rows) if r["season"] == s])
    for b in E.BOOKS4:
        R.line_of(f"  book bet: {b}", [r for r in p1 if r["book"] == b])
    for side in ("over", "under"):
        R.line_of(f"  side: {side}", [r for r in p1 if r["side"] == side])


# ── selftest ─────────────────────────────────────────────────────────────────────

def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok &= bool(cond)

    ref = {(f"g{i}", i): ("P", 10, 5, 3, 1, 1, 0) for i in range(1000)}
    check("gate 1: identical pull passes", gate_same_source(dict(ref), ref)[0])
    bad = dict(ref)
    for i in range(6):
        bad[(f"g{i}", i)] = ("P", 11, 5, 3, 1, 1, 0)
    check("gate 1: 0.6% of rows differing fails", not gate_same_source(bad, ref)[0])
    few = dict(list(ref.items())[:994])
    check("gate 1: 0.6% of rows missing fails", not gate_same_source(few, ref)[0])
    many = {**ref, **{(f"x{i}", -i): ("Q", 1, 1, 1, 0, 0, 0) for i in range(6)}}
    check("gate 1: 0.6% extra rows fails", not gate_same_source(many, ref)[0])
    check("gate 1: an empty reference fails", not gate_same_source({}, {})[0])
    odds = {f"d{i}": 2 for i in range(100)}
    check("gate 2: 95 of 100 nights matching passes",
          gate_coverage(odds, {f"d{i}": 2 for i in range(95)})[0])
    check("gate 2: 94 of 100 nights fails (missing nights and short nights both count)",
          not gate_coverage(odds, {**{f"d{i}": 2 for i in range(94)}, "d94": 1})[0])
    check("gate 2: no odds nights fails", not gate_coverage({}, {})[0])
    keys = {(f"d{i}", "p") for i in range(100)}
    check("gate 3: 95% found passes", gate_names(keys, {(f"d{i}", "p"): 1 for i in range(95)})[0])
    check("gate 3: 94% found fails", not gate_names(keys, {(f"d{i}", "p"): 1 for i in range(94)})[0])
    r = lambda ev, book: {"ev": ev, "book": book}
    rows = [r(0.03, "betmgm"), r(0.0299, "betmgm"), r(0.05, "fanduel"), r(0.06, "draftkings"),
            r(0.0599, "williamhill_us"), r(0.07, "betmgm")]
    check("lead 1: BetMGM only, EV >= 3% inclusive", [x["ev"] for x in lead1(rows)] == [0.03, 0.07])
    check("lead 2: any book, EV >= 6% inclusive", [x["ev"] for x in lead2(rows)] == [0.06, 0.07])
    check("verdict: ROI <= 0 is KILL", verdict({"n": 100, "roi": 0.0, "ci": (-9, 9)}).startswith("KILL"))
    check("verdict: ROI > 0, CI spans 0 is NOT REFUTED",
          verdict({"n": 100, "roi": 3.0, "ci": (-9, 12)}).startswith("NOT REFUTED"))
    check("verdict: CI lower > 0 is CONFIRMED", verdict({"n": 100, "roi": 9.0, "ci": (0.5, 18)}).startswith("CONFIRMED"))
    check("verdict: n < 50 is inconclusive", verdict({"n": 49, "roi": 30.0, "ci": (5, 50)}).startswith("inconclusive")
          and verdict({"n": 50, "roi": 30.0, "ci": (5, 50)}).startswith("CONFIRMED") and verdict(None).startswith("incon"))
    check("postseason label by calendar year", postseason("2023-05-03") == "2023 postseason"
          and postseason("2025-06-22") == "2025 postseason")
    nights = postseason_nights({"2024-01-05": 9, "2023-12-09": 1, "2024-12-17": 1, "2024-05-01": 3},
                               {"2024-01-05"})
    check("postseason nights: regular-season dates and both Cup finals excluded", nights == {"2024-05-01": 3})
    print("selftest:", "ALL PASS" if ok else "FAILURES")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    fetch() if a.fetch else main()
