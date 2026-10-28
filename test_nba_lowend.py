"""NBA_LOWEND_PREREG.md: the low end and its similar-volume percentages (no network). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_lowend as LO


def games():
    """Six games at 6 FGA (4 two-point tries, 2 made), six at 14 FGA (12 two-point tries, 8 made), both with 2 3PA and 4
    FTA; six at 10 FGA with 9 3PA (1 two-point try, made) and no free throws."""
    low = [{"fga": 6, "fgm": 3, "fg3a": 2, "fg3m": 1, "fta": 4, "ftm": 3} for _ in range(6)]
    high = [{"fga": 14, "fgm": 8, "fg3a": 2, "fg3m": 0, "fta": 4, "ftm": 4} for _ in range(6)]
    return low + high + [{"fga": 10, "fgm": 4, "fg3a": 9, "fg3m": 3, "fta": 0, "ftm": 0} for _ in range(6)]


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")

    g = games()
    err = {"min": 5.0, "fga": 3.0, "fg3a": 1.0, "fta": 1.5, "reb": 2.0, "ast": 1.0}
    lo0 = mod.low_end(g, {"fga": 10.0, "fg3a": 3.0, "fta": 4.0, "reb": 6.0, "ast": 3.0}, 30.0, {"reb": 0.2, "ast": 0.1}, err, 1.0)
    p2_want = (6 * 2 + 6 * 1) / (6 * 4 + 6 * 1)          # FGA within 3 of 7: the 6- and 10-FGA games, not the 14s
    p3_want = (6 * 1 + 6 * 0) / (6 * 2 + 6 * 2)          # 3PA within 1 of 2: the 2-3PA games, not the 9s
    ft_want = mod.pct(g, 2.5, 1.5, lambda r: r["fta"], lambda r: r["ftm"], "ft")
    want(abs(lo0["points"] - (2 * 5 * p2_want + 3 * 2 * p3_want + 2.5 * ft_want)) < 1e-9,
         "2P% from games of similar FGA (6 and 10, not the 14s), 3P% from games of similar 3PA")
    want(mod.pct(g[:4], 4.0, 3.0, lambda r: r["fga"] - r["fg3a"], lambda r: r["fgm"] - r["fg3m"], "p2") == 8 / 16,
         "under 5 similar games: his overall percentage")
    want(mod.pct(g, 7.0, 3.0, lambda r: r["fga"] - r["fg3a"], lambda r: r["fgm"] - r["fg3m"], "p2", vol=lambda r: r["fga"]) == 18 / 30,
         "the window is on volume (FGA), the percentage on two-point tries")
    want(mod.pct([], 4.0, 3.0, lambda r: 0, lambda r: 0, "ft") == 0.78, "no attempts at all: the league's")
    vol = {"fga": 10.0, "fg3a": 3.0, "fta": 4.0, "reb": 6.0, "ast": 3.0}
    rt = {"reb": 0.2, "ast": 0.1}
    lo = mod.low_end(g, vol, 30.0, rt, err, 1.0)
    want(lo["_fga"] == 7.0 and lo["_fg3a"] == 2.0 and lo["_fta"] == 2.5, "k = 1: FGA 10-3, 3PA 3-1, FTA 4-1.5")
    want(abs(lo["points"] - lo0["points"]) < 1e-9, "points = 2 x 2PA x 2P% + 3 x 3PA x 3P% + FTA x FT%")
    want(abs(lo["pra"] - (lo["points"] + 25 * 0.2 + 25 * 0.1)) < 1e-9, "rebounds and assists at (minutes - 5) x his rates")
    lo_half = mod.low_end(g, vol, 30.0, rt, err, 0.5)
    want(lo_half["_fga"] == 8.5 and lo_half["points"] > lo["points"], "k = 0.5: half the error off")
    return ok


def test_lowend():
    assert check(LO)


def test_mutants():
    src = pathlib.Path(LO.__file__).read_text()
    for tag, a, b in (
            ("all games, not similar volume", "near = [r for r in games if abs(vol(r) - lo) <= err]", "near = list(games)"),
            ("2P% windowed on two-point tries", '"p2", vol=lambda r: r["fga"] or 0)', '"p2")'),
            ("full projection, not the low end", "fga = max(0.0, vol[\"fga\"] - k * err[\"fga\"])", "fga = vol[\"fga\"]"),
            ("minutes not lowered for boards", "m_lo = max(0.0, minutes - k * err[\"min\"])", "m_lo = minutes")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_lowend_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_lowend_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_lowend_mut", None)


if __name__ == "__main__":
    test_lowend()
    test_mutants()
    print("test_nba_lowend: OK")
