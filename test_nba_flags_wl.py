"""NBA_FLAGS_WL_PREREG.md: the minutes/rate split is exact, and the model test's card applies the registered rules.
MUTANTS in test_mutants()."""
import importlib
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags_model_test as T
import nba_flags_wl as W


def check_split(mod):
    r = mod.split_effects({"proj": 18.0, "base_min": 30.0, "d_min": 5.0, "act": 12, "min": 24.0})
    r0 = mod.split_effects({"proj": 18.0, "base_min": 30.0, "d_min": 5.0, "act": 0, "min": 0.0})
    return (abs(r["m_eff"] + r["r_eff"] - (12 - 18.0)) < 1e-9 and abs(r["pmin"] - (30.0 + 0.98 + 0.356 * 5.0)) < 1e-9
            and abs(r0["m_eff"] + r0["r_eff"] - (0 - 18.0)) < 1e-9 and r["m_eff"] < 0)


def row(b, stat, line, so, date="2024-01-10", tg="BOS", d=5.0, price=1.9, n_out=1, xmin=28.0, act=30):
    # rate_60 = (so + br x 60) / (min_out + 60) with br = 0.5, min_out 60; proj = rate x (0.98 + 30 + 0.356 d)
    return {"date": date, "season": "23-24", "tg": (date, tg), "b": b, "x": 9, "stat": stat, "n_out": n_out,
            "xmin": xmin, "aidx": 1, "base10": 30.0, "last3": 30.0, "d_shr": d, "so": so, "min_out": 60.0, "br": 0.5,
            "act": act, "min": 32.0, "fdk": (line, price)}


def check_card(mod):
    pm = 0.98 + 30.0 + 0.356 * 5.0                                 # 32.76 projected minutes
    proj = lambda so: (so + 30.0) / 120.0 * pm
    rows = [row(1, "pts", proj(60) - 6.0, 60),                    # excess 1.2: carded
            row(1, "pra", proj(60) - 9.1, 60),                    # his combo (excess 1.4): singles first
            row(2, "pts", proj(60) - 5.5, 60),                    # excess 1.1: carded (2nd slot)
            row(3, "pts", proj(60) - 5.2, 60),                    # excess 1.04: 3rd in the team-game
            row(4, "pts", proj(60) - 11.0, 60),                   # excess 2.2: EDGE TOO BIG
            row(5, "reb", proj(60) - 1.5, 60, tg="NYK"),          # rebounds are on the card (amendment 32)
            row(6, "pts", proj(60) - 6.0, 60, tg="MIA", d=9.0),   # out of the 3-8 band (proj recomputed, still flagged)
            row(7, "pts", proj(60) - 6.0, 60, tg="LAL", price=1.79),
            row(8, "pts", proj(60) - 6.0, 60, tg="PHX", n_out=2),
            row(9, "pts", proj(60) - 6.0, 60, tg="DEN", xmin=32.0)]
    got = sorted((r["b"], r["stat"]) for r in mod.card(rows, 60.0, None))
    return got == [(1, "pts"), (2, "pts"), (5, "reb")]


def test_split():
    assert check_split(W)


def test_card_rules():
    assert check_card(T)


def test_mutants():
    for modname, chk, tag, a, b in (
            ("nba_flags_wl", check_split, "minutes effect at projected rate dropped",
             "r[\"m_eff\"] = r[\"prate\"] * (r[\"min\"] - r[\"pmin\"])", "r[\"m_eff\"] = (r[\"min\"] - r[\"pmin\"])"),
            ("nba_flags_model_test", check_card, "band ignored", "not 3 <= r[\"d_shr\"] <= 8 or ", ""),
            ("nba_flags_model_test", check_card, "edge cap ignored", "not 1 <= ex < 2", "not 1 <= ex"),
            ("nba_flags_model_test", check_card, "3 per team-game", "[:2]]", "[:3]]"),
            ("nba_flags_model_test", check_card, "combos first", "max([x for x in w if x[\"stat\"] not in COMBOS] or w,",
             "max(w,")):
        src = pathlib.Path(f"{pathlib.Path(__file__).resolve().parent}/{modname}.py").read_text()
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / f"{modname}_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            assert not chk(importlib.import_module(f"{modname}_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop(f"{modname}_mut", None)
