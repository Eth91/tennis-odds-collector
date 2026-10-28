"""Amendment 34: nba_finals stores new finals and never asks for a live game, on a fake schedule and feed (no
network). MUTANTS in test_mutants()."""
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
    asked = []
    get = lambda g: asked.append(g) or by[g]
    sched = [{"gid": "0022300001", "status": 3}, {"gid": "0022300005", "status": 2}]       # one final, one live
    want(mod.run(con, schedule=lambda: sched, get=get) == (1, 0), "a new final is stored")
    want(asked == ["0022300001"], "a live game is not asked for")
    want(mod.run(con, schedule=lambda: sched, get=get) == (0, 0) and asked == ["0022300001"], "nothing new: nothing asked")
    sched.append({"gid": "0022300002", "status": 3})
    want(mod.run(con, schedule=lambda: sched, get=get) == (1, 0), "the next final is stored")
    want(con.execute("SELECT COUNT(*) FROM playtypes").fetchone()[0] == 0, "no play-type snapshot")
    return ok


def test_finals():
    assert check(F)


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for tag, a, b in (("live games asked for", 'if g["status"] == 3]', "]"),):
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
