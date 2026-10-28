"""Amendment 34: nba_finals stores new finals (not live games) and rebuilds the pages only when it stored one, on
a fake schedule and feed (no network). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_finals as F
import nba_matchup as MU
from test_nba_matchup import BOXES, scored


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    con = MU.connect(pathlib.Path(tempfile.mkdtemp()) / "m.sqlite")
    by = {b["gameId"]: scored(b) for b in BOXES}
    asked, built = [], []
    get = lambda g: asked.append(g) or by[g]
    builder = lambda name, args: built.append(name) or (2 if name == "vs" else 0)
    sched = [{"gid": "0022300001", "status": 3}, {"gid": "0022300005", "status": 2}]       # one final, one live
    res = mod.run(con, schedule=lambda: sched, get=get, builder=builder)
    want(res == (1, 0, [("boxscore", 0), ("vs", 2), ("players", 0)]), f"a new final: stored, pages rebuilt in order {res}")
    want(asked == ["0022300001"], "a live game is not asked for")
    built.clear()
    res = mod.run(con, schedule=lambda: sched, get=get, builder=builder)
    want(res == (0, 0, []) and built == [], "nothing new: no page rebuilt")
    sched.append({"gid": "0022300002", "status": 3})
    res = mod.run(con, schedule=lambda: sched, get=get, builder=builder)
    want(res[0] == 1 and built == ["boxscore", "vs", "players"], "the next final: rebuilt again")
    want(all(a[0].endswith(".py") for _n, a in mod.PAGES) and [n for n, _a in mod.PAGES] == ["boxscore", "vs", "players"],
         "the daily builders, in their daily order")
    return ok


def test_finals():
    assert check(F)


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for tag, a, b in (("always rebuilds", " if stored else []", " if True else []"),
                      ("never rebuilds", " if stored else []", " if False else []"),
                      ("live games asked for", 'if g["status"] == 3]', "]")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_finals_mut34.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_finals_mut34")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_finals_mut34", None)


if __name__ == "__main__":
    test_finals()
    test_mutants()
    print("test_nba_finals: OK")
