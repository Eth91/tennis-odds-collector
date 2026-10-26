#!/usr/bin/env python3
"""Is there an edge in price alone? Executes NBA_PRICE_EDGE_PREREG.md.

P1: bet the book whose price beats the leave-one-out de-vigged consensus of the other books by
>= 3% EV, every player prop in the tip snapshot, 2023-24 and 2024-25 regular seasons.
P2: the null and Arm T re-priced at FD only / DK only / best FD+DK / best of four (execution only).

    python nba_price_edge.py --selftest   # guards (each mutation-tested)
    python nba_price_edge.py              # the pre-registered test
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics as st
import sys
from collections import defaultdict

import nba_margin_refit as RF
import nba_pricing as P
import nba_pricing_realline as R
import wnba_tonight as T

BOOKS4 = ("fanduel", "draftkings", "betmgm", "williamhill_us")
MKT10 = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists",
         "player_threes": "threes", "player_steals": "steals", "player_blocks": "blocks",
         "player_points_rebounds_assists": "pra", "player_points_rebounds": "pts_reb",
         "player_points_assists": "pts_ast", "player_rebounds_assists": "reb_ast"}
GRADE = {"points": lambda b: b["pts"], "rebounds": lambda b: b["reb"], "assists": lambda b: b["ast"],
         "threes": lambda b: b["fg3m"], "steals": lambda b: b["stl"], "blocks": lambda b: b["blk"],
         "pra": lambda b: b["pts"] + b["reb"] + b["ast"], "pts_reb": lambda b: b["pts"] + b["reb"],
         "pts_ast": lambda b: b["pts"] + b["ast"], "reb_ast": lambda b: b["reb"] + b["ast"]}
SEASONS = ("2023-24", "2024-25")
SEASON_SPLIT = "2024-07-01"
EV_MIN, MIN_BOOKS = 0.03, 3
BANDS = ((0.0, 0.02), (0.02, 0.04), (0.04, 0.06), (0.06, 0.10), (0.10, 9.9))
ARM_T = (1186, -41.09)
NULL = (35353, -6.97)


def season(d):
    return SEASONS[0] if d < SEASON_SPLIT else SEASONS[1]


# ── loading ──────────────────────────────────────────────────────────────────────

def load_quotes(path=R.ODDS, pre_tip_only=True, drop_ambiguous=True):
    """{(date, norm, stat, line): {book: [over, under]}} (a missing side is 0.0), plus the set of
    (date, norm) whose name maps to two players (two events that night) — dropped for P1; P2 keeps
    them (pre_tip_only=False, drop_ambiguous=False) to mirror nba_pricing_realline.load_lines."""
    o = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=90)
    q = ("SELECT game_date, event_id, player, market, line, side, price, book FROM props "
         "WHERE price IS NOT NULL AND line IS NOT NULL")
    if pre_tip_only:
        q += " AND snapshot_ts <= commence_time"
    quotes = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    events = defaultdict(set)
    for d, ev, p, m, line, side, price, book in o.execute(q):
        if m not in MKT10 or book not in BOOKS4 or side not in ("over", "under"):
            continue
        nm = RF.norm(p)
        events[(d, nm)].add(ev)
        q_ = quotes[(d, nm, MKT10[m], round(float(line), 1))][book]
        i = 0 if side == "over" else 1
        q_[i] = max(q_[i], float(price))
    o.close()
    amb = {k for k, evs in events.items() if len(evs) > 1}
    if not drop_ambiguous:
        return quotes, amb
    return {k: v for k, v in quotes.items() if (k[0], k[1]) not in amb}, amb


def load_box(path=R.LOGS, table="logs_full", seasons=SEASONS):
    """{(date, norm): box row} for the graded seasons (default: the two regular seasons);
    ambiguous names dropped. nba_price_playoffs reads its postseason table through this too."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    box, pids = {}, defaultdict(set)
    for d, pid, nm, mn, pts, reb, ast, fg3m, stl, blk in con.execute(
            f"SELECT date, player_id, player, min, pts, reb, ast, fg3m, stl, blk FROM {table} "
            f"WHERE season IN ({','.join('?' * len(seasons))})", seasons):
        k = (d, RF.norm(nm))
        pids[k].add(pid)
        box[k] = {"min": float(mn or 0), "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m,
                  "stl": stl, "blk": blk}
    con.close()
    amb = {k for k, s in pids.items() if len(s) > 1}
    return {k: v for k, v in box.items() if k not in amb}, amb


