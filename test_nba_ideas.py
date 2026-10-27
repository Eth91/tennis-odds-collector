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
    assert L.process(now="2026-11-01T23:31:00", **kw) == 2 and len(sent) == 2            # RETURN and FOUL on B's points under
    assert any(b.startswith("🔻 RETURN Bee PTS u11.5") for b in sent) and any(b.startswith("🟠 FOUL Bee PTS u11.5") for b in sent)
    assert all(b.endswith("shadow") for b in sent)
    assert L.process(now="2026-11-01T23:33:00", **kw) == 0 and len(sent) == 2            # once per game


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
