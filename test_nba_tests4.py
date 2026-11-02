"""NBA_TESTS4_PREREG.md: the pieces of the four tests that do arithmetic (no network). MUTANTS in test_mutants()."""
import importlib
import math
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_tests4 as T


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")

    mu, r = 1.3, 4.0                                      # NB(mean 1.3, r 4): P(X <= 1) by hand
    p = r / (r + mu)
    want(abs(mod.nb_pmf_cdf(1, mu, r) - (p ** r * (1 + r * (1 - p)))) < 1e-12, "negative binomial P(X <= 1)")
    pois = math.exp(-1.3) * (1 + 1.3)
    want(abs(mod.nb_pmf_cdf(1, 1.3, 1e6) - pois) < 1e-5, "a huge r is the Poisson")
    want(mod.ts(20, 12, 5) == (20 / (2 * (12 + 2.2)), 14.2), "TS% = pts / (2 x (FGA + 0.44 FTA))")
    want(mod.ts(0, 0, 0) == (None, 0.0), "no attempts: no TS%")
    want(abs(mod.grade(5, 4.5, 1.9) - 0.9) < 1e-12 and mod.grade(4, 4.5, 1.9) == -1.0 and mod.grade(4, 4.0, 1.9) == 0.0, "win, loss, push")
    pairs = [(2.0, x) for x in (0, 1, 2, 3, 4, 2, 1, 2, 3, 2)]
    want(mod.fit_r(pairs) > 50, "under-dispersed counts fit a large r (near Poisson)")
    return ok


def test_tests4():
    assert check(T)


def test_mutants():
    src = pathlib.Path(T.__file__).read_text()
    for tag, a, b in (("NB term", "term *= (i + r) / (i + 1) * (1 - p)", "term *= (i + r) / (i + 2) * (1 - p)"),
                      ("TS% without free throws", "tsa = (fga or 0) + 0.44 * (fta or 0)", "tsa = (fga or 0)"),
                      ("a push loses", "(0.0 if stat == line else -1.0)", "-1.0")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_tests4_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_tests4_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_tests4_mut", None)


if __name__ == "__main__":
    test_tests4()
    test_mutants()
    print("test_nba_tests4: OK")