# ── P1 ───────────────────────────────────────────────────────────────────────────

def devig(over, under):
    return (1 / over) / (1 / over + 1 / under)


def best_outlier(books):
    """books: {book: [over, under]}. The highest-EV book-side against the leave-one-out consensus
    of the other two-sided books, or None if fewer than MIN_BOOKS are two-sided at this line."""
    two = {b: q for b, q in books.items() if q[0] > 1.0 and q[1] > 1.0}
    if len(two) < MIN_BOOKS:
        return None
    best = None
    for b in BOOKS4:
        if b not in two:
            continue
        ref = [two[k] for k in BOOKS4 if k in two and k != b]
        pf = st.mean(devig(*q) for q in ref)
        for i, side, p in ((0, "over", pf), (1, "under", 1 - pf)):
            ev = p * two[b][i] - 1
            if best is None or ev > best["ev"]:
                best = {"book": b, "side": side, "price": two[b][i], "p_fair": p, "ev": ev,
                        "avg_price": st.mean(q[i] for q in ref), "n_books": len(two)}
    return best


def grade(row, stat, line, side):
    """1/0, or None when the player did not play (void)."""
    if row is None or row["min"] <= 0:
        return None
    v = GRADE[stat](row)
    return int(v > line) if side == "over" else int(v < line)


def p1_rows(quotes, box):
    """Every graded best-outlier candidate with EV >= 0 (the bands); P1 filters EV >= EV_MIN."""
    out, cnt = [], defaultdict(int)
    for (d, nm, stat, line), books in quotes.items():
        b = best_outlier(books)
        if b is None:
            continue
        cnt["lines_3plus_books"] += 1
        if b["ev"] < 0:
            continue
        won = grade(box.get((d, nm)), stat, line, b["side"])
        if won is None:
            cnt["void_or_ungraded"] += 1
            continue
        out.append(dict(b, date=d, season=season(d), player=nm, stat=stat, line=line, won=won))
    return out, dict(cnt)


def verdict_p1(pool, s1, s2):
    if not pool or pool["n"] < R.MIN_CELL_N:
        return "THIN -> KILL (n < 100)"
    if pool["roi"] <= 0:
        return "KILL (pooled ROI <= 0)"
    if not s1 or not s2 or (s1["roi"] > 0) != (s2["roi"] > 0):
        return "KILL (the two seasons disagree in sign)"
    if pool["ci"] and pool["ci"][0] > 0:
        return "A — actionable to PAPER"
    return "B — informative, shadow only"


# ── P2 ───────────────────────────────────────────────────────────────────────────

def over_price(quotes, key, books):
    """The best over quote at this exact line among `books` (one-sided allowed, as the harness)."""
    q = quotes.get(key, {})
    return max((q[b][0] for b in books if b in q and q[b][0] > 1.0), default=None)


def repriced(rows, quotes, books):
    out = []
    for r in rows:
        p = over_price(quotes, r["key"], books)
        if p is not None:
            out.append(dict(r, price=p))
    return out


def lowest_line(quotes_by_ps, d, nm, stat):
    """(line, best over price) at the lowest line any of the four books quotes an over on."""
    ls = quotes_by_ps.get((d, nm, stat))
    if not ls:
        return None
    line = min(ls)
    return line, max(ls[line])


# ── selftest ─────────────────────────────────────────────────────────────────────

