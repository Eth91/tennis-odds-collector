"""NBA_MINUTES_PREREG.md: the minutes study's targets and guards on a small fake league (no network). MUTANTS in
test_mutants()."""
import importlib
import json
import pathlib
import sqlite3
import sys
import tempfile
import zlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_minutes as MIN

X, S2, S6, G4, F5, K, J, Q = 1, 2, 6, 4, 5, 7, 8, 9   # usual five X S2 S6 G4 F5; K and J bench forwards; Q a bench guard
POS = {X: "F-C", S2: "G", S6: "F", G4: "G", F5: "F", K: "F", J: "F-C", Q: "G"}
MINS = {X: 32, S2: 34, S6: 30, G4: 28, F5: 26, K: 14, J: 16, Q: 20}


def stores():
    """2023-24, HOM: G1-G6 the usual five start. G7-G9: K starts for F5 (who sits), J plays 24 then (16 otherwise), Q 20.
    G10-G12 everyone. Tonight G13 (2023-11-13): X does not play; NBA.com's five has K for X. K played 31 that night; on
    the night itself every box value is 99 so a leak shows."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    g = sqlite3.connect(tmp / "g.sqlite")
    g.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fga, fta, fg3a, fg3m, reb, ast, pts)")
    g.execute("CREATE TABLE positions (player_id, player, position)")
    g.executemany("INSERT INTO positions VALUES (?, ?, ?)", [(p, f"P{p}", v) for p, v in POS.items()])
    rows, lineups = [], {}
    usual = (X, S2, S6, G4, F5)
    for i in range(1, 14):
        d, gid = f"2023-11-{i:02d}", f"G{i}"
        five, mins = list(usual), dict(MINS)
        if 7 <= i <= 9:
            five = [X, S2, S6, G4, K]
            mins.update({F5: 0, K: 30, J: 24})
        if i == 13:
            five = [K, S2, S6, G4, F5]
            mins = {p: 99 for p in MINS if p != X}
            mins[K] = 31
        lineups.setdefault(d, []).append(("HOM", five))
        for p, mn in mins.items():
            if mn:
                rows.append(("2023-24", gid, d, "HOM", p, f"P{p}", mn, 10, 2, 3, 1, 5, 3, 12))
    g.executemany("INSERT INTO logs_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    g.commit()
    r = sqlite3.connect(tmp / "r.sqlite")
    r.execute("CREATE TABLE raw (kind TEXT, key TEXT, season TEXT, url TEXT, fetched_at TEXT, status INTEGER, n INTEGER, body BLOB)")
    for d, teams in lineups.items():
        body = {"games": [{"homeTeam": {"teamAbbreviation": t, "players": [{"personId": p, "position": "X"} for p in five] +
                                        [{"personId": 99, "position": ""}]}, "awayTeam": {}} for t, five in teams]}
        r.execute("INSERT INTO raw VALUES ('lineups', ?, '2023-24', '', '', 200, 1, ?)", (d, zlib.compress(json.dumps(body).encode())))
    r.commit()
    return tmp


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")

    tmp = stores()
    five = mod.lineups(tmp / "r.sqlite")
    want(five[("2023-11-13", "HOM")] == frozenset({K, S2, S6, G4, F5}), "the five with a position are the starters")
    rows, pos, five = mod.load(tmp / "g.sqlite", tmp / "r.sqlite")
    s = mod.Season("2023-24", rows, pos, five)
    rs = [r for r in mod.spots(s) if r["date"] == "2023-11-13" and r["know"] == "confirmed"]
    a = next((r for r in rs if r["target"] == "A"), None)
    want(a and a["pid"] == K and a["x"] == X and a["n"] == 1 and a["actual"] == 31, "target A: K, starting for X, played 31")
    want(a and a["n_starts"] == 3 and a["starts_min"] == 30 and abs(a["l5"] - 20.4) < 1e-9,
         "his starts (G7-G9, 30 min) and last 5 (30, 30, 14, 14, 14) from games before tonight only (not tonight's 31)")
    b = next((r for r in rs if r["target"] == "B"), None)
    want(b and b["pid"] == J and b["how"] == "history" and b["with_s_min"] == 24 and b["n_with_s"] == 3,
         "target B: J, whose minutes rose when K started (24 vs 16), not Q")
    if a:
        want(abs(mod.blend(a) - (3 / 6 * 30 + 3 / 6 * a["v3"])) < 1e-9, "blend A: w = 3 / (3 + 3) on his starts, the rest V3")
    return ok


def test_minutes():
    assert check(MIN)


def test_mutants():
    src = pathlib.Path(MIN.__file__).read_text()
    for tag, a, b in (
            ("tonight leaks into his games", 'return rs[:bisect_left([r["date"] for r in rs], date)]',
             'return rs[:bisect_left([r["date"] for r in rs], date + "~")]'),
            ("pickup ignores history", "        if best:\n            return best[1], \"history\", best[2], best[3]\n", ""),
            ("blend all on starts", "w = n / (n + K_BLEND)", "w = 1.0")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_minutes_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_minutes_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_minutes_mut", None)


if __name__ == "__main__":
    test_minutes()
    test_mutants()
    print("test_nba_minutes: OK")
