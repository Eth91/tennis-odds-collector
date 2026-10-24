"""Amendment 6: a wowy split must be measured on the beneficiary's CURRENT team; the cold tier's
"has a prior split" means a split on this team; logged flags are voided by the same rule.
MUTANTS: the team check removed; the void rule ignoring the team."""
import importlib
import pathlib
import sys
import tempfile
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F

PAIRS = [  # x_id, b_id, b_name, n_out, d_min, rate_pts, rate_reb, rate_pra, team
    (10, 1, "Horford", 2, 0.0, 0.42, 0.27, 0.79, "BOS"),     # split from Boston; both now GSW
    (10, 2, "Podz", 9, 3.0, 0.50, 0.20, 0.90, "GSW"),        # split measured at GSW
    (20, 3, "Twice", 6, 2.0, 0.40, 0.20, 0.70, "BOS"),       # same pair measured on two teams:
    (20, 3, "Twice", 4, 1.0, 0.45, 0.25, 0.80, "PHX"),       #   only the current team's counts
]
OUT = {10: ("Porzingis", "GSW"), 20: ("Star", "PHX")}
CUR = {1: "GSW", 2: "GSW", 3: "PHX"}
GAMES = {"GSW": ("G1", "t", "MEM @ GSW"), "PHX": ("G2", "t", "PHX @ LAL")}
BASE = {1: 24.0, 2: 28.0, 3: 30.0}


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    why = Counter()
    c = mod.wowy_candidates(PAIRS, OUT, CUR, GAMES, set(), BASE, why)
    bs = {(x[3], round(x[5], 3)) for x in c}
    want(not any(b == 1 for b, _ in bs) and why["wowy_split_other_team"] >= 1,
         "Horford's Boston split does not flag him at Golden State")
    want(any(b == 2 for b, _ in bs), "a split measured at the current team still flags")
    want({p for b, p in bs if b == 3} == {round(0.45 * 31.0, 3), round(0.25 * 31.0, 3), round(0.80 * 31.0, 3)},
         "a pair measured on two teams uses only the current team's split")
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
    for name, a, b in (("team check removed", "        if p_team != tri:\n", "        if False:\n"),
                       ("void ignores team", "if not teams or team in teams:", "if not teams:")):
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