def selftest():
    import os
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok &= bool(cond)

    check("de-vig: even prices -> 0.5", abs(devig(1.909, 1.909) - 0.5) < 1e-12)
    check("de-vig: 1.5 / 2.75 -> 0.6471", abs(devig(1.5, 2.75) - (1 / 1.5) / (1 / 1.5 + 1 / 2.75)) < 1e-12
          and abs(devig(1.5, 2.75) - 0.6471) < 1e-4)
    even = [1.91, 1.91]
    b = best_outlier({"fanduel": [3.0, 1.30], "draftkings": list(even), "betmgm": list(even)})
    check("leave-one-out: the outlier's own price is not in its reference (p_fair = 0.5)",
          b and b["book"] == "fanduel" and b["side"] == "over" and abs(b["p_fair"] - 0.5) < 1e-12
          and abs(b["ev"] - 0.5) < 1e-12 and abs(b["avg_price"] - 1.91) < 1e-12)
    check("needs >= 3 two-sided books", best_outlier({"fanduel": [3.0, 1.3], "draftkings": list(even)}) is None)
    check("a one-sided book does not count",
          best_outlier({"fanduel": [3.0, 1.3], "draftkings": list(even), "betmgm": [1.91, 0.0]}) is None)
    b = best_outlier({"fanduel": [1.30, 3.0], "draftkings": list(even), "betmgm": list(even),
                      "williamhill_us": list(even)})
    check("finds an outlier under, reference = 3 books", b and b["side"] == "under" and b["n_books"] == 4
          and abs(b["ev"] - 0.5) < 1e-12)
    row = {"min": 30.0, "pts": 20, "reb": 7, "ast": 5, "fg3m": 3, "stl": 1, "blk": 2}
    check("grading: over / under", grade(row, "points", 19.5, "over") == 1
          and grade(row, "points", 20.5, "over") == 0 and grade(row, "points", 20.5, "under") == 1
          and grade(row, "points", 19.5, "under") == 0)
    check("grading: combos and threes", grade(row, "pra", 31.5, "over") == 1
          and grade(row, "pra", 32.5, "over") == 0 and grade(row, "reb_ast", 11.5, "over") == 1
          and grade(row, "threes", 2.5, "over") == 1 and grade(row, "threes", 3.5, "over") == 0
          and grade(row, "steals", 0.5, "over") == 1 and grade(row, "steals", 1.5, "over") == 0
          and grade(row, "blocks", 1.5, "over") == 1 and grade(row, "blocks", 2.5, "over") == 0)
    check("void: no box score, or 0 minutes", grade(None, "points", 9.5, "over") is None
          and grade(dict(row, min=0.0), "points", 9.5, "over") is None)

    with tempfile.TemporaryDirectory() as tmp:
        odds, logs = os.path.join(tmp, "o.sqlite"), os.path.join(tmp, "l.sqlite")
        c = sqlite3.connect(odds)
        c.execute("CREATE TABLE props (sport, event_id, commence_time, game_date, home_team, away_team, "
                  "book, market, player, side, line, price, snapshot_ts, snap_kind, fetched_at)")
        rows = []
        for ev, ct, snap, d, p in (("e1", "2024-01-02T00:40:00Z", "2024-01-02T00:10:38Z", "2024-01-01", "Ann Bee"),
                                   ("e2", "2024-01-03T00:40:00Z", "2024-01-03T01:10:38Z", "2024-01-02", "Cee Dee"),
                                   ("e3", "2024-01-04T00:40:00Z", "2024-01-04T00:10:38Z", "2024-01-03", "Eff Gee"),
                                   ("e4", "2024-01-04T00:40:00Z", "2024-01-04T00:10:38Z", "2024-01-03", "Eff Gee Jr.")):
            for bk in BOOKS4[:3]:
                for side in ("over", "under"):
                    rows.append(("nba", ev, ct, d, "", "", bk, "player_points", p, side, 10.5, 1.91, snap, "tip", ""))
        c.executemany("INSERT INTO props VALUES (" + ",".join("?" * 15) + ")", rows)
        c.commit()
        c.close()
        qs, amb = load_quotes(odds)
        check("loader: pre-tip snapshot kept", ("2024-01-01", "ann bee", "points", 10.5) in qs)
        check("loader: in-play snapshot dropped", not any(k[1] == "cee dee" for k in qs))
        q2 = load_quotes(odds, pre_tip_only=False, drop_ambiguous=False)[0]
        check("loader: P2 mode keeps in-play and ambiguous rows (mirrors the harness)",
              any(k[1] == "cee dee" for k in q2) and any(k[1] == "eff gee" for k in q2))
        check("loader: a name on two events that night is dropped",
              ("2024-01-03", "eff gee") in amb and not any(k[1] == "eff gee" for k in qs))
        c = sqlite3.connect(logs)
        c.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fgm, fga, "
                  "fg3m, fg3a, ftm, fta, oreb, dreb, reb, ast, stl, blk, tov, pf, pts, plus_minus)")
        for s, d, pid, nm in (("2023-24", "2024-01-01", 1, "Ann Bee"), ("2023-24", "2024-01-01", 2, "Hal Eye"),
                              ("2023-24", "2024-01-01", 3, "Hal Eye"), ("2022-23", "2023-01-01", 4, "Old Guy")):
            c.execute("INSERT INTO logs_full (season, date, player_id, player, min, pts, reb, ast, fg3m, stl, blk) "
                      "VALUES (?,?,?,?,30,10,5,5,1,1,1)", (s, d, pid, nm))
        c.commit()
        c.close()
        bx, bamb = load_box(logs)
        check("box: two players with one name that night are dropped",
              ("2024-01-01", "hal eye") in bamb and ("2024-01-01", "hal eye") not in bx)
        check("box: only the two graded seasons", ("2024-01-01", "ann bee") in bx
              and ("2023-01-01", "old guy") not in bx)
    print("selftest:", "ALL PASS" if ok else "FAILURES")
    return ok


