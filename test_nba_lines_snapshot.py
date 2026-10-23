"""nba_lines: DraftKings arrives on the VM as a pushed snapshot (NBA_SPEED_PREREG.md amendment 4).
Its rows keep the snapshot's own fetch time; a re-sent or OLDER snapshot is not ingested; a stale
one is logged and is not a failure. MUTANTS for each are checked in test_mutants()."""
import datetime as dt
import importlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_lines as L

EVENT = "New York Knicks @ Boston Celtics"


def _iso(minutes_ago):
    t = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    return (t - dt.timedelta(minutes=minutes_ago)).isoformat()


def setup(mod):
    d = pathlib.Path(tempfile.mkdtemp())
    mod.DB = d / "l.sqlite"
    game = {"status": 1, "utc": "2099-01-01T00:00:00Z", "gid": "G1", "home": "BOS", "away": "NYK",
            "home_nick": "Celtics", "away_nick": "Knicks"}
    mod.R.schedule = lambda: [game]
    mod.R.season_boxes = lambda sched: ({}, None)
    mod.R.player_index = lambda day: ({}, "")
    mod.R.state = lambda day, boxes, index=None: ({}, {}, {})

    class Resolver:
        def __init__(self, *a):
            pass

        def __call__(self, player, home, away):
            return 7
    mod.Resolver = Resolver
    mod.DK_SNAPSHOT = str(d / "dk.json")
    mod.BOOKS["dk"] = mod.fetch_dk_snapshot
    return d


def push(d, at, over, under=1.91):
    rows = [(EVENT, "Jalen Brunson", "points", 25.5, "over", over),
            (EVENT, "Jalen Brunson", "points", 25.5, "under", under)]
    (d / "dk.json").write_text(json.dumps({"book": "dk", "fetched_at": at, "rows": rows, "detail": ""}))


def db(mod):
    return sqlite3.connect(mod.DB)


def check(mod):
    saved = {k: getattr(mod.R, k) for k in ("schedule", "season_boxes", "player_index", "state")}
    try:
        return _check(mod)
    finally:                                   # nba_rosters is shared: never leak the stubs
        for k, v in saved.items():
            setattr(mod.R, k, v)


def _check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    d = setup(mod)
    t1, t0, t2 = _iso(2), _iso(4), _iso(1)
    push(d, t1, 1.91)
    want(mod.cycle(("dk",)) == [], "a fresh snapshot ingests without failure")
    c = db(mod)
    want(c.execute("SELECT DISTINCT collected_at FROM board WHERE book='dk'").fetchall() == [(t1,)],
         "board rows carry the snapshot's fetch time, not the ingest time")
    want(c.execute("SELECT COUNT(*), MIN(seen_at) FROM quotes").fetchone() == (2, t1),
         "change log: 2 first-seen quotes dated to the fetch time")
    mod.cycle(("dk",))
    want(db(mod).execute("SELECT COUNT(*) FROM quotes").fetchone()[0] == 2, "the same snapshot again adds nothing")
    push(d, t2, 1.80, 2.02)
    mod.cycle(("dk",))
    c = db(mod)
    want(c.execute("SELECT seen_at, odds FROM quotes WHERE side='over' ORDER BY seen_at").fetchall()
         == [(t1, 1.91), (t2, 1.80)], "a newer snapshot logs the price move at ITS fetch time")
    push(d, t0, 2.50, 1.50)                                      # an OLDER snapshot arrives late
    mod.cycle(("dk",))
    want(db(mod).execute("SELECT odds FROM board WHERE side='over'").fetchone()[0] == 1.80,
         "an older snapshot never overwrites a newer board")
    push(d, _iso(30), 1.70)                                      # sender asleep 30 min
    want(mod.cycle(("dk",)) == [], "a stale snapshot is NOT a failure")
    c = db(mod)
    want(c.execute("SELECT status FROM cycles ORDER BY rowid DESC LIMIT 1").fetchone()[0] == "stale",
         "a stale snapshot is logged as stale")
    want(c.execute("SELECT odds FROM board WHERE side='over'").fetchone()[0] == 1.80,
         "a stale snapshot leaves the board untouched")
    (d / "dk.json").unlink()
    want(mod.cycle(("dk",)) == [] and db(mod).execute(
        "SELECT status FROM cycles ORDER BY rowid DESC LIMIT 1").fetchone()[0] == "stale",
         "no snapshot at all = stale, not a failure")
    return ok


def test_snapshot_ingest():
    assert check(importlib.reload(L))


def test_default_books_from_env():
    os.environ["NBA_BOOKS"] = "fd"
    try:
        assert importlib.reload(L).DEFAULT_BOOKS == ("fd",)
    finally:
        del os.environ["NBA_BOOKS"]
    assert importlib.reload(L).DEFAULT_BOOKS == ("fd", "dk")


def test_mutants():
    src = pathlib.Path(L.__file__).read_text()
    for name, a, b in (
            ("snapshot time ignored", 'bts = got[2] if len(got) > 2 else ts', 'bts = ts'),
            ("older snapshot accepted", 'if bts != ts and last and bts <= last:', 'if bts != ts and last and bts == last:'),
            ("stale counted as failure", 'report.append(f"{book}=stale ({e}) — board left untouched")\n            continue',
             'report.append(f"{book}=stale ({e}) — board left untouched")\n            failed.append(book)\n            continue')):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_lines_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            mut = importlib.import_module("nba_lines_mut")
            print(f"MUTANT ({name}) — must fail:")
            assert not check(mut), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_lines_mut", None)


if __name__ == "__main__":
    test_snapshot_ingest()
    test_default_books_from_env()
    test_mutants()
    print("test_nba_lines_snapshot: OK")
