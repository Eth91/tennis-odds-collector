"""nba_research_score: the replay grades only what was knowable before tip — the board as of the last change before
tip (carried forward through the change log), history strictly before the game — and voids DNPs and pushes.
MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_matchup as MU
import nba_research as R
import nba_research_score as SC

GID, DATE, TIP = "0022600013", "2026-10-22", "2026-10-23T00:00:00Z"


def stores():
    d = pathlib.Path(tempfile.mkdtemp())
    q = sqlite3.connect(d / "l.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    rows = [("2026-10-22T15:00:00", "fd", 1, 20.5, "over", 1.9), ("2026-10-22T15:00:00", "fd", 1, 20.5, "under", 1.9),
            ("2026-10-22T15:00:00", "dk", 1, 20.5, "over", 1.95), ("2026-10-22T15:00:00", "dk", 1, 20.5, "under", 1.85),
            ("2026-10-22T20:00:00", "fd", 1, 20.5, "over", 1.8),          # a change: only the over is written
            ("2026-10-23T01:00:00", "fd", 1, 20.5, "over", 3.0),          # after tip: must not count
            ("2026-10-22T15:00:00", "fd", 2, 9.5, "over", 1.9), ("2026-10-22T15:00:00", "fd", 2, 9.5, "under", 1.9),   # DNP
            ("2026-10-22T15:00:00", "fd", 3, 10.0, "over", 1.9), ("2026-10-22T15:00:00", "fd", 3, 10.0, "under", 1.9)]  # push
    q.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,'',?,?,?,?)",
                  [(t, b, GID, TIP, pid, "points", ln, sd, o) for t, b, pid, ln, sd, o in rows])
    q.commit(); q.close()
    n = sqlite3.connect(d / "n.sqlite")
    n.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT, pid INTEGER, "
              "player TEXT, status TEXT, reason TEXT)")
    n.commit(); n.close()
    m = MU.connect(d / "m.sqlite")
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) " \
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    for i in range(10):                                   # ten earlier games: 18 points each, all unders of 20.5
        g = f"00226000{i:02d}"
        m.execute("INSERT INTO games VALUES (?,?,?,?,?,?,?)", (g, "2026-27", f"2026-10-{i + 1:02d}", "PHX", "UTA", 100, 90))
        m.execute(PG, (g, "PHX", 1, "SG", 1, 30, 18, 3, 3, 1, 0, 0, 2, 15, 5, 3))
    m.execute("INSERT INTO games VALUES (?,?,?,?,?,?,?)", (GID, "2026-27", DATE, "PHX", "UTA", 110, 100))
    m.execute(PG, (GID, "PHX", 1, "SG", 1, 34, 25, 3, 3, 1, 0, 0, 2, 18, 6, 4))         # tonight: 25, an over
    m.execute(PG, (GID, "PHX", 3, "C", 1, 28, 10, 9, 1, 0, 0, 1, 1, 8, 0, 2))           # exactly 10: a push
    m.commit(); m.close()
    return d


def check(mod):
    d = stores()
    recs = mod.grade(lines=d / "l.sqlite", matchup=d / "m.sqlite", news=d / "n.sqlite", season="2026-27")
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    want([r["pid"] for r in recs] == [1], "one gradable prop: the DNP and the push are void")
    if not recs:
        return False
    r = recs[0]
    fair = (R.no_vig(1.8, 1.9) + R.no_vig(1.95, 1.85)) / 2
    want(r["fair"] == pytest.approx(fair), "close = the board carried forward to the last change before tip")
    want(r["over"] is True and r["line"] == 20.5, "graded at FanDuel's main rung")
    want(r["l10"] == (0, 10), "history strictly before the game: ten unders, not tonight's over")
    want(r["move"] == 0, "no line move")
    s = mod.score([(r, "under")], "x", "y")
    want(s["wins"] == 0 and s["roi"] == -1 and s["implied"] == pytest.approx(1 - fair, abs=1e-4), "a losing pick costs the stake")
    s = mod.score([(r, "over")], "x", "y")
    want(s["roi"] == pytest.approx(1.95 - 1, abs=1e-4) and s["verdict"] == "too few picks", "paid at the best closing price")
    return ok


def test_grade_and_score():
    assert check(SC)


def test_scorecard_shape():
    d = stores()
    sc = SC.scorecard(SC.grade(lines=d / "l.sqlite", matchup=d / "m.sqlite", news=d / "n.sqlite", season="2026-27"))
    assert sc["props"] == 1 and sc["nights"] == 1 and sc["from"] == DATE
    names = [s["signal"] for s in sc["signals"]]
    assert "Colored L10 box" in names and "DvP (blended, as shown)" in names and "Value > 0" in names
    assert set(sc["brier"]) == {"price (no-vig)", "L10 hit rate", "coin flip"}


def test_mutants():
    src = pathlib.Path(SC.__file__).read_text()
    for tag, a, b in (("prices after tip leak in", "            if not tip or t >= tip:\n", "            if not tip:\n"),
                      ("tonight's box in his history", 'for r in logs.get(pid, []) if r[0] < date]',
                       'for r in logs.get(pid, []) if r[0] <= date]')):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_research_score_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_research_score_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_research_score_mut", None)
