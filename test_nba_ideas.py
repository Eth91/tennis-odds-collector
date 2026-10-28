"""NBA_IDEAS_PREREG.md amendment 1: RETURN_UNDER, FOUL_BIG and MIN_RESTRICT on the side-by-side's synthetic day, and the
live tip - 30 pings. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_replay as RP
import nba_sxs_rules as SR
import test_nba_sxs as T


def stores(tmp, x_status="Probable", awy_fta=30):
    """HOM's season: X (30 min) played S0-S3 and missed S4-S5; B played 20 with X and 28 without; C 25 throughout.
    B (a C) fouls 6 a game. AWY has 10 earlier games drawing awy_fta free throws. X's status on the day: x_status."""
    p = T.stores(tmp)
    n = sqlite3.connect(p["news"])
    n.execute("UPDATE snapshots SET status = ? WHERE pid = ?", (x_status, T.X))
    n.execute("CREATE TABLE news_items (source, item_id, detected_at, player, pid, team, game_date, status, headline, body, "
              "provenance, seeded)")
    n.executemany("INSERT INTO news_items (detected_at, pid, game_date, headline, body) VALUES (?,?,?,?,?)",
                  [("2026-11-01T17:00:20+00:00", T.B, T.D, "Bee update", "Bee will play on a minutes restriction tonight"),
                   ("2026-11-01T12:00:00+00:00", T.C, T.D, "Cee update", "Cee is on a minute restriction")])
    n.commit()
    m = sqlite3.connect(p["matchup"])
    m.execute("ALTER TABLE player_games ADD COLUMN pf REAL")
    for i in range(6):
        g, d = f"S{i}", f"2026-10-{26 + i:02d}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'OTH', 100, 99)", (g, d))
        rows = [(g, "HOM", T.B, 20 if i < 4 else 28, 6), (g, "HOM", T.C, 25, 1)]
        if i < 4:
            rows.append((g, "HOM", T.X, 30, 2))
        m.executemany("INSERT INTO player_games (gid, team, pid, min, pf) VALUES (?,?,?,?,?)", rows)
    for i in range(10):
        g, d = f"A{i}", f"2026-10-{15 + i:02d}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'AWY', 'OTH', 100, 99)", (g, d))
        m.execute("INSERT INTO player_games (gid, team, pid, min, fta, pf) VALUES (?, 'AWY', ?, 30, ?, 2)", (g, T.O, awy_fta))
    m.commit()
    gl = sqlite3.connect(p["gamelogs"])
    gl.execute("CREATE TABLE positions (player_id INTEGER, player TEXT, position TEXT)")
    gl.executemany("INSERT INTO positions VALUES (?, '', ?)", [(T.B, "C"), (T.C, "F"), (T.X, "C"), (T.O, "G")])
    gl.commit()
    return p


