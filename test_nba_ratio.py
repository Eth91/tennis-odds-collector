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
                    "CREATE TABLE fetched (date TEXT, measure TEXT, rows INTEGER, fetched_at TEXT)")
    for i in range(4):
        d = f"2026-10-{27 + i:02d}"
        at = f"2026-10-{28 + i:02d}T11:20:00+00:00"                # stored the next morning, as the daily job did
        t.executemany("INSERT INTO fetched VALUES (?, ?, 1, ?)", [(d, "Passing", at), (d, "Rebounding", at)])
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
    for tag, a, b in (("same-day volume", 'g = [(d, f, mn) for d, f, mn in self.games.get(pid, ()) if d < date]',
                       'g = [(d, f, mn) for d, f, mn in self.games.get(pid, ()) if d <= date]'),
                      ("PA multiple 1x", '"RATIO_PA": ("assists", "pa", 2.0)', '"RATIO_PA": ("assists", "pa", 1.0)'),
                      ("missing tracking skipped, not 0", "tr = [self.trk.get((d, pid), (0.0, 0.0)) for d, _f, _m in g if d in self.fetched]",
                       "tr = [self.trk[(d, pid)] for d, _f, _m in g if (d, pid) in self.trk]")):
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


def test_pa28_replay_and_live():
    """B: 7.0 potential assists a game. A 2.5 assists opener clears 2.8x (7.0); 3.5 doesn't (9.8). Live pings once."""
    import nba_role_open as L
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = stores(tmp)
    q = sqlite3.connect(p["lines"])
    q.execute("UPDATE quotes SET line = 2.5 WHERE pid = ? AND stat = 'assists'", (T.B,))
    q.commit()
    SR.MATCHUP_DB, SR.TRACKING_DB = p["matchup"], p["tracking"]
    SR._RT.clear()
    try:
        day = RP.Day(T.D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
        sig = RP.run_day(day, [SR.RATIO_PA28()])
        assert [(s["pid"], s["market"], s["line"], s["t"]) for s in sig] == [(T.B, "assists", 2.5, "2026-11-01T16:10:00")]
    finally:
        SR._RT.clear()
    q.execute("CREATE TABLE board (book TEXT, collected_at TEXT, gid TEXT, tip_utc TEXT, event TEXT, home TEXT, away TEXT, "
              "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    sent = []
    kw = dict(lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"],
              tracking_db=p["tracking"], db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    assert L.process(now="2026-11-01T15:00:00", **kw) == 0                               # install
    for pid, nm, ln in ((T.B, "Bee", 2.5), (T.C, "Cee", 3.5)):
        q.executemany("INSERT INTO board (book, collected_at, gid, tip_utc, pid, player, stat, line, side, odds) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      [("fd", "2026-11-01T16:10:00", T.G, T.TIP, pid, nm, "assists", ln, s, 1.9) for s in ("over", "under")])
    q.commit()
    assert L.process(now="2026-11-01T16:11:00", **kw) == 1 and len(sent) == 1
    assert sent[0].startswith("🟣 PA28 Bee AST o2.5") and "2.8x" in sent[0] and sent[0].endswith("shadow")
    assert L.process(now="2026-11-01T16:12:00", **kw) == 0 and len(sent) == 1


def dvp_stores(tmp, oth_guard_pts=30, b_min=30):
    """AWY has 14 games before the date: 10 vs OTH (OTH's guard scores oth_guard_pts) and 4 vs HOM (B, a G, scores 12)."""
    p = stores(tmp)
    m = sqlite3.connect(p["matchup"])
    m.execute("UPDATE player_games SET min = ? WHERE pid = ? AND gid LIKE 'R%'", (b_min, T.B))
    for i in range(10):
        g, d = f"O{i}", f"2026-10-{15 + i:02d}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'OTH', 'AWY', 100, 99)", (g, d))
        m.executemany("INSERT INTO player_games (gid, team, pid, min, pts, fga) VALUES (?,?,?,?,?,?)",
                      [(g, "OTH", 50, 34, oth_guard_pts, 15), (g, "AWY", T.O, 30, 10, 9)])
    m.commit()
    gl = sqlite3.connect(p["gamelogs"])
    gl.execute("CREATE TABLE positions (player_id INTEGER, player TEXT, position TEXT)")
    gl.executemany("INSERT INTO positions VALUES (?, '', ?)", [(T.B, "G"), (T.C, "F"), (50, "G"), (T.O, "G")])
    gl.commit()
    return p


def check_dvp(mod_sr=SR, **kw):
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = dvp_stores(tmp, **kw)
    mod_sr.MATCHUP_DB, mod_sr.TRACKING_DB, mod_sr.ROLE_GAMELOGS_DB = p["matchup"], p["tracking"], p["gamelogs"]
    mod_sr._RT.clear()
    mod_sr._DV.clear()
    day = RP.Day(T.D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
    return [(s["pid"], s["market"], s["line"]) for s in RP.run_day(day, [mod_sr.PTS_DVP()])]


def test_pts_dvp():
    try:
        assert check_dvp() == [(T.B, "points", 10.5)]                   # soft on guards: B (11 FGA, 30 min) fires
        assert check_dvp(oth_guard_pts=4) == []                         # AWY tough on guards: no
        assert check_dvp(b_min=18) == []                                # under 20 minutes: no
    finally:
        SR._RT.clear()
        SR._DV.clear()


def test_pts_dvp_mutants():
    src = pathlib.Path(SR.__file__).read_text()
    for tag, a, b, kw in (("DvP cut ignored", "if d is not None and d > cut:", "if d is not None:", {"oth_guard_pts": 4}),
                          ("minutes ignored", 'or vol["mpg"] < mpg:', ":", {"b_min": 18})):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_sxs_rules_dmut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            assert check_dvp(importlib.import_module("nba_sxs_rules_dmut"), **kw) != [], tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_sxs_rules_dmut", None)
