"""nba_dk_receive: the GitHub key's forced command accepts only a well-formed, recent DraftKings
snapshot, never steps the file backwards, and writes atomically. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_dk_receive as K

NOW = dt.datetime(2026, 10, 23, 23, 0, 0)
ROW = ["NY Knicks @ BOS Celtics", "Jalen Brunson", "points", 25.5, "over", 1.91]


def snap(at=NOW, rows=None, **kw):
    s = {"book": "dk", "fetched_at": at.isoformat(), "rows": [list(ROW)] if rows is None else rows, "detail": ""}
    s.update(kw)
    return json.dumps(s).encode()


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    out = pathlib.Path(tempfile.mkdtemp()) / "dk_snapshot.json"
    code, msg = mod.receive(snap(NOW - dt.timedelta(seconds=30)), NOW, out)
    want(code == 0 and msg.startswith("ok") and json.loads(out.read_text())["rows"] == [ROW],
         "a recent, well-formed snapshot is written")
    code, msg = mod.receive(snap(NOW - dt.timedelta(seconds=60)), NOW, out)
    want(code == 0 and msg.startswith("kept") and json.loads(out.read_text())["fetched_at"]
         == (NOW - dt.timedelta(seconds=30)).isoformat(), "an OLDER snapshot never replaces a newer one")
    code, msg = mod.receive(snap(NOW - dt.timedelta(seconds=30)), NOW, out)
    want(code == 0 and msg.startswith("kept") and not out.with_name(out.name + ".part").exists(),
         "the same snapshot again: kept, not rewritten; no temp file left")
    bad = (("old", snap(NOW - dt.timedelta(minutes=20))), ("future", snap(NOW + dt.timedelta(minutes=5))),
           ("wrong book", snap(book="fd")), ("not json", b"{nope"), ("tz offset", snap(at=NOW.replace(tzinfo=dt.timezone.utc))),
           ("short row", snap(rows=[ROW[:5]])), ("side", snap(rows=[ROW[:4] + ["sideways", 1.91]])),
           ("odds <= 1", snap(rows=[ROW[:5] + [1.0]])), ("odds NaN", snap(rows=[ROW[:5] + [float("nan")]])),
           ("line not a number", snap(rows=[ROW[:3] + ["25.5"] + ROW[4:]])), ("bool line", snap(rows=[ROW[:3] + [True] + ROW[4:]])),
           ("empty player", snap(rows=[[ROW[0], ""] + ROW[2:]])), ("long event", snap(rows=[["x" * 201] + ROW[1:]])),
           ("too many rows", snap(rows=[list(ROW)] * (mod.MAX_ROWS + 1))), ("too large (valid JSON, padded)", snap(NOW - dt.timedelta(seconds=10)) + b" " * mod.MAX_BYTES),
           ("bad detail", snap(detail=["x"])))
    before = out.read_text()
    for name, raw in bad:
        code, msg = mod.receive(raw, NOW, out)
        want(code == 2 and msg.startswith("refused") and out.read_text() == before, f"refused and untouched: {name}")
    return ok


def test_receiver():
    assert check(K)


def test_mutants():
    src = pathlib.Path(K.__file__).read_text()
    for name, a, b in (
            ("never steps backwards", 'if cur and snap["fetched_at"] <= cur:', 'if cur and snap["fetched_at"] < cur:'),
            ("age bound", "if age > MAX_AGE_S or age < -MAX_AHEAD_S:", "if age < -MAX_AHEAD_S:"),
            ("future bound", "if age > MAX_AGE_S or age < -MAX_AHEAD_S:", "if age > MAX_AGE_S:"),
            ("book check", 'snap.get("book") != "dk"', 'snap.get("book") is None'),
            ("odds range", "and 1.0 < r[5] < 1000", ""),
            ("row width", "len(r) == 6", "len(r) >= 5"),
            ("bool is not a number", "and not isinstance(x, bool)", ""),
            ("size cap", "if len(raw) > MAX_BYTES:", "if False:")):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_dk_receive_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            mut = importlib.import_module("nba_dk_receive_mut")
            print(f"MUTANT ({name}) — must fail:")
            try:
                survived = check(mut)
            except Exception as e:                  # a crash is a caught mutant too
                print(f"   (crashed: {type(e).__name__})")
                survived = False
            assert not survived, name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_dk_receive_mut", None)


if __name__ == "__main__":
    test_receiver()
    test_mutants()
    print("test_nba_dk_receive: OK")