# ── main ─────────────────────────────────────────────────────────────────────────

def cut(label, rows):
    return R.line_of(label, rows)


def main():
    print("=== P1 — bet the book that disagrees with the others ===")
    quotes, amb = load_quotes()
    box, bamb = load_box()
    rows, cnt = p1_rows(quotes, box)
    print(f"player-stat-lines {len(quotes):,}; ambiguous names dropped: odds {len(amb)}, box {len(bamb)}; {cnt}")
    bets = [r for r in rows if r["ev"] >= EV_MIN]
    pool = cut("P1 pooled, EV >= 3%", bets)
    s1 = cut("  2023-24", [r for r in bets if r["season"] == SEASONS[0]])
    s2 = cut("  2024-25", [r for r in bets if r["season"] == SEASONS[1]])
    cut("control: same bets at the reference avg price", [dict(r, price=r["avg_price"]) for r in bets])
    if bets:
        print(f"  mean EV claimed {100 * st.mean(r['ev'] for r in bets):+.2f}%; mean p_fair "
              f"{st.mean(r['p_fair'] for r in bets):.3f} vs realised {st.mean(r['won'] for r in bets):.3f}")
    print(f"\nVERDICT P1: {verdict_p1(pool, s1, s2)}")

    print("\n--- information only ---")
    for lo, hi in BANDS:
        sub = [r for r in rows if lo <= r["ev"] < hi]
        cut(f"EV {100 * lo:.0f}-{100 * hi:.0f}%" if hi < 9 else f"EV >= {100 * lo:.0f}%", sub)
        if sub:
            print(f"      p_fair {st.mean(r['p_fair'] for r in sub):.3f} vs realised {st.mean(r['won'] for r in sub):.3f}")
    for b in BOOKS4:
        cut(f"book bet: {b}", [r for r in bets if r["book"] == b])
    cut("at FanDuel or DraftKings", [r for r in bets if r["book"] in BOOKS4[:2]])
    for s in ("over", "under"):
        cut(f"side: {s}", [r for r in bets if r["side"] == s])
    for stat in GRADE:
        cut(f"market: {stat}", [r for r in bets if r["stat"] == stat])

    print("\n=== P2 — what shopping adds (execution only) ===")
    q_all, _ = load_quotes(pre_tip_only=False, drop_ambiguous=False)
    by_ps = defaultdict(lambda: defaultdict(list))
    for (d, nm, stat, line), bk in q_all.items():
        for q in bk.values():
            if q[0] > 1.0:
                by_ps[(d, nm, stat)][line].append(q[0])
    tg, names, _pos = R.load_games()
    lines = R.load_lines()
    null, wowy, low, wc = [], set(), [], defaultdict(int)
    for c in R.walk(tg, names, lines, wc):
        nm_n = RF.norm(c["nm"])
        wowy.add((c["date"], nm_n))
        for stat, ladder in c["best"].items():
            ml = T._main_line(ladder)
            if ml is None:
                continue
            actual = c["brow"][T.PROP_STATS[stat]]
            null.append({"date": c["date"], "key": (c["date"], nm_n, stat, ml), "price": ladder[ml][0],
                         "won": 1 if actual > ml else 0})
            ll = lowest_line(by_ps, c["date"], nm_n, stat)
            if ll:
                low.append({"date": c["date"], "price": ll[1], "won": 1 if actual > ll[0] else 0,
                            "moved": ll[0] < ml})
    sel, _n, _m, _c = R.collect()
    kept, _dropped = P.select(sel)                    # Arm T = collect() + current_selection
    arm = [dict(r, key=(r["date"], RF.norm(r["player"]), r["stat"], r["line"])) for r in kept]

    for label, rows_, want in (("null (always over, main rung)", null, NULL), ("Arm T selections", arm, ARM_T)):
        print(f"\n{label}:")
        ctl = repriced(rows_, q_all, BOOKS4[:2])
        mism = sum(1 for a, b_ in zip(rows_, ctl) if abs(a["price"] - b_["price"]) > 1e-9)
        roi = R.units(rows_) / len(rows_) * 100
        good = (len(ctl) == len(rows_) == want[0] and mism == 0
                and abs((R.units(rows_) if want is ARM_T else roi) - want[1]) < 0.005)
        print(f"  CONTROL best FD+DK re-priced from the 4-book table: n={len(ctl)} (harness {len(rows_)}, "
              f"registered {want[0]}), price mismatches {mism} -> {'REPRODUCED' if good else 'NOT REPRODUCED'}")
        if not good:
            print("  the harness changed; nothing in P2 is concluded")
            continue
        cut("  best FD+DK (control)", ctl)
        cut("  FanDuel only", repriced(rows_, q_all, ("fanduel",)))
        cut("  DraftKings only", repriced(rows_, q_all, ("draftkings",)))
        cut("  best of four", repriced(rows_, q_all, BOOKS4))
        sub = [r for r in rows_ if over_price(q_all, r["key"], BOOKS4) is not None]
        both = [r for r in sub if over_price(q_all, r["key"], ("fanduel",)) is not None
                and over_price(q_all, r["key"], ("draftkings",)) is not None]
        print(f"  on the {len(both)} with both FD and DK at the line:")
        cut("    FanDuel only", repriced(both, q_all, ("fanduel",)))
        cut("    DraftKings only", repriced(both, q_all, ("draftkings",)))
        cut("    best FD+DK", repriced(both, q_all, BOOKS4[:2]))
        cut("    best of four", repriced(both, q_all, BOOKS4))
    print("\nline shopping (null universe):")
    cut("  main rung, best of four", repriced(null, q_all, BOOKS4))
    cut("  lowest line any book posts", low)
    cut("    of which a lower line than the main rung", [r for r in low if r["moved"]])

    print("\nP1 restricted to WOWY-tier candidates (injury spots):")
    cut("  P1 bets, WOWY tier", [r for r in bets if (r["date"], r["player"]) in wowy])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    main()
