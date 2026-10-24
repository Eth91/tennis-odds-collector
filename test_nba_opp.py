"""Amendment 9: OPPORTUNITY-CONFIRMED. nba_flags.opp_cell on a hand-built split, and the scoreboard
cell (forward only from its own cutover). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_clv as V
import nba_flags as F


def apps(dates):
    return [(d, 30.0, {}, "GSW") for d in dates]


OUT = apps(["2026-01-05", "2026-01-06"])
IN = apps(["2026-01-01", "2026-01-02", "2026-01-03"])


def trk(out_rc, in_rc, out_pa=5.0, in_pa=5.0):
    t = {}
    for a in OUT:
        t[(a[0], 1)] = {"reb_chances": out_rc, "potential_ast": out_pa}
    for a in IN:
        t[(a[0], 1)] = {"reb_chances": in_rc, "potential_ast": in_pa}
    return t


def check(mod_f, mod_v):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    want(mod_f.opp_cell(trk(11.0, 10.0), 1, OUT, IN, "rebounds") == ("CONFIRMED", 1.1),
         "rebound chances 11 vs 10 per game = ratio 1.10 = CONFIRMED (inclusive)")
    want(mod_f.opp_cell(trk(10.9, 10.0), 1, OUT, IN, "reb")[0] == "NOT CONFIRMED", "1.09 = NOT CONFIRMED")
    want(mod_f.opp_cell(trk(10.0, 10.0, 8.0, 5.0), 1, OUT, IN, "pra") == ("CONFIRMED", round(18 / 15, 3)),
         "PRA uses rebound chances + potential assists (18 vs 15)")
    want(mod_f.opp_cell(trk(10.0, 10.0, 8.0, 5.0), 1, OUT, IN, "rebounds")[0] == "NOT CONFIRMED",
         "rebounds ignore potential assists")
    want(mod_f.opp_cell(trk(20.0, 10.0), 1, OUT, IN, "points") == ("n/a", None), "points-only = n/a")
    want(mod_f.opp_cell(None, 1, OUT, IN, "rebounds") == ("NO DATA", None), "no tracking data = NO DATA")
    t = trk(20.0, 10.0)
    del t[("2026-01-05", 1)]
    want(mod_f.opp_cell(t, 1, OUT, IN, "rebounds") == ("THIN", None), "only 1 tracked game without X = THIN")
    # scoreboard: forward only from AMEND9_CUTOVER
    d = pathlib.Path(tempfile.mkdtemp())
    sh = mod_f._shadow(d / "s.sqlite")
    q = sqlite3.connect(d / "q.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT,"
              " stat TEXT, line REAL, side TEXT, odds REAL)")
    for fid, at, pid in (("old", "2026-01-09T11:00:00", 1), ("new", "2026-01-09T13:00:00", 2)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, gtime, "
                   "pid, opp_cell) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (fid, at, "2026-01-09", "wowy", "T", "X", f"B{pid}", "reb", 5.5, 1.9, "G", "2026-01-10T00:00:00Z",
                    pid, "CONFIRMED"))
    sh.commit(); q.commit()
    mod_v.SHADOW, mod_v.LINES = d / "s.sqlite", d / "q.sqlite"
    mod_v.AMEND8_CUTOVER, mod_v.AMEND9_CUTOVER = "2026-01-09T10:00:00", "2026-01-09T12:00:00"
    rows = {r["flag_id"]: r for r in mod_v.collect()}
    want("OPPORTUNITY" not in rows["old"].get("cells", {}) and rows["new"]["cells"].get("OPPORTUNITY") == "CONFIRMED",
         "scoreboard cell only for flags logged after amendment 9's cutover")
    return ok


def test_opp():
    assert check(F, V)


def test_mutants():
    for modname, mod, name, a, b in (
            ("nba_flags", F, "threshold exclusive", "return (\"CONFIRMED\" if ratio >= OPP_CONFIRM", "return (\"CONFIRMED\" if ratio > OPP_CONFIRM"),
            ("nba_flags", F, "PRA = rebounds only", '"pra": ("reb_chances", "potential_ast"),', '"pra": ("reb_chances",),'),
            ("nba_flags", F, "thin rule off", "if len(vo) < C.MIN_WOWY or len(vi) < 3 or sum(vi) <= 0:", "if sum(vi) <= 0:"),
            ("nba_clv", V, "not forward-only", 'if r["logged_at"] >= AMEND9_CUTOVER:', "if True:")):
        src = pathlib.Path(mod.__file__).read_text()
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / f"{modname}_mut9.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            m = importlib.import_module(f"{modname}_mut9")
            print(f"MUTANT ({name}) — must fail:")
            assert not (check(m, V) if modname == "nba_flags" else check(F, m)), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop(f"{modname}_mut9", None)


if __name__ == "__main__":
    test_opp()
    test_mutants()
    print("test_nba_opp: OK")