def run(names, mod_sr=SR, **kw):
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = stores(tmp, **kw)
    mod_sr.MATCHUP_DB, mod_sr.ROLE_GAMELOGS_DB, mod_sr.NEWS_DB = p["matchup"], p["gamelogs"], p["news"]
    mod_sr.LINEUPS_DB, mod_sr.INDEX_JSON = tmp / "none.sqlite", tmp / "none.json"
    for c in ("_RD", "_FD", "_DV", "_VD"):
        getattr(mod_sr, c).clear()
    day = RP.Day(T.D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
    sig = RP.run_day(day, [c() for c in mod_sr.RULES if c.name in names])
    return sorted((s["rule"], s["pid"], s["market"], s["side"], s["line"], s["t"]) for s in sig)


def check(mod_sr=SR):
    ok = run(("RETURN_UNDER",), mod_sr) == [("RETURN_UNDER", T.B, "points", "under", 11.5, "2026-11-01T23:30:00")]
    ok &= run(("RETURN_UNDER",), mod_sr, x_status="Out") == []                         # X still out: no return
    ok &= run(("FOUL_BIG",), mod_sr) == [("FOUL_BIG", T.B, "points", "under", 11.5, "2026-11-01T23:30:00")]
    ok &= run(("FOUL_BIG",), mod_sr, awy_fta=18) == []                                 # AWY doesn't draw fouls: no
    ok &= run(("MIN_RESTRICT",), mod_sr) == [("MIN_RESTRICT", T.B, "points", "under", 10.5, "2026-11-01T17:00:30")]
    return bool(ok)                                                                     # C's 12:00 item: no look within 15 min


def test_idea_rules():
    try:
        assert check()
    finally:
        for c in ("_RD", "_FD", "_DV", "_VD"):
            getattr(SR, c).clear()


def test_registry_covers_idea_rules():
    for name in ("RETURN_UNDER", "FOUL_BIG", "MIN_RESTRICT"):
        cls = next(c for c in SR.RULES if c.name == name)
        assert SR.REGISTRY[name][1] == SR.fingerprint(cls) and cls.deps == SR.IDEA_DEPS


def test_live_tip30():
    import nba_role_open as L
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = stores(tmp)
    q = sqlite3.connect(p["lines"])
    q.execute("CREATE TABLE board (book TEXT, collected_at TEXT, gid TEXT, tip_utc TEXT, event TEXT, home TEXT, away TEXT, "
              "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    q.executemany("INSERT INTO board (book, collected_at, gid, tip_utc, home, away, pid, player, stat, line, side, odds) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [("fd", "2026-11-01T15:00:00", T.G, T.TIP, "HOM", "AWY", T.B, "Bee", "points", 11.5, s, o)
                                                        for s, o in (("over", 1.85), ("under", 1.95))])
    q.commit()
    sent = []
    kw = dict(lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=tmp / "none.sqlite", index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    assert L.process(now="2026-11-01T16:00:00", **kw) == 0                               # install
    assert L.process(now="2026-11-01T23:20:00", **kw) == 0 and sent == []                # before tip - 30
    L.process(now="2026-11-01T23:31:00", **kw)
    ideas = [b for b in sent if not b.startswith("🔵 UNDER")]                            # UNDER20 (NBA_UNDER_PREREG.md) also runs here
    assert len(ideas) == 2, sent                                                         # RETURN and FOUL on B's points under
    assert any(b.startswith("🔻 RETURN Bee PTS u11.5") for b in sent) and any(b.startswith("🟠 FOUL Bee PTS u11.5") for b in sent)
    assert all(b.endswith("shadow") for b in sent)
    n = len(sent)
    assert L.process(now="2026-11-01T23:33:00", **kw) == 0 and len(sent) == n            # once per game


def test_mutants():
    src = pathlib.Path(SR.__file__).read_text()
    ideas = pathlib.Path(sys.modules["nba_ideas"].__file__).read_text()
    for target, tag, a, b in (
            ("sr", "a returner still listed out counts", "        if st in RP.OUTS or (lu and x not in lu[\"active\"]):\n            continue\n", ""),
            ("ideas", "no minutes-bump condition", "if wo and wi and sum(wo) / len(wo) - sum(wi) / len(wi) >= 4:", "if wo and wi:"),
            ("ideas", "opponent FTA ignored", "and fta is not None and pf >= FOUL_PF36 and fta > FOUL_OPP_FTA", "and pf >= FOUL_PF36"),
            ("sr", "restriction window ignored", "if at > v.t or pid in self.done or RP.minus(v.t, self.window) > at:",
             "if at > v.t or pid in self.done:")):
        d = pathlib.Path(tempfile.mkdtemp())
        s_src, i_src = (src.replace(a, b), ideas) if target == "sr" else (src, ideas.replace(a, b))
        assert (src if target == "sr" else ideas).count(a) == 1, tag
        (d / "nba_ideas.py").write_text(i_src)
        (d / "nba_sxs_rules_imut.py").write_text(s_src)
        sys.path.insert(0, str(d))
        saved = sys.modules.pop("nba_ideas")
        try:
            assert not check(importlib.import_module("nba_sxs_rules_imut")), tag
        finally:
            sys.path.remove(str(d))
            for k in ("nba_ideas", "nba_sxs_rules_imut"):
                sys.modules.pop(k, None)
            sys.modules["nba_ideas"] = saved


def check_early(mod_sr=SR, last_fga=6.0, n_games=2):
    """B: last season 6 FGA a game; this season n_games at 30 min and 11 FGA. His points open at 10.5 (15:00)."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = T.stores(tmp)
    m = sqlite3.connect(p["matchup"])
    for i in range(n_games):
        g, d = f"E{i}", f"2026-10-{20 + i:02d}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'OTH', 100, 99)", (g, d))
        m.execute("INSERT INTO player_games (gid, team, pid, min, fga) VALUES (?, 'HOM', ?, 30, 11)", (g, T.B))
    m.commit()
    gl = sqlite3.connect(p["gamelogs"])
    gl.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fga)")
    gl.executemany("INSERT INTO logs_full VALUES ('2025-26', ?, ?, 'HOM', ?, '', 25, ?)",
                   [(f"L{i}", f"2026-01-{1 + i:02d}", T.B, last_fga) for i in range(25)])
    gl.commit()
    mod_sr.MATCHUP_DB, mod_sr.ROLE_GAMELOGS_DB = p["matchup"], p["gamelogs"]
    mod_sr._ED.clear()
    day = RP.Day(T.D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
    return [(s["pid"], s["market"], s["line"]) for s in RP.run_day(day, [mod_sr.EARLY_SURGE()])]


def test_early_surge():
    try:
        assert check_early() == [(T.B, "points", 10.5)]                # 11 >= 1.2 x 6 and >= 0.8 x 10.5: fires
        assert check_early(last_fga=10.0) == []                        # 11 < 1.2 x 10: no surge
        assert check_early(n_games=5) == []                            # game 6: the window is over
    finally:
        SR._ED.clear()


def test_early_surge_mutants():
    import nba_early as EARLY
    src = pathlib.Path(EARLY.__file__).read_text()
    sr_src = pathlib.Path(SR.__file__).read_text()
    for tag, a, b, kw in (("window ignored", "if not 1 <= len(g) <= 4 or pid not in ed.last:", "if pid not in ed.last:", {"n_games": 5}),
                          ("no surge needed", "fga >= SURGE * ed.last[pid]", "fga >= 0 * ed.last[pid]", {"last_fga": 10.0})):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_early.py").write_text(src.replace(a, b))
        (d / "nba_sxs_rules_emut.py").write_text(sr_src)
        sys.path.insert(0, str(d))
        saved = sys.modules.pop("nba_early")
        try:
            assert check_early(importlib.import_module("nba_sxs_rules_emut"), **kw) != [], tag
        finally:
            sys.path.remove(str(d))
            for k in ("nba_early", "nba_sxs_rules_emut"):
                sys.modules.pop(k, None)
            sys.modules["nba_early"] = saved


def check_live_early(L):
    """B surges (11 FGA vs 6 last season), C doesn't (11 vs 10). DraftKings opens both at 16:10; FanDuel opens B at 16:12."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = T.stores(tmp)
    m = sqlite3.connect(p["matchup"])
    for i in range(2):
        g, d = f"E{i}", f"2026-10-{20 + i:02d}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'OTH', 100, 99)", (g, d))
        m.executemany("INSERT INTO player_games (gid, team, pid, min, fga) VALUES (?, 'HOM', ?, 30, 11)", [(g, T.B), (g, T.C)])
    m.commit()
    gl = sqlite3.connect(p["gamelogs"])
    gl.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fga, fta, fg3a, fg3m, reb, ast, pts)")
    gl.executemany("INSERT INTO logs_full (season, game_id, date, team, player_id, player, min, fga) VALUES ('2025-26', ?, ?, 'HOM', ?, '', 25, ?)",
                   [(f"L{i}", f"2026-01-{1 + i:02d}", pid, f) for i in range(25) for pid, f in ((T.B, 6.0), (T.C, 10.0))])
    gl.commit()
    q = sqlite3.connect(p["lines"])
    q.execute("CREATE TABLE board (book TEXT, collected_at TEXT, gid TEXT, tip_utc TEXT, event TEXT, home TEXT, away TEXT, "
              "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    q.commit()
    sent = []
    kw = dict(lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=tmp / "none.sqlite", index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    assert L.process(now="2026-11-01T14:00:00", **kw) == 0                               # install
    q.executemany("INSERT INTO board (book, collected_at, gid, tip_utc, home, away, pid, player, stat, line, side, odds) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [("dk", "2026-11-01T16:10:00", T.G, T.TIP, "HOM", "AWY", pid, nm, "points", ln, s, 1.9)
                                                       for pid, nm, ln in ((T.B, "Bee", 10.5), (T.C, "Cee", 12.5)) for s in ("over", "under")])
    q.commit()
    assert L.process(now="2026-11-01T16:11:00", **kw) == 1
    assert sent == ["🟡 EARLY Bee PTS o10.5 -111 DK · 11.0 FGA vs 6.0 last season (1.83x) · shadow"], sent
    q.executemany("INSERT INTO board (book, collected_at, gid, tip_utc, home, away, pid, player, stat, line, side, odds) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [("fd", "2026-11-01T16:12:00", T.G, T.TIP, "HOM", "AWY", T.B, "Bee", "points", 10.5, s, 1.87)
                                                       for s in ("over", "under")])
    q.commit()
    assert L.process(now="2026-11-01T16:13:00", **kw) == 0 and len(sent) == 1           # FanDuel's opener later: once per player


def test_live_early_ping():
    import nba_role_open as L
    check_live_early(L)


def test_live_early_mutants():
    src = pathlib.Path(sys.modules["nba_role_open"].__file__).read_text()
    for tag, a, b in (("no surge check", "            if EARLY.early_surge(ed, pid, date, m[0]):", "            if ed.last.get(pid):"),
                      ("no dedupe", "                if cur.rowcount:\n                    ok = sender(early_body(", "                if True:\n                    ok = sender(early_body(")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_role_open_emut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            check_live_early(importlib.import_module("nba_role_open_emut"))
        except (AssertionError, ZeroDivisionError):
            continue
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_role_open_emut", None)
        raise AssertionError(f"mutant survived: {tag}")
