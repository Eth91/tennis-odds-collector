"""Amendments 9 and 33: OPPORTUNITY-CONFIRMED. nba_flags.opp_cell on a hand-built split (the flag's season
only), and the scoreboard cell (forward only from amendment 33's cutover). MUTANTS in test_mutants()."""
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
S = 2025                                    # their season (nba_coldstart.season_of), = the flag's


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
    want(mod_f.opp_cell(trk(11.0, 10.0), 1, OUT, IN, "rebounds", S) == ("CONFIRMED", 1.1),
         "rebound chances 11 vs 10 per game = ratio 1.10 = CONFIRMED (inclusive)")
    want(mod_f.opp_cell(trk(10.9, 10.0), 1, OUT, IN, "reb", S)[0] == "NOT CONFIRMED", "1.09 = NOT CONFIRMED")
    want(mod_f.opp_cell(trk(10.0, 10.0, 8.0, 5.0), 1, OUT, IN, "pra", S) == ("CONFIRMED", round(18 / 15, 3)),
         "PRA uses rebound chances + potential assists (18 vs 15)")
    want(mod_f.opp_cell(trk(10.0, 10.0, 8.0, 5.0), 1, OUT, IN, "rebounds", S)[0] == "NOT CONFIRMED",
         "rebounds ignore potential assists")
    want(mod_f.opp_cell(trk(20.0, 10.0), 1, OUT, IN, "points", S) == ("n/a", None), "points-only = n/a")
    want(mod_f.opp_cell(None, 1, OUT, IN, "rebounds", S) == ("NO DATA", None), "no tracking data = NO DATA")
    t = trk(20.0, 10.0)
    del t[("2026-01-05", 1)]
    want(mod_f.opp_cell(t, 1, OUT, IN, "rebounds", S) == ("THIN", None), "only 1 tracked game without X = THIN")
    t = trk(11.0, 10.0)
    t[("2026-01-01", 1)]["reb_chances"] = None          # feed omitted him: 0 chances that game
    want(mod_f.opp_cell(t, 1, OUT, IN, "rebounds", S) == ("CONFIRMED", round(11 / (20 / 3), 3)),
         "a tracked game with blank rebound chances counts as 0 (the feed omits zero-chance players)")
    # AMENDMENT 33: only the flag's season. Without X in 2026-27 at 19 rebound chances, with X in 2025-26
    # at 13: the feed's gap between the seasons alone used to read CONFIRMED (1.46).
    o27 = apps(["2026-10-25", "2026-10-26"])
    i26 = apps(["2026-03-01", "2026-03-02", "2026-03-03"])
    i27 = apps(["2026-10-20", "2026-10-21", "2026-10-22"])
    t = {(a[0], 1): {"reb_chances": 19.0, "potential_ast": 5.0} for a in o27 + i27}
    t.update({(a[0], 1): {"reb_chances": 13.0, "potential_ast": 5.0} for a in i26 + apps(["2026-03-05"])})
    want(mod_f.opp_cell(t, 1, o27, i26, "rebounds", 2026) == ("THIN", None),
         "with-X games all from last season = THIN, not CONFIRMED")
    want(mod_f.opp_cell(t, 1, o27, i26 + i27, "rebounds", 2026) == ("NOT CONFIRMED", 1.0),
         "last season's games are dropped, not averaged in (19 vs 19)")
    want(mod_f.opp_cell(t, 1, o27 + apps(["2026-03-05"]), i26 + i27, "rebounds", 2025) == ("THIN", None),
         "a 2025-26 flag counts only 2025-26 games (1 without X = THIN)")
    # scoreboard: forward only from AMEND33_CUTOVER (the cell restarts; amendment 9's labels are not scored)
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
    mod_v.AMEND8_CUTOVER, mod_v.AMEND9_CUTOVER, mod_v.AMEND33_CUTOVER = (
        "2026-01-09T10:00:00", "2026-01-09T10:30:00", "2026-01-09T12:00:00")     # "old" sits between 9 and 33
    rows = {r["flag_id"]: r for r in mod_v.collect()}
    want("OPPORTUNITY" not in rows["old"].get("cells", {}) and rows["new"]["cells"].get("OPPORTUNITY") == "CONFIRMED",
         "scoreboard cell only for flags logged after amendment 33's cutover")
    return ok


def test_opp():
    assert check(F, V)


def test_mutants():
    for modname, mod, name, a, b in (
            ("nba_flags", F, "threshold exclusive", "return (\"CONFIRMED\" if ratio >= OPP_CONFIRM", "return (\"CONFIRMED\" if ratio > OPP_CONFIRM"),
            ("nba_flags", F, "PRA = rebounds only", '"pra": ("reb_chances", "potential_ast"),', '"pra": ("reb_chances",),'),
            ("nba_flags", F, "thin rule off", "if len(vo) < C.MIN_WOWY or len(vi) < 3 or sum(vi) <= 0:", "if sum(vi) <= 0:"),
            ("nba_flags", F, "blank skipped, not 0", "return [sum(row.get(k) or 0.0 for k in keys)\n                for row in (trk.get((a[0], b_id)) for a in apps if C.season_of(a[0]) == season) if row]",
             "return [sum(row.get(k) for k in keys)\n                for row in (trk.get((a[0], b_id)) for a in apps if C.season_of(a[0]) == season) if row and all(row.get(k) is not None for k in keys)]"),
            ("nba_flags", F, "any season (amendment 33 off)", "for a in apps if C.season_of(a[0]) == season)", "for a in apps)"),
            ("nba_clv", V, "not forward-only", 'if r["logged_at"] >= AMEND33_CUTOVER:', "if True:"),
            ("nba_clv", V, "old labels scored", 'if r["logged_at"] >= AMEND33_CUTOVER:', 'if r["logged_at"] >= AMEND9_CUTOVER:')):
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
