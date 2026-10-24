"""Amendment 6: logged wowy flags whose split came from another team are voided. (The live team check
itself is now part of the live wowy tier, amendment 7: test_nba_wowy_live.) MUTANT: the void rule
ignoring the team."""
import importlib
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F

def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    pt = {(10, 1): {"BOS"}, (10, 2): {"GSW"}}
    want(mod.amend6_reason("wowy", "GSW", 10, 1, pt) == "amend6: with/without split measured on another team (BOS)",
         "void reason for a logged Horford flag")
    want(mod.amend6_reason("wowy", "GSW", 10, 2, pt) is None, "a same-team flag is not voided")
    want(mod.amend6_reason("priced", "GSW", 10, 1, pt) is None, "priced flags are untouched (live same-team split)")
    want(mod.amend6_reason("wowy", "GSW", 99, 1, pt) is None, "no stored pair at all: nothing to judge, not voided")
    return ok


def test_amend6():
    assert check(F)


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for name, a, b in (("void ignores team", "if not teams or team in teams:", "if not teams:"),):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mut6.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({name}) — must fail:")
            assert not check(importlib.import_module("nba_flags_mut6")), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mut6", None)


if __name__ == "__main__":
    test_amend6()
    test_mutants()
    print("test_nba_amend6: OK")
