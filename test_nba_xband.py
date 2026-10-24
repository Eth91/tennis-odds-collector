"""Amendment 16: wowy qualifies an absent X at 24+ minutes (priced and cold stay at 28), and wowy flags
with X under 28 score in their own `x24-28` cell. MUTANTS in test_mutants()."""
import contextlib
import importlib
import io
import pathlib
import sys
import tempfile
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_clv as V
import nba_flags as F
from test_nba_wowy_live import st


def apps_at(xmin):
    return {9: [(f"2026-01-{d:02d}", xmin, st(20, 5, 5), "GSW") for d in range(1, 11)],
            1: [(f"2026-01-{d:02d}", 20.0, st(10, 4, 2), "GSW") for d in range(1, 11)]
               + [(f"2026-01-{d:02d}", 30.0, st(18, 6, 3), "GSW") for d in (11, 12)]}


def qualifies(mod, xmin):
    why = Counter()
    c = mod.wowy_live(apps_at(xmin), {9: ("X", "GSW")}, {1: "GSW", 9: "GSW"}, {"GSW": ("G", "t", "m")}, {9}, why)
    return bool(c)


def cell_counts(v, rows):
    v.VOIDED = 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        v.scoreboard(rows)
    return {ln.split()[0]: int(ln.split()[2]) for ln in buf.getvalue().splitlines()
            if ln.startswith("wowy/") and ln.split()[1] == "FD"}


def row(x_min, x_status=None):
    return {"tier": "wowy", "gid": "G", "horizon": 0, "confirmed": None, "x_status": x_status, "x_min": x_min,
            "fd_flag": (10.5, 1.91), "fd_close": (11.5, 1.91), "fd_beat": True, "fd_move": 1.0}


def check(fmod, vmod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    want(qualifies(fmod, 25.0) and qualifies(fmod, 30.0) and not qualifies(fmod, 23.0),
         "wowy: X at 25 and 30 min qualifies, 23 does not")
    c = cell_counts(vmod, [row(None), row(30.0), row(27.7), row(24.3, "Doubtful")])
    want(c == {"wowy/h0": 2, "wowy/x24-28": 1, "wowy/doubtful": 1},
         f"cells: pre-cutover + 28+ in h0, 27.7 in x24-28, Doubtful wins over the band ({c})")
    return ok


def test_band():
    assert check(F, V)


def test_priced_and_cold_keep_28():
    src = pathlib.Path(F.__file__).read_text()
    assert F.STAR_MIN == 28.0 and F.WOWY_STAR_MIN == 24.0
    assert 'why["x_not_a_star_here"]' in src and 'why["priced_x_not_a_star_here"]' in src
    assert src.count("_mean_last10(xa) < STAR_MIN") == 2          # cold + priced
    assert src.count("_mean_last10(xa) < WOWY_STAR_MIN") == 1     # wowy


def test_mutants():
    for mod, tag, a, b in (
            (F, "wowy bar not lowered", "_mean_last10(xa) < WOWY_STAR_MIN", "_mean_last10(xa) < STAR_MIN"),
            (V, "no x24-28 cell", '                else "x24-28" if r.get("x_min") is not None and r["x_min"] < 28\n', "")):
        src = pathlib.Path(mod.__file__).read_text()
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        name = f"{pathlib.Path(mod.__file__).stem}_mut16"
        (d / f"{name}.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            m = importlib.import_module(name)
            assert not check(m if mod is F else F, m if mod is V else V), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop(name, None)


if __name__ == "__main__":
    test_band(); test_priced_and_cold_keep_28(); test_mutants()
    print("test_nba_xband: OK")
