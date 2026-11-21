"""nhl_stats: rest days (a back-to-back is 0), each player-game's margin from his team's side, his share of the team's
shots and power-play time, the date windows. MUTANTS in test_mutants()."""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nhl_stats as S

COL = {c: i + 3 for i, c in enumerate(S.LOG_COLS)}


def sched():
    g = lambda gid, d, a, h, asc, hsc, state="final": {"gid": gid, "date": d, "away": a, "home": h, "away_score": asc,
                                                      "home_score": hsc, "state": state}
    return [g("1", "2026-10-10", "EDM", "NYR", 2, 5), g("2", "2026-10-11", "EDM", "BOS", 4, 1),
            g("3", "2026-10-12", "NYR", "BOS", None, None, "postponed"), g("4", "2026-10-14", "BOS", "EDM", 3, 3)]


def P():
    sk = lambda team, opp, home, shots, pp, pos="C": {"team": team, "opp": opp, "home": home, "pos": pos, "shots": shots,
                                                     "pp_min": pp, "min": 18.0, "goals": 0}
    return {("1", 10): sk("EDM", "NYR", 0, 3, 2.0), ("1", 11): sk("EDM", "NYR", 0, 1, 0.0, "D"),
            ("1", 12): dict(sk("EDM", "NYR", 0, None, None, "G"), saves=30), ("1", 20): sk("NYR", "EDM", 1, 6, 0.5),
            ("2", 10): sk("EDM", "BOS", 0, 2, 1.0)}


def T():
    return {("1", "EDM"): {"pp_sec": 240}, ("1", "NYR"): {"pp_sec": 0}, ("2", "EDM"): {"pp_sec": 30}}


def check(M):
    rest = M.rest_days(sched())
    rows = {(r[COL["gid"]], r[1]): r for r in M.log_rows(2026, P(), T(), sched())}
    a, d, g, n, b = rows[("1", 10)], rows[("1", 11)], rows[("1", 12)], rows[("1", 20)], rows[("2", 10)]
    ok = rest[("1", "EDM")] is None and rest[("2", "EDM")] == 0 and rest[("4", "BOS")] == 2 and ("3", "NYR") not in rest
    ok &= a[COL["margin"]] == -3 and n[COL["margin"]] == 3 and b[COL["margin"]] == 3 and b[COL["rest"]] == 0
    ok &= a[COL["shot_share"]] == 75.0 and d[COL["shot_share"]] == 25.0 and g[COL["shot_share"]] is None
    ok &= a[COL["pp_share"]] == 50.0 and n[COL["pp_share"]] == 0.0 and b[COL["pp_share"]] == 100.0   # 60 s of a 30 s power play: capped
    return bool(ok)


def test_logs():
    assert check(S)


def test_spans():
    sp = S.spans("2026-10-01", "2026-10-31")
    assert sp[0][0] == "2026-10-01" and sp[-1][1] > "2026-10-31" and all(a < b for a, b in sp)
    assert all(sp[i][1] == sp[i + 1][0] for i in range(len(sp) - 1))


def _mutant(name, old, new):
    src = pathlib.Path(S.__file__).read_text()
    assert src.count(old) == 1, (name, old)
    f = pathlib.Path(tempfile.mkdtemp()) / f"{name}.py"
    f.write_text(src.replace(old, new))
    spec = importlib.util.spec_from_file_location(name, f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_mutants():
    cases = [
        ("nhl_stats_m1", "mine, theirs = (g[\"home_score\"], g[\"away_score\"]) if t == g[\"home\"] else (g[\"away_score\"], g[\"home_score\"])",
         "mine, theirs = (g[\"home_score\"], g[\"away_score\"])", "the margin is his team's"),
        ("nhl_stats_m2", ".days - 1 if i else None", ".days if i else None", "a back-to-back is 0 days' rest"),
        ("nhl_stats_m3", "min(100.0, 100 * e[\"pp_min\"] * 60 / tpp)", "100 * e[\"pp_min\"] * 60 / tpp", "the share is capped"),
        ("nhl_stats_m4", "if g[\"state\"] == \"postponed\":", "if False:", "a postponed game is no rest day"),
    ]
    for name, old, new, label in cases:
        assert not check(_mutant(name, old, new)), f"mutant survived: {label}"
