"""NBA_BOOST_PREREG.md: the BOOST rule on small fake seasons (no network). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_boost as BOOST

X, S2, S6, B, G4, F5, N9 = 1, 2, 6, 3, 4, 5, 9   # X a big starter, S2 a guard starter, S6 a forward starter, B a big
POS = {X: "C", S2: "G", S6: "F", B: "C-F", G4: "G", F5: "F", N9: "C"}
BASE = {X: (30, 15, 1, 10, 3, 18), S2: (32, 18, 3, 4, 7, 22), S6: (28, 12, 2, 6, 2, 14), B: (24, 8, 0, 8, 1, 10),
        G4: (22, 8, 2, 3, 4, 9), F5: (18, 5, 1, 4, 1, 6), N9: (12, 4, 0, 3, 0, 4)}   # min, fga, fg3m, reb, ast, pts
BOX = ("min", "fga", "fg3m", "reb", "ast", "pts")
NAME = {X: "Xavier Big", S2: "Sam Guard", S6: "Sid Forward", B: "Bee Big", G4: "Gus Guard", F5: "Fay Forward", N9: "Ned Nine"}


def game(season, gid, date, team, players, edits=None):
    rows = []
    for p in players:
        v = dict(zip(BOX, BASE[p]))
        v.update((edits or {}).get(p, {}))
        rows.append({"season": season, "gid": gid, "date": date, "team": team, "pid": p, **v})
    return rows


def scenario_a():
    """Last season (2023-24): X plays L1-L2 for AWY, joins HOM (L3-L5), misses L6-L10 with S2 and S6 in (B 26 min and
    12, 11, 13, 10, 8 rebounds; F5 18 min, 7 rebounds), misses L11 with S2 also out (B 4), plays L12-L14. This season:
    T1-T6 everyone plays; X misses T7 (B 5 rebounds, tonight in the leak check), T8 and T9 (B 12, 12)."""
    rows, everyone = [], [X, S2, S6, B, G4, F5]
    no_x = [S2, S6, B, G4, F5]
    for i in (1, 2):
        d = f"2023-11-0{i}"
        rows += game("2023-24", f"A{i}", d, "AWY", [X])
        rows += game("2023-24", f"L{i}", d, "HOM", no_x, {B: {"reb": 3}})
    for i in (3, 4, 5):
        rows += game("2023-24", f"L{i}", f"2023-11-0{i}", "HOM", everyone)
    for i, rb in zip((6, 7, 8, 9, 10), (12, 11, 13, 10, 8)):
        rows += game("2023-24", f"L{i}", f"2023-11-{i:02d}", "HOM", no_x, {B: {"min": 26, "reb": rb}, F5: {"reb": 7}})
    rows += game("2023-24", "L11", "2023-11-11", "HOM", [S6, B, G4, F5], {B: {"min": 26, "reb": 4}})
    for i in (12, 13, 14):
        rows += game("2023-24", f"L{i}", f"2023-11-{i}", "HOM", everyone)
    for i in range(1, 7):
        rows += game("2024-25", f"T{i}", f"2024-11-0{i}", "HOM", everyone)
    for i, rb in ((7, 5), (8, 12), (9, 12)):
        rows += game("2024-25", f"T{i}", f"2024-11-0{i}", "HOM", no_x, {B: {"min": 26, "reb": rb}})
    return rows


def scenario_b():
    """This season only: T1-T3 everyone; S2 (the guard) misses T4-T6 with X and S6 in (B 26 min, 12 rebounds); T7-T9
    everyone. Tonight T10, S2 out again (absence game 1)."""
    rows, everyone = [], [X, S2, S6, B, G4, F5]
    for i in range(1, 10):
        if 4 <= i <= 6:
            rows += game("2024-25", f"T{i}", f"2024-11-0{i}", "HOM", [X, S6, B, G4, F5], {B: {"min": 26, "reb": 12}})
        else:
            rows += game("2024-25", f"T{i}", f"2024-11-0{i}", "HOM", everyone)
    return rows


def scenario_c():
    """This season only: T1-T6 everyone. Tonight T7 nobody has missed a game yet (no history)."""
    return [r for i in range(1, 7) for r in game("2024-25", f"T{i}", f"2024-11-0{i}", "HOM", [X, S2, S6, B, G4, F5])]


def scenario_d():
    """This season only, no B: T1-T6 everyone. N9 (a 12-minute big) is the only bench big, so he steps in for X."""
    return [r for i in range(1, 7) for r in game("2024-25", f"T{i}", f"2024-11-0{i}", "HOM", [X, S2, S6, G4, F5, N9])]


def scenario_e():
    """Last season: L1-L7 everyone (B 24 min, 10 points); L8-L10 S2 and S6 rest (B 30 min, 25 points). This season: T1
    without B, T2-T4 everyone (B 14 points)."""
    rows, everyone = [], [X, S2, S6, B, G4, F5]
    for i in range(1, 11):
        rest = i >= 8
        rows += game("2023-24", f"L{i}", f"2024-03-{i:02d}", "HOM", [X, B, G4, F5] if rest else everyone,
                     {B: {"min": 30, "pts": 25}} if rest else None)
    rows += game("2024-25", "T1", "2024-11-01", "HOM", [X, S2, S6, G4, F5])
    for i in (2, 3, 4):
        rows += game("2024-25", f"T{i}", f"2024-11-0{i}", "HOM", everyone, {B: {"pts": 14}})
    return rows


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")

    groups = {p: mod.group(v) for p, v in POS.items()}
    a = mod.BoostData(scenario_a(), groups, "2024-25")
    ev = lambda bd, d, p, mk, line, price, out: mod.boost_eval(bd, d, "HOM", p, mk, line, price, out)
    want(a.starters("HOM", "2024-11-07") == {X, S2, S6}, "starters: 26+ min/g over this season's games")
    f = ev(a, "2024-11-07", B, "rebounds", 9.5, 1.9, {X})
    want(f and f["kind"] == "history" and (f["hits"], f["h"], f["n"]) == (4, 5, 1),
         "B: 4 of 5 history games over 9.5 (L6-L10 only: not tonight, not L11 with S2 out, not before X joined)")
    want(f and abs(f["avg"] - 10.8) < 1e-9 and f["relevant"], "the history average; X is a top-2 rebounder")
    want(ev(a, "2024-11-07", B, "rebounds", 10.0, 1.9, {X}) is None, "a push is not a hit (3 of 5 beat 10)")
    want(ev(a, "2024-11-07", B, "rebounds", 9.5, 1.6, {X}) is None, "an over worse than -150 is skipped")
    want(ev(a, "2024-11-07", F5, "rebounds", 5.5, 1.9, {X}) is None, "F5 beat 5.5 every time but averaged 18 minutes")
    want(ev(a, "2024-11-10", B, "rebounds", 4.5, 1.9, {X}) is None, "absence game 4 is not a spot")
    want((ev(a, "2024-11-09", B, "rebounds", 4.5, 1.9, {X}) or {}).get("n") == 3, "absence game 3 is")

    b = mod.BoostData(scenario_b(), groups, "2024-25")
    want(not b.relevant(S2, "HOM", "2024-11-10")["reb"] and b.relevant(S2, "HOM", "2024-11-10")["pts"],
         "the guard is not a top-2 rebounder but is top-3 in FGA")
    want(ev(b, "2024-11-10", B, "rebounds", 9.5, 1.9, {S2}) is None, "an irrelevant absence needs 6+ games (B has 3 of 3)")

    c = mod.BoostData(scenario_c(), groups, "2024-25")
    pr = c.projection(B, X, "HOM", "2024-11-07", {X})
    want(pr and abs(pr["reb"] - (8 + 10 * 24 / 41)) < 1e-9 and abs(pr["min"] - (24 + 30 * 72 / 172)) < 1e-9,
         "projection: X's 10 rebounds and 30 minutes split 3x to his group (B) over the active roster")
    f = ev(c, "2024-11-07", B, "rebounds", 11.5, 1.9, {X})
    want(f and f["kind"] == "no history" and f["h"] == 0 and not f["step"],
         "no history: 13.85 projected is 15%+ over 11.5 (B steps in but needs no floor: not a STEP flag)")
    want(ev(c, "2024-11-07", B, "rebounds", 12.5, 1.9, {X}) is None, "13.85 is not 15% over 12.5")
    want(ev(c, "2024-11-07", B, "rebounds", 7.5, 1.9, {S2}) is None, "no history needs a relevant absence (the guard out)")

    dd = mod.BoostData(scenario_d(), groups, "2024-25")
    want(dd.step_in(X, "HOM", "2024-11-07", {X}) == N9, "the step-in player: the top bench player at X's position")
    pr = dd.projection(N9, X, "HOM", "2024-11-07", {X})
    m0 = 12 + 30 * 36 / 136
    want(pr and abs(pr["min"] - 24.0) < 1e-9 and abs(pr["reb"] - (3 + 10 * 9 / 26 + (24 - m0) * 3 / 12)) < 1e-9,
         "he projects to 19.9 minutes, raised to 24 with his own rebounds per minute")
    f = ev(dd, "2024-11-07", N9, "rebounds", 5.5, 1.9, {X})
    want(f and f["kind"] == "no history" and f["step"] and mod.kind_of(f) == "step",
         "N9 at 24 minutes: 7.48 rebounds is 15%+ over 5.5, a STEP flag")

    e = mod.BoostData(scenario_e(), groups, "2024-25")
    be = e.base_with(B, X, "HOM", "2024-11-04", [S2, S6])
    want(be and be["pts"] == 10.0 and be["min"] == 24.0,
         "2 games this season: last season's, only those with the other starters (not the 25-point rest games)")
    be = e.base_with(B, X, "HOM", "2024-11-05", [S2, S6])
    want(be and be["pts"] == 14.0, "3 games this season: this season's only")
    return ok


def check_backtest(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")

    tmp = pathlib.Path(tempfile.mkdtemp())
    g = sqlite3.connect(tmp / "g.sqlite")
    g.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fga, fg3m, reb, ast, pts)")
    g.executemany("INSERT INTO logs_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  [(r["season"], r["gid"], r["date"], r["team"], r["pid"], NAME[r['pid']], r["min"], r["fga"], r["fg3m"],
                    r["reb"], r["ast"], r["pts"]) for r in scenario_a()])
    g.execute("CREATE TABLE positions (player_id, player, position)")
    g.executemany("INSERT INTO positions VALUES (?,?,?)", [(p, NAME[p], v) for p, v in POS.items()])
    g.commit()
    o = sqlite3.connect(tmp / "o.sqlite")
    o.execute("CREATE TABLE props (game_date, player, market, line, side, price, book)")
    o.executemany("INSERT INTO props VALUES ('2024-11-07', 'Bee Big', 'player_rebounds', ?, ?, ?, ?)",
                  [(9.5, "over", 1.9, "fanduel"), (9.5, "under", 1.9, "fanduel"), (10.5, "over", 2.4, "fanduel"),
                   (10.5, "under", 1.55, "fanduel"), (9.5, "over", 1.95, "draftkings"), (9.5, "under", 1.85, "draftkings")])
    o.commit()
    fl = mod.backtest(tmp / "g.sqlite", tmp / "o.sqlite", seasons=("2024-25",))
    want(len(fl) == 1, "one flag: B's rebounds on 11-07")
    if fl:
        f = fl[0]
        want((f["line"], f["price"], f["nv"]) == (9.5, 1.95, 0.5), "the main rung nearest even; best over; FanDuel's no-vig")
        want(f["actual"] == 5 and f["u"] == -1.0, "graded on tonight's box: 5 rebounds loses")
    return ok


N7 = 7                                                   # joined this season: no history games
TIP, D = "2026-11-02T00:00:00+00:00", "2026-11-01"


def live_stores(tmp, step=False):
    """This season (nba_matchup): T1-T6, everyone plays (N7 22 min, 6 rebounds). Last season (logs_full 2025-26): L1-L5
    everyone, X out L6-L10 with S2 and S6 in (B 26 min, 12, 11, 13, 10, 12 rebounds), L11-L13 everyone. Tonight X is Out
    on the 16:00 report."""
    p = {k: tmp / f"{k}.sqlite" for k in ("lines", "news", "matchup", "gamelogs")}
    m = sqlite3.connect(p["matchup"])
    m.execute("CREATE TABLE games (gid, season, date, home, away, home_pts, away_pts)")
    m.execute("CREATE TABLE player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta, pf)")
    base = {**BASE, N7: (22, 6, 0, 6, 1, 7)}
    for i in range(1, 7):
        g = f"T{i}"
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'AWY', 100, 99)", (g, f"2026-10-2{i}"))
        m.executemany("INSERT INTO player_games (gid, team, pid, min, fga, fg3m, reb, ast, pts) VALUES (?, 'HOM', ?,?,?,?,?,?,?)",
                      [(g, pid) + base[pid] for pid in ((X, S2, S6, G4, F5, N9) if step else (X, S2, S6, B, G4, F5, N7))])
    m.commit()
    gl = sqlite3.connect(p["gamelogs"])
    gl.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, "
               "reb, ast, stl, blk, tov, pf, pts, plus_minus)")
    rows = []
    for i in range(1, 14):
        out_x = 6 <= i <= 10
        for pid in (X, S2, S6, B, G4, F5):
            if out_x and pid == X:
                continue
            mn, fga, fg3m, reb, ast, pts = BASE[pid]
            if out_x and pid == B:
                mn, reb = 26, (12, 11, 13, 10, 12)[i - 6]
            rows.append(("2025-26", f"L{i}", f"2026-01-{i:02d}", "HOM", pid, NAME[pid], mn, fga, fg3m, reb, ast, pts))
    gl.executemany("INSERT INTO logs_full (season, game_id, date, team, player_id, player, min, fga, fg3m, reb, ast, pts) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    gl.execute("CREATE TABLE positions (player_id, player, position)")
    if step:
        gl.execute("DELETE FROM logs_full")              # the step case: no last season, no history
    gl.executemany("INSERT INTO positions VALUES (?,?,?)", [(pid, NAME.get(pid, "Nate Seven"), v) for pid, v in {**POS, N7: "C"}.items()])
    gl.commit()
    n = sqlite3.connect(p["news"])
    n.execute("CREATE TABLE snapshots (mark, published_at, game_date, matchup, team, pid, player, status, reason)")
    n.execute("INSERT INTO snapshots (published_at, game_date, team, pid, player, status) VALUES "
              "('2026-11-01T16:00:04+00:00', ?, 'HOM', ?, 'Xavier Big', 'Out')", (D, X))
    n.commit()
    q = sqlite3.connect(p["lines"])
    q.execute("CREATE TABLE board (book TEXT, collected_at TEXT, gid TEXT, tip_utc TEXT, event TEXT, home TEXT, away TEXT, "
              "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    q.commit()
    return p


def post(p, book, at, props):
    q = sqlite3.connect(p["lines"])
    q.executemany("INSERT INTO board (book, collected_at, gid, tip_utc, home, away, pid, player, stat, line, side, odds) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [(book, at, "G1", TIP, "HOM", "AWY", pid, nm, stat, ln, s, 1.9)
                                                       for pid, nm, stat, ln in props for s in ("over", "under")])
    q.commit()


def check_live(L):
    """DraftKings opens B's rebounds (9.5) and N7's (7.5) at 16:10; FanDuel opens B's at 16:12. One BOOST ping (B, 5 of 5
    without X); N7's no-history flag is recorded, not pinged; FanDuel's later opener does not ping again."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = live_stores(tmp)
    sent = []
    kw = dict(lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=tmp / "none.sqlite", index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    L.process(now="2026-11-01T14:00:00", **kw)                                          # install
    post(p, "dk", "2026-11-01T16:10:00", ((B, "Bee Big", "rebounds", 9.5), (N7, "Nate Seven", "rebounds", 7.5)))
    L.process(now="2026-11-01T16:11:00", **kw)
    boost = [b for b in sent if "BOOST" in b]
    assert boost == ["🟢 BOOST Bee Big REB o9.5 -111 DK · Xavier Big out (game 1) · 5/5 beat 9.5 without him, avg 11.6 · shadow"], sent
    post(p, "fd", "2026-11-01T16:12:00", ((B, "Bee Big", "rebounds", 9.5),))
    L.process(now="2026-11-01T16:13:00", **kw)
    assert [b for b in sent if "BOOST" in b] == boost, sent
    rows = sqlite3.connect(tmp / "role.sqlite").execute(
        "SELECT rule, pid, market, book, pinged FROM ratio_signals WHERE rule LIKE 'BOOST%' ORDER BY rule").fetchall()
    assert rows == [("BOOST", B, "rebounds", "dk", 1), ("BOOST_NH", N7, "rebounds", "dk", 0)], rows


def check_new_markets(L):
    """Running before the combos were watched (installed, no 'markets' key): a P+R prop already posted is marked open, not
    acted on; the rebounds opener still pings."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = live_stores(tmp)
    con = sqlite3.connect(tmp / "role.sqlite")
    for s_ in L.DDL:
        con.execute(s_)
    con.execute("INSERT INTO meta VALUES ('installed', '2026-10-27T00:00:00')")
    con.commit()
    sent = []
    kw = dict(lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=tmp / "none.sqlite", index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    post(p, "dk", "2026-11-01T16:10:00", ((B, "Bee Big", "pts_reb", 15.5), (B, "Bee Big", "rebounds", 9.5)))
    L.process(now="2026-11-01T16:11:00", **kw)
    assert [b for b in sent if "BOOST" in b] == [
        "🟢 BOOST Bee Big REB o9.5 -111 DK · Xavier Big out (game 1) · 5/5 beat 9.5 without him, avg 11.6 · shadow"], sent
    post(p, "fd", "2026-11-01T16:12:00", ((B, "Bee Big", "pts_reb", 15.5),))
    L.process(now="2026-11-01T16:13:00", **kw)
    assert [b for b in sent if "P+R" in b] == [
        "🟢 BOOST Bee Big P+R o15.5 -111 FD · Xavier Big out (game 1) · 5/5 beat 15.5 without him, avg 21.6 · shadow"], sent


def check_live_step(L):
    """No B; N9, a 12-minute big, steps in for X at 24 minutes: his rebounds opener pings as a STEP flag."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = live_stores(tmp, step=True)
    sent = []
    kw = dict(lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=tmp / "none.sqlite", index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    L.process(now="2026-11-01T14:00:00", **kw)
    post(p, "dk", "2026-11-01T16:10:00", ((N9, "Ned Nine", "rebounds", 5.5),))
    L.process(now="2026-11-01T16:11:00", **kw)
    assert [b for b in sent if "BOOST" in b] == [
        "🟢 BOOST STEP Ned Nine REB o5.5 -111 DK · Xavier Big out (game 1) · steps in, proj 7.5 at 24 min · shadow"], sent
    rows = sqlite3.connect(tmp / "role.sqlite").execute("SELECT rule, pinged FROM ratio_signals WHERE rule LIKE 'BOOST%'").fetchall()
    assert rows == [("BOOST_STEP", 1)], rows


def test_live():
    import nba_role_open as L
    check_live(L)
    check_new_markets(L)
    check_live_step(L)


def test_live_mutants():
    import nba_role_open as L
    src = pathlib.Path(L.__file__).read_text()
    for tag, a, b in (("no-history flags ping", 'if cur.rowcount and rule != "BOOST_NH":', "if cur.rowcount:"),
                      ("no dedupe", 'if cur.rowcount and rule != "BOOST_NH":', 'if rule != "BOOST_NH":'),
                      ("STEP flags silent", 'if cur.rowcount and rule != "BOOST_NH":', 'if cur.rowcount and rule == "BOOST":'),
                      ("new markets act at once", "if first_run or market not in installed or", "if first_run or")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_role_open_bmut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            mod = importlib.import_module("nba_role_open_bmut")
            check_live(mod)
            check_new_markets(mod)
            check_live_step(mod)
        except AssertionError:
            continue
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_role_open_bmut", None)
        raise AssertionError(f"mutant survived: {tag}")


def test_boost():
    assert check(BOOST)
    assert check_backtest(BOOST)


MUTANTS = (
    ("same-day game leaks", "return g[:bisect_left(g, (date,))]", "return g[:bisect_left(g, (date + '~',))]"),
    ("other starters ignored", "all(o in box and box[o][\"min\"] for o in others)", "True"),
    ("games before X joined count", " and self.on_team_at(x, team, d, date)", ""),
    ("80% bar strict", "hits / len(hist) >= HIT_AT - 1e-9", "hits / len(hist) > HIT_AT"),
    ("a push counts as a hit", "hits = sum(stat_of(r, market) > line for r in hist)", "hits = sum(stat_of(r, market) >= line for r in hist)"),
    ("no price cap", "if price is None or price < PRICE_MIN - 1e-9 or pid in out_all:", "if price is None or pid in out_all:"),
    ("no minutes condition", "if avg_min >= MIN_AVG_MIN and", "if True and"),
    ("irrelevant absences at 3 games", "(rel or len(hist) >= MIN_H_IRRELEVANT)", "True"),
    ("absence game not checked", "if n > SPOT_MAX:", "if False:"),
    ("no-history ignores relevance", "elif rel:", "else:"),
    ("no position weight", "SAME_W if self.groups.get(p) and self.groups.get(p) == self.groups.get(x) else 1.0", "1.0"),
    ("no 15% margin", "mu >= PROJ_AT * line", "mu >= line"),
    ("bases ignore the other starters", "if all(q in b and b[q][\"min\"] for q in (pid, x, *others))]",
     "if all(q in b and b[q][\"min\"] for q in (pid, x))]"),
    ("bases mix the seasons", "(this if len(this) >= BASE_MIN_GAMES else [r for s, r in rs if s != self.season])",
     "[r for s, r in rs]"),
    ("bases from last season first", "(this if len(this) >= BASE_MIN_GAMES else [r for s, r in rs if s != self.season])",
     "[r for s, r in rs if s != self.season]"),
    ("no minutes floor", "if step in proj and proj[step][\"min\"] < STEP_MIN", "if False and proj[step][\"min\"] < STEP_MIN"),
    ("step-in from any position", "if gx and self.groups.get(p) == gx and", "if gx and"),
    ("STEP not marked", 'proj[step]["step"] = 1.0', "pass"),
)


def test_mutants():
    src = pathlib.Path(BOOST.__file__).read_text()
    for tag, a, b in MUTANTS:
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_boost_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            mod = importlib.import_module("nba_boost_mut")
            assert not (check(mod) and check_backtest(mod)), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_boost_mut", None)


if __name__ == "__main__":
    test_boost()
    test_mutants()
    test_live()
    test_live_mutants()
    print("test_nba_boost: OK")
