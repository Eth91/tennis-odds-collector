"""NBA_RATIO_PREREG.md: the ratio rules at the opener on the side-by-side's synthetic day, with this season's volume
before the date only. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_ratio as RATIO
import nba_replay as RP
import nba_sxs_rules as SR
import test_nba_sxs as T


def stores(tmp):
    p = T.stores(tmp)
    m = sqlite3.connect(p["matchup"])
    for i in range(4):                                       # B: 11 FGA a game; C: 9
        g, d = f"R{i}", f"2026-10-{27 + i:02d}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'AWY', 100, 99)", (g, d))
        m.executemany("INSERT INTO player_games (gid, team, pid, min, pts, reb, ast, fga) VALUES (?,?,?,?,?,?,?,?)",
                      [(g, "HOM", T.B, 30, 12, 5, 3, 11), (g, "HOM", T.C, 28, 10, 4, 2, 9)])
    m.execute("INSERT INTO player_games (gid, team, pid, min, pts, reb, ast, fga) VALUES ('G1', 'HOM', ?, 30, 40, 5, 3, 40)", (T.C,))
    m.commit()                                               # C's 40 FGA on the day itself must not count
    p["tracking"] = tmp / "trk.sqlite"
    t = sqlite3.connect(p["tracking"])
    t.executescript("CREATE TABLE tracking (date TEXT, player_id INTEGER, potential_ast REAL, reb_chances REAL);"
                    "CREATE TABLE fetched (date TEXT, measure TEXT)")
    for i in range(4):
        d = f"2026-10-{27 + i:02d}"
        t.executemany("INSERT INTO fetched VALUES (?, ?)", [(d, "Passing"), (d, "Rebounding")])
        t.execute("INSERT INTO tracking VALUES (?, ?, 7.0, 13.0)", (d, T.B))
        if i < 2:                                            # C: 6 potential assists on 2 of 4 fetched dates -> 3.0 a game
            t.execute("INSERT INTO tracking VALUES (?, ?, 6.0, 0.0)", (d, T.C))
    t.commit()
    q = sqlite3.connect(p["lines"])                          # openers at 16:10: B ast 3.5 / reb 6.5; C ast 2.5
    q.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [("2026-11-01T16:10:00", "fd", T.G, T.TIP, pid, "", st, ln, sd, 1.9) for pid, st, ln in
                   ((T.B, "assists", 3.5), (T.B, "rebounds", 6.5), (T.C, "assists", 2.5)) for sd in ("over", "under")])
    q.commit()
    return p


def check(mod=RATIO, mod_sr=SR):
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = stores(tmp)
    mod_sr.MATCHUP_DB, mod_sr.TRACKING_DB = p["matchup"], p["tracking"]
    mod_sr._RT.clear()
    day = RP.Day(T.D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
    sig = RP.run_day(day, [c() for c in mod_sr.RULES if c.name.startswith("RATIO_")])
    got = sorted((s["rule"], s["pid"], s["market"], s["line"]) for s in sig)
    # B: FGA 11 >= 10.5 (his points opened at 15:00); PA 7 >= 2 x 3.5; RC 13 >= 2 x 6.5.
    # C: FGA 9 < 12.5 (his 40 on the day not counted); PA 3.0 (missing dates are 0) < 2 x 2.5.
    return got == [("RATIO_FGA", T.B, "points", 10.5), ("RATIO_PA", T.B, "assists", 3.5), ("RATIO_RC", T.B, "rebounds", 6.5)]


def test_ratio_rules():
    try:
        assert check()
    finally:
        SR._RT.clear()


def test_registry_covers_ratio_rules():
    for name in ("RATIO_FGA", "RATIO_PA", "RATIO_RC"):
        cls = next(c for c in SR.RULES if c.name == name)
        assert SR.REGISTRY[name][1] == SR.fingerprint(cls) and cls.deps == SR.RATIO_DEPS


def test_mutants():
    src = pathlib.Path(RATIO.__file__).read_text()
    for tag, a, b in (("same-day volume", 'g = [(d, f) for d, f in self.games.get(pid, ()) if d < date]',
                       'g = [(d, f) for d, f in self.games.get(pid, ()) if d <= date]'),
                      ("PA multiple 1x", '"RATIO_PA": ("assists", "pa", 2.0)', '"RATIO_PA": ("assists", "pa", 1.0)'),
                      ("missing tracking skipped, not 0", "tr = [self.trk.get((d, pid), (0.0, 0.0)) for d, _f in g if d in self.fetched]",
                       "tr = [self.trk[(d, pid)] for d, _f in g if (d, pid) in self.trk]")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_ratio.py").write_text(src.replace(a, b))
        sr_src = pathlib.Path(SR.__file__).read_text()
        (d / "nba_sxs_rules_rmut.py").write_text(sr_src)
        sys.path.insert(0, str(d))
        saved = sys.modules.pop("nba_ratio")
        try:
            mut = importlib.import_module("nba_ratio")
            srm = importlib.import_module("nba_sxs_rules_rmut")
            assert not check(mut, srm), tag
        finally:
            sys.path.remove(str(d))
            for k in ("nba_ratio", "nba_sxs_rules_rmut"):
                sys.modules.pop(k, None)
            sys.modules["nba_ratio"] = saved
