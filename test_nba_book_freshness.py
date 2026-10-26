"""nba_flags: a snapshot-fed DraftKings board (the VM, amendment 4) counts only while it is <= 12 min
old; a locally collected book keeps the 90-min window. MUTANT: the per-book limit ignored."""
import datetime as dt
import importlib
import os
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

NOW = dt.datetime(2026, 1, 9, 20, 0, tzinfo=dt.timezone.utc)


def board(path, ages):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE board (book TEXT, collected_at TEXT, gid TEXT, tip_utc TEXT, event TEXT, "
              "home TEXT, away TEXT, pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    for book, mins in ages.items():
        at = (NOW - dt.timedelta(minutes=mins)).replace(tzinfo=None).isoformat()
        over = 1.95 if book == "dk" else 1.87                  # DK's over is the better price
        for side, o in (("over", over), ("under", 1.91)):
            c.execute("INSERT INTO board VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (book, at, "G", "", "", "", "", 7, "p", "points", 20.5, side, o))
    c.commit()


def run(mod_name, snapshot, ages):
    if snapshot:
        os.environ["NBA_DK_SNAPSHOT"] = "/tmp/x.json"
    else:
        os.environ.pop("NBA_DK_SNAPSHOT", None)
    try:
        F = importlib.reload(importlib.import_module(mod_name))
    finally:
        os.environ.pop("NBA_DK_SNAPSHOT", None)
    d = pathlib.Path(tempfile.mkdtemp())
    board(d / "l.sqlite", ages)
    F.LINES_DB = d / "l.sqlite"
    lines, status = F.latest_lines(NOW)
    ladders = F.board_ladders(NOW)
    return lines.get(("G", 7, "points")), status, ladders.get(("G", 7), {}).get("points", {}).get(20.5)


def check(mod_name):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    ln, st, lad = run(mod_name, True, {"fd": 30, "dk": 30})
    want(ln and ln[1] == 1.87 and "dk" in st and lad == (1.87, 1.91),
         "snapshot-fed DK 30 min old is excluded (flag price and ladder are FanDuel's)")
    ln, st, lad = run(mod_name, True, {"fd": 30, "dk": 5})
    want(ln and ln[1] == 1.95 and lad == (1.95, 1.91), "snapshot-fed DK 5 min old is used")
    ln, st, lad = run(mod_name, False, {"fd": 30, "dk": 30})
    want(ln and ln[1] == 1.95 and st == "ok", "a locally collected DK keeps the 90-min window")
    ln, st, lad = run(mod_name, True, {"fd": 100, "dk": 5})
    want(ln and ln[1] == 1.95 and "fd" in st, "FanDuel past 90 min is excluded as before")
    importlib.reload(importlib.import_module(mod_name))     # leave the shared module as found
    return ok


def test_book_freshness():
    assert check("nba_flags")


def test_mutant_per_book_limit_ignored():
    here = pathlib.Path(__file__).resolve().parent
    src = (here / "nba_flags.py").read_text()
    a = "minutes=BOOK_MAX_AGE_MIN.get(b, LINE_MAX_AGE_MIN)"
    assert src.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_flags_mut.py").write_text(src.replace(a, "minutes=LINE_MAX_AGE_MIN"))
    sys.path.insert(0, str(d))
    try:
        print("MUTANT (per-book limit ignored) — must fail:")
        assert not check("nba_flags_mut")
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("nba_flags_mut", None)


def check_by_game(F):
    """A back-to-back player has rungs on the board for two games: each game sees only its own."""
    d = pathlib.Path(tempfile.mkdtemp())
    c = sqlite3.connect(d / "l.sqlite")
    c.execute("CREATE TABLE board (book TEXT, collected_at TEXT, gid TEXT, tip_utc TEXT, event TEXT, "
              "home TEXT, away TEXT, pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    at = (NOW - dt.timedelta(minutes=5)).replace(tzinfo=None).isoformat()
    for gid, line in (("SAT", 13.5), ("SUN", 14.5)):
        for side in ("over", "under"):
            c.execute("INSERT INTO board VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      ("fd", at, gid, "", "", "", "", 7, "p", "points", line, side, 1.91))
    c.commit()
    F.LINES_DB = d / "l.sqlite"
    lines, _ = F.latest_lines(NOW)
    lad = F.board_ladders(NOW)
    return (lines.get(("SAT", 7, "points"), (None,))[0] == 13.5 and lines.get(("SUN", 7, "points"), (None,))[0] == 14.5
            and list(lad[("SUN", 7)]["points"]) == [14.5])


def test_lines_by_game():
    import nba_flags as F
    saved = F.LINES_DB
    try:
        assert check_by_game(F)
    finally:
        F.LINES_DB = saved


def test_mutants_by_game():
    here = pathlib.Path(__file__).resolve().parent
    src = (here / "nba_flags.py").read_text()
    for tag, a, b in (("lines keyed without the game", "two.setdefault((gid, pid, stat, line), {})",
                       "two.setdefault((\"G\", pid, stat, line), {})"),
                      ("ladders keyed without the game", "k = (gid, pid, stat, round(float(line), 1))",
                       "k = (\"G\", pid, stat, round(float(line), 1))")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mutg.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            try:
                survived = check_by_game(importlib.import_module("nba_flags_mutg"))
            except (KeyError, TypeError):
                survived = False
            assert not survived, tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mutg", None)


if __name__ == "__main__":
    test_book_freshness()
    test_mutant_per_book_limit_ignored()
    print("test_nba_book_freshness: OK")
