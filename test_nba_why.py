"""NBA_WHY_PREREG.md: the filter search's rules (2 conditions max, different rows, coverage, every-date selection,
conflicting sides skipped). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_why as W

DATES = ("d1", "d2", "d3")


def recs():
    """80 props: 'home=home' unders always win (planted); 'b2b=yes' unders win on every date but cover 3 of 80 (< 5%)."""
    rng = np.random.default_rng(1)
    out = []
    for i in range(80):
        home = i % 2 == 0
        win_under = home or i in (0, 1, 2) or rng.random() < 0.5
        out.append({"date": DATES[i % 3], "market": "points",
                    "b": {"home": "home" if home else "away", "b2b": "yes" if i in (0, 1, 2) else "no",
                          "role": ("bench", "mid", "starter30")[i % 3]},
                    "price": {"over": "mid", "under": "mid"},
                    "profit": {"over": -1.0 if win_under else 0.9, "under": 0.9 if win_under else -1.0},
                    "odds": {"over": 1.9, "under": 1.9}, "clv": {"over": -0.05, "under": 0.02}})
    return out


def check(mod=W):
    r = recs()
    conds = mod.conditions(r)
    fl = mod.filters(conds)
    ok = all(len(ks) <= 2 and (len(ks) == 1 or ks[0][0] != ks[1][0]) for _sd, ks in fl)
    prof = {sd: np.array([x["profit"][sd] for x in r]) for sd in ("over", "under")}
    every = np.ones(len(r), bool)
    sel = mod.select(r, conds, fl, every, prof)
    ok &= ("under", (("home", "home"),)) in sel
    ok &= not any(("b2b", "yes") in ks for _sd, ks in sel)                 # 3 of 80 props: under 5% coverage
    ok &= all(sd == "under" or ("home", "home") not in ks for sd, ks in sel)
    b = mod.bets(r, conds, [("under", (("home", "home"),)), ("over", (("home", "home"),))], every)
    ok &= b == []                                                          # both sides on the same props: skipped
    return bool(ok)


def test_search_rules():
    assert check()


def test_mutants():
    src = pathlib.Path(W.__file__).read_text()
    for tag, a, b in (("3-condition filters", "pairs = [(a, b) for a, b in itertools.combinations(keys, 2) if a[0] != b[0]]",
                       "pairs = [(a, b) for a, b in itertools.combinations(keys, 2)]"),
                      ("no coverage floor", "        if n < COVER * n_all:\n            continue\n", ""),
                      ("conflicts kept", "    both = side[\"over\"] & side[\"under\"]\n", "    both = side[\"over\"] & False\n")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_why_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            assert not check(importlib.import_module("nba_why_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_why_mut", None)
