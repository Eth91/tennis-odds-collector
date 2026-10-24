"""Amendment 7: the wowy tier computed live from `apps` with the margin test's formulas (team-scoped
split since X's first franchise game; base_min = last-10 mean; d_min shrunk by n_out/(n_out+3);
rate shrunk with 60 pseudo-minutes at B's last-10 rate). Expected values are computed BY HAND below,
independently of the code. Cold's "has a split" = B played >= 2 of X's missed games. MUTANTS."""
import importlib
import pathlib
import sys
import tempfile
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F


def st(pts, reb, ast):
    return {"pts": pts, "reb": reb, "ast": ast, "pra": pts + reb + ast}


def build():
    """X (id 9) plays 30 min in 10 GSW games (days 01-10), misses days 11-12. B (id 1) plays 20 min
    with X (10 pts, 4 reb, 2 ast) and 30 min without (18 pts, 6 reb, 3 ast). B also has 3 BOS games
    AFTER X's first GSW game (days 13-15, X absent) that a team-blind split would count as "without X". C (id 2) never played without X."""
    apps = {9: [(f"2026-01-{d:02d}", 30.0, st(20, 5, 5), "GSW") for d in range(1, 11)],
            1: [(f"2026-01-{d:02d}", 20.0, st(10, 4, 2), "GSW") for d in range(1, 11)]
               + [(f"2026-01-{d:02d}", 30.0, st(18, 6, 3), "GSW") for d in (11, 12)]
               + [(f"2026-01-{d:02d}", 40.0, st(30, 10, 10), "BOS") for d in (13, 14, 15)],
            2: [(f"2026-01-{d:02d}", 25.0, st(12, 5, 1), "GSW") for d in range(1, 11)]}
    return apps


def expected():
    b10 = [20.0] * 8 + [30.0] * 2                      # last 10 GSW games: days 03-12
    base_min = sum(b10) / 10                            # 22.0
    m10 = sum(b10)                                      # 220
    n_out, min_out = 2, 60.0
    d_min = (30.0 - 20.0) * n_out / (n_out + 3.0)       # 4.0
    out = {}
    for stat, with_x, without in (("pts", 10, 18), ("reb", 4, 6), ("pra", 16, 27)):
        base_rate = (8 * with_x + 2 * without) / m10
        rate = (2 * without + base_rate * 60.0) / (min_out + 60.0)
        out[stat] = rate * (base_min + d_min)
    return out


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    apps = build()
    why = Counter()
    c = mod.wowy_live(apps, {9: ("Star", "GSW")}, {1: "GSW", 2: "GSW", 9: "GSW"}, {"GSW": ("G", "t", "m")}, {9}, why)
    got = {(x[3], x[4]): x[5] for x in c}
    exp = expected()
    want(all(abs(got.get((1, s), -1) - v) < 1e-9 for s, v in exp.items()),
         f"B's projections equal the hand-computed margin formula {({s: round(v, 3) for s, v in exp.items()})}")
    want(not any(b == 2 for b, _ in got), "C (never played without X) has no wowy split")
    out, inn = mod.split(apps, 1, 9, "GSW")
    want(len(out) == 2 and len(inn) == 10 and all(a[3] == "GSW" for a in out + inn),
         "split is team-scoped: B's Boston games are ignored")
    apps_short = {k: v[:] for k, v in apps.items()}
    apps_short[9] = apps[9][:9]                         # X has 9 franchise games: not a star here
    want(not mod.wowy_live(apps_short, {9: ("Star", "GSW")}, {1: "GSW", 9: "GSW"}, {"GSW": ("G", "t", "m")}, {9},
                           Counter()), "X with < 10 franchise games is not a trigger")
    return ok


def test_wowy_live():
    assert check(F)


def test_mutants():
    src = pathlib.Path(F.__file__).read_text()
    for name, a, b in (
            ("no d_min shrink", "d_min *= len(b_out) / (len(b_out) + K_DMIN)", "d_min *= 1.0"),
            ("base_rate over all games", "base_rate = sum(a[2][stat] for a in b10) / max(1e-9, m10)",
             "base_rate = sum(a[2][stat] for a in ba) / max(1e-9, sum(a[1] for a in ba))"),
            ("split not team-scoped", "since = [a for a in _team_apps(apps, b_id, tri) if a[0] >= x_first]",
             "since = [a for a in apps.get(b_id, []) if a[0] >= x_first]"),
            ("base_min over all games", "base_min = sum(a[1] for a in b10) / len(b10)",
             "base_min = sum(a[1] for a in ba) / len(ba)"),
            ("no rate shrink", "rate = (sum(a[2][stat] for a in b_out) + base_rate * K_MIN) / (min_out + K_MIN)",
             "rate = sum(a[2][stat] for a in b_out) / min_out")):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_flags_mut7.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({name}) — must fail:")
            assert not check(importlib.import_module("nba_flags_mut7")), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_flags_mut7", None)


if __name__ == "__main__":
    test_wowy_live()
    test_mutants()
    print("test_nba_wowy_live: OK")
