"""NBA_BOOST_PREREG.md: the BOOST rule on small fake seasons (no network). MUTANTS in test_mutants()."""
import importlib
import pathlib
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_boost as BOOST

X, S2, S6, B, G4, F5, N9 = 1, 2, 6, 3, 4, 5, 9   # X a big starter, S2 a guard starter, S6 a forward starter, B a big
POS = {X: "C", S2: "G", S6: "F", B: "C-F", G4: "G", F5: "F", N9: "C"}
BASE = {X: (30, 15, 1, 10, 3, 18), S2: (32, 18, 3, 4, 7, 22), S6: (28, 12, 2, 6, 2, 14), B: (24, 8, 0, 8, 1, 10),
        G4: (22, 8, 2, 3, 4, 9), F5: (18, 5, 1, 4, 1, 6), N9: (12, 4, 0, 3, 2, 4)}   # min, fga, fg3m, reb, ast, pts
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
    want(f and f["kind"] == "no history" and f["h"] == 0, "no history: 13.85 projected is 15%+ over 11.5")
    want(ev(c, "2024-11-07", B, "rebounds", 12.5, 1.9, {X}) is None, "13.85 is not 15% over 12.5")
    want(ev(c, "2024-11-07", B, "rebounds", 7.5, 1.9, {S2}) is None, "no history needs a relevant absence (the guard out)")

    dd = mod.BoostData(scenario_d(), groups, "2024-25")
    want(dd.step_in(X, "HOM", "2024-11-07", {X}) == N9, "the step-in player: the top bench player at X's position")
    pr = dd.projection(N9, X, "HOM", "2024-11-07", {X})
    want(pr and abs(pr["min"] - (12 + 30 * 36 / 136)) < 1e-9, "no 24-minute floor any more (amendment 6): N9 projects 19.9")
    want(ev(dd, "2024-11-07", N9, "rebounds", 5.5, 1.9, {X}) is None, "so no no-history flag (under 20 minutes)")

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
    g.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fga, fg3m, reb, ast, pts, fta, fg3a)")
    g.executemany("INSERT INTO logs_full (season, game_id, date, team, player_id, player, min, fga, fg3m, reb, ast, pts) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
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
    kw = dict(phone=L.ALL_RULES + ("BOOST_NH", "BOOST_PICKUP"), lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
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
    assert rows == [("BOOST", B, "rebounds", "dk", 1), ("BOOST_NH", N7, "rebounds", "dk", 0), ("BOOST_STEP", B, "rebounds", "dk", 0)], \
        rows                                             # B also steps in (amendment 2's pick): recorded, one ping a prop


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
    kw = dict(phone=L.ALL_RULES + ("BOOST_NH", "BOOST_PICKUP"), lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
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
    """No B and no starter flags; N9, the bench big, steps in for X (amendment 2's pick): his rebounds opener (2.5) pings
    as a STEP flag on ROLE1 v3's minutes (no starts to blend)."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = live_stores(tmp, step=True)
    sent = []
    kw = dict(phone=L.ALL_RULES + ("BOOST_NH", "BOOST_PICKUP"), lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=tmp / "none.sqlite", index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    L.process(now="2026-11-01T14:00:00", **kw)
    post(p, "dk", "2026-11-01T16:10:00", ((N9, "Ned Nine", "rebounds", 2.5),))
    L.process(now="2026-11-01T16:11:00", **kw)
    boost = [b for b in sent if "BOOST" in b]
    assert len(boost) == 1 and re.fullmatch(r"🟢 BOOST STEP Ned Nine REB o2\.5 -111 DK · Xavier Big out \(game 1\) · starts for him, "
                                            r"\d+ min \(0 starts\), proj [\d.]+ · [\d.]+ FGA, [\d.]+ FTA, [\d.]+ 3PA · shadow", boost[0]), sent
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
    ping = 'if cur.rowcount and rule in ("BOOST", "BOOST_STEP") and not dup:'
    for tag, a, b in (("no-history flags ping", ping, "if cur.rowcount:"),
                      ("no dedupe", ping, 'if rule in ("BOOST", "BOOST_STEP") and not dup:'),
                      ("STEP flags silent", ping, 'if cur.rowcount and rule == "BOOST" and not dup:'),
                      ("pickups ping", ping, 'if cur.rowcount and rule in ("BOOST", "BOOST_STEP", "BOOST_PICKUP") and not dup:'),
                      ("a prop pinged twice", ping, 'if cur.rowcount and rule in ("BOOST", "BOOST_STEP"):'),
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
            check_live_lineup(mod)
        except AssertionError:
            continue
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_role_open_bmut", None)
        raise AssertionError(f"mutant survived: {tag}")


# ── amendment 4: the lineup tab's usual five, its projected five, NBA.com's lineup ─────────────────────────────────
def lineup_stores(tmp, n9_started=False):
    """This season (with starter flags): T1-T6, X, S2, S6, G4 and F5 start; B (24 min) and N9 (12 min) come off the
    bench. Last season's P2-P4: N9 started for F5 (28 min, 9 rebounds) and B played 30. With n9_started, also P1
    (2026-03-01): X came off the bench and N9 started. X is Out on the 16:00 report."""
    p = {k: tmp / f"{k}.sqlite" for k in ("lines", "news", "matchup", "gamelogs", "lineups")}
    m = sqlite3.connect(p["matchup"])
    m.execute("CREATE TABLE games (gid, season, date, home, away, home_pts, away_pts)")
    m.execute("CREATE TABLE player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta, pf)")
    five = (X, S2, S6, G4, F5)
    games = [(f"P{i}", "2025-26", f"2026-03-0{i}") for i in (2, 3, 4)] + [(f"T{i}", "2026-27", f"2026-10-2{i}") for i in range(1, 7)]
    games += [("P1", "2025-26", "2026-03-01")] if n9_started else []
    for g, season, d in games:
        m.execute("INSERT INTO games VALUES (?, ?, ?, 'HOM', 'AWY', 100, 99)", (g, season, d))
        for pid in five + (B, N9):
            mn, fga, fg3m, reb, ast, pts = BASE[pid]
            st = int(pid in five)
            if g == "P1":
                st, mn = (0, 20) if pid == X else (1, 25) if pid == N9 else (st, mn)
            if g in ("P2", "P3", "P4"):                  # N9 started for F5, 28 minutes and 9 rebounds; B played 30
                st, mn, reb = (1, 28, 9) if pid == N9 else (0, 18, reb) if pid == F5 else (0, 30, reb) if pid == B else (st, mn, reb)
            m.execute("INSERT INTO player_games (gid, team, pid, starter, min, fga, fg3m, reb, ast, pts) VALUES (?, 'HOM', ?,?,?,?,?,?,?,?)",
                      (g, pid, st, mn, fga, fg3m, reb, ast, pts))
    m.commit()
    gl = sqlite3.connect(p["gamelogs"])
    gl.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, "
               "reb, ast, stl, blk, tov, pf, pts, plus_minus)")
    gl.execute("CREATE TABLE positions (player_id, player, position)")
    gl.executemany("INSERT INTO positions VALUES (?,?,?)", [(pid, NAME[pid], v) for pid, v in POS.items()])
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
    sqlite3.connect(p["lineups"]).execute("CREATE TABLE snaps (fetched_at TEXT, date_et TEXT, sha TEXT, body BLOB)")
    return p


def post_lineup(p, at, five):
    """NBA.com's lineups snapshot: HOM's five Expected (position set), AWY's empty."""
    import json
    import zlib
    body = {"games": [{"gameId": "G1", "homeTeam": {"teamAbbreviation": "HOM", "players": [
        {"personId": pid, "playerName": NAME[pid], "position": POS[pid][:1] + "X", "lineupStatus": "Expected"} for pid in five]},
        "awayTeam": {"teamAbbreviation": "AWY", "players": []}}]}
    c = sqlite3.connect(p["lineups"])
    c.execute("INSERT INTO snaps VALUES (?, ?, 'x', ?)", (at, D, zlib.compress(json.dumps(body).encode())))
    c.commit()


def check_lineups(mod):
    import nba_role as ROLE
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")

    tmp = pathlib.Path(tempfile.mkdtemp())
    p = lineup_stores(tmp)
    bd = mod.live_data(p["matchup"], p["gamelogs"], "2026-27")
    rd = ROLE.RoleData(p["matchup"], p["gamelogs"], "2026-27")
    want(bd.usual_five("HOM", D) == {X, S2, S6, G4, F5} and bd.starters("HOM", D) == {X, S2, S6, G4, F5},
         "starters are the usual five (most starts in the last 10), not 26+ minutes")
    five, pairs = bd.tonight("HOM", D, {X})
    want(five == {S2, S6, G4, F5, B} and pairs == {B: X}, "projected five: X's spot to B (shares a letter, more minutes than N9)")
    posted = (S2, S6, G4, F5, N9)
    want(bd.tonight("HOM", D, {X}, posted)[1] == {N9: X}, "NBA.com's five names N9 instead")
    step = lambda pid, mk, line, five_: mod.step_eval(bd, rd, D, "HOM", pid, mk, line, 1.9, {X}, five_)
    want(step(N9, "rebounds", 4.5, None) is None, "projected five: N9 is not the step-in, no STEP flag")
    v3 = mod.v3_minutes(bd, rd, "HOM", D, {X})
    sm = mod.step_minutes(bd, rd, N9, "HOM", D, {X})
    want(sm and sm[1] == 3 and abs(sm[0] - (0.5 * 28 + 0.5 * v3[N9])) < 1e-9, "N9's minutes: w = 3/6 on his 3 starts (28), the rest V3")
    rate = (18 + 27 / 84 * 150) / (72 + 150)
    f = step(N9, "rebounds", 4.5, posted)
    smf = mod.step_minutes(bd, rd, N9, "HOM", D, {X}, 26.0)
    want(v3[N9] < 26 and abs(smf[0] - (0.5 * 28 + 0.5 * 26)) < 1e-9, "the floor: V3 raised to 26 before the blend")
    want(f and mod.kind_of(f) == "step" and abs(f["proj_min"] - smf[0]) < 1e-9 and abs(f["proj"] - smf[0] * rate) < 1e-9
         and f["n_starts"] == 3,
         "NBA.com's five: N9 steps in on the floored minutes x his rebounds per minute (amendment 7), a STEP flag")
    rt = mod.rates(bd, N9, D)
    want(f and all(abs(f["vol"][s] - smf[0] * rt[s]) < 1e-9 for s in ("fga", "fta", "fg3a")) and rt["fga"] > 0,
         "the ping's shot volume: his FGA, FTA and 3PA per minute x his STEP minutes")
    want(step(N9, "assists", 0.5, posted) is None, "X is not a top-2 passer: no STEP flag on assists")
    want(mod.step_eval(bd, rd, D, "HOM", N9, "rebounds", 4.5, 1.6, {X}, posted) is None, "STEP skips overs worse than -150")
    smb = mod.step_minutes(bd, rd, B, "HOM", D, {X})
    want(smb and smb[1] == 0 and smb[0] == v3[B], "B has no starts: his minutes are V3's")
    tfive, tpairs = bd.tonight("HOM", D, {X}, posted)
    want(bd.pickup("HOM", D, N9, tfive, {X}) == (B, "history", 30.0, 3), "the bench pickup: B played 30 when N9 started (24 otherwise)")
    fake = mod.Trees({"features": list(mod.MIN_FEATURES), "baseline": 30.0, "trees": []})
    pick = lambda pid, five_: mod.pickup_eval(bd, rd, D, "HOM", pid, "assists", 0.5, 1.9, {X}, five_, trees=fake)
    f = pick(B, posted)
    want(f and mod.kind_of(f) == "pickup" and f["proj_min"] == 30.0 and f["step_in"] == N9, "B's assists: a PICKUP flag at 30 minutes")
    want(pick(F5, posted) is None, "only the pickup")
    want(pick(N9, None) is None, "not before NBA.com's five: on the projected five N9 would be B's pickup")
    tmp2 = pathlib.Path(tempfile.mkdtemp())
    bd2 = mod.live_data(lineup_stores(tmp2, n9_started=True)["matchup"], tmp2 / "gamelogs.sqlite", "2026-27")
    want(bd2.tonight("HOM", D, {X})[1] == {N9: X},
         "projected five: N9 started last season's game X did not (no starts in the last 10), so he steps in")
    rd2 = ROLE.RoleData(tmp2 / "matchup.sqlite", tmp2 / "gamelogs.sqlite", "2026-27")
    sm2 = mod.step_minutes(bd2, rd2, N9, "HOM", D, {X})
    f2 = mod.step_eval(bd2, rd2, D, "HOM", N9, "rebounds", 2.5, 1.9, {X}, None)
    want(sm2 and sm2[2] < 26 and f2 and abs(f2["proj_min"] - sm2[0]) < 1e-9, "the projected five: no floor (V3 under 26 stays)")
    return ok


FAKE_30 = {"features": list(BOOST.MIN_FEATURES), "baseline": 30.0, "trees": []}


def check_live_lineup(L):
    """DraftKings opens N9's rebounds (4.5) and B's assists (0.5) at 16:10, before NBA.com's lineup: no flag. NBA.com
    posts N9 starting at 17:00; the 17:01 run judges both 16:10 props at their lines: one STEP ping (N9) and one silent
    PICKUP row (B); the 17:02 run adds nothing."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = lineup_stores(tmp)
    sent = []
    kw = dict(phone=L.ALL_RULES + ("BOOST_NH", "BOOST_PICKUP"), lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=p["lineups"], index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    saved = BOOST._TREES.get("b")
    BOOST._TREES["b"] = BOOST.Trees(FAKE_30)
    try:
        L.process(now="2026-11-01T14:00:00", **kw)
        post(p, "dk", "2026-11-01T16:10:00", ((N9, "Ned Nine", "rebounds", 4.5), (B, "Bee Big", "assists", 0.5)))
        L.process(now="2026-11-01T16:11:00", **kw)
        assert not [b for b in sent if "BOOST" in b], sent
        post_lineup(p, "2026-11-01T17:00:00+00:00", (S2, S6, G4, F5, N9))
        L.process(now="2026-11-01T17:01:00", **kw)
        L.process(now="2026-11-01T17:02:00", **kw)
    finally:
        BOOST._TREES.pop("b", None)
        if saved:
            BOOST._TREES["b"] = saved
    boost = [b for b in sent if "BOOST" in b]
    assert len(boost) == 1 and re.fullmatch(r"🟢 BOOST STEP Ned Nine REB o4\.5 -111 DK · Xavier Big out \(game 1\) · starts for him, "
                                            r"\d+ min \(3 starts\), proj [\d.]+ · [\d.]+ FGA, [\d.]+ FTA, [\d.]+ 3PA · shadow", boost[0]), sent
    rows = sqlite3.connect(tmp / "role.sqlite").execute(
        "SELECT rule, pid, market, pinged FROM ratio_signals WHERE rule LIKE 'BOOST%' ORDER BY rule").fetchall()
    assert rows == [("BOOST_PICKUP", B, "assists", 0), ("BOOST_STEP", N9, "rebounds", 1)], rows


class FakeView:
    def __init__(self, boards):
        self.date, self.t, self.changed, self._b = D, None, set(), boards

    def board(self, g, p, mk, b):
        return self._b.get((g, p, mk, b), {})

    def props(self, g, book):
        return [(p, mk) for (g2, p, mk, b) in self._b if g2 == g and b == book]

    def games(self):
        return {"G1": {"tip": "2026-11-02T00:00:00", "home": "HOM", "away": "AWY"}}

    def game_of(self, team):
        return "G1" if team in ("HOM", "AWY") else None


def check_replay_step(SR):
    """The side-by-side's BOOST_STEP and BOOST_PICKUP: the 16:10 openers without a lineup give nothing; DraftKings'
    first look after NBA.com's 17:00 lineup gives N9's STEP signal and B's PICKUP signal once each."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = lineup_stores(tmp)
    post_lineup(p, "2026-11-01T17:00:00+00:00", (S2, S6, G4, F5, N9))
    saved = SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB, SR.LINEUPS_DB, BOOST._TREES.get("b")
    SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB, SR.LINEUPS_DB = p["matchup"], p["gamelogs"], p["lineups"]
    BOOST._TREES["b"] = BOOST.Trees(FAKE_30)
    got = {}
    try:
        for cls in (SR.BOOST_STEP, SR.BOOST_PICKUP):
            ks = [("G1", N9, "rebounds", "dk"), ("G1", B, "assists", "dk")]
            v = FakeView({ks[0]: {(4.5, "over"): 1.9, (4.5, "under"): 1.9}, ks[1]: {(0.5, "over"): 1.9, (0.5, "under"): 1.9}})
            r = cls()
            r.start_day(v)
            r.on_report(v, "2026-11-01T16:00:04", [("HOM", X, "Out")], {}, set())
            v.t, v.changed = "2026-11-01T16:10:00", set(ks)
            first = r.on_obs(v, "dk", {"G1"})
            v.t, v.changed = "2026-11-01T17:03:00", set()
            second = r.on_obs(v, "dk", {"G1"})
            third = r.on_obs(v, "dk", {"G1"})
            got[cls.name] = (first, [(s_["pid"], s_["market"], s_["line"]) for s_ in second], third)
    finally:
        SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB, SR.LINEUPS_DB = saved[:3]
        BOOST._TREES.pop("b", None)
        if saved[3]:
            BOOST._TREES["b"] = saved[3]
    assert got == {"BOOST_STEP": ([], [(N9, "rebounds", 4.5)], []), "BOOST_PICKUP": ([], [(B, "assists", 0.5)], [])}, got


def test_lineups():
    import nba_role_open as L
    import nba_sxs_rules as SR
    assert check_lineups(BOOST)
    check_live_lineup(L)
    check_replay_step(SR)


LINEUP_MUTANTS = (
    ("no usual five", "if self.has_starts and len(recent) >= USUAL_MIN:", "if False:"),
    ("NBA.com's lineup ignored", "            if posted:\n                five, gone = set(posted)", "            if False:\n                five, gone = set(posted)"),
    ("who started when he sat ignored", "key = lambda u, p: (self.started_for(u, team, date)[p],", "key = lambda u, p: (0,"),
    ("STEP blend all on starts", "w = len(starts) / (len(starts) + STEP_K)", "w = 1.0"),
    ("STEP ignores relevance", "        if not any(bd.relevant(x, team, date)[s] for s in PARTS[market]):\n            continue\n        sm, rt",
     "        sm, rt"),
    ("STEP for anyone", "if n > SPOT_MAX or bd.step_in(x, team, date, out_all, posted) != pid:", "if n > SPOT_MAX:"),
    ("pickup for anyone", "if not pk or pk[0] != pid:", "if not pk:"),
    ("rates without last season", "+ lr * K_RATE) / (tm + K_RATE)", "+ 0) / (tm + 0)"),
    ("pickup without NBA.com", "    if not posted or price is None", "    if price is None"),
    ("no floor once posted", "STEP_FLOOR if posted else None", "None"),
    ("floor at the opener too", "STEP_FLOOR if posted else None", "STEP_FLOOR"),
    ("STEP without a price cap", "        return None\n    for x in sorted(bd.starters(team, date) & set(out_all)):\n        n = bd.absence_n(x, team, date)\n        if n > SPOT_MAX or bd.step_in",
     "        pass\n    for x in sorted(bd.starters(team, date) & set(out_all)):\n        n = bd.absence_n(x, team, date)\n        if n > SPOT_MAX or bd.step_in"),
)


def test_lineup_mutants():
    src = pathlib.Path(BOOST.__file__).read_text()
    for tag, a, b in LINEUP_MUTANTS:
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_boost_lmut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check_lineups(importlib.import_module("nba_boost_lmut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_boost_lmut", None)
    import nba_role_open as L
    lsrc = pathlib.Path(L.__file__).read_text()
    a = "        fired += step_checks(con, keys, now, n, matchup_db, gamelogs_db, lineups_db, sender, bds, rds, stat_cache, phone)\n"
    assert lsrc.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_role_open_lmut.py").write_text(lsrc.replace(a, ""))
    sys.path.insert(0, str(d))
    try:
        check_live_lineup(importlib.import_module("nba_role_open_lmut"))
    except AssertionError:
        pass
    else:
        raise AssertionError("mutant survived: no second check when NBA.com's lineup posts")
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("nba_role_open_lmut", None)


def test_boost():
    assert check(BOOST)
    assert check_backtest(BOOST)


MUTANTS = (
    ("same-day game leaks", "return g[:bisect_left(g, (date,))]", "return g[:bisect_left(g, (date + '~',))]"),
    ("other starters ignored", "all(o in box and box[o][\"min\"] for o in others)", "True"),
    ("games before X joined count", " and self.on_team_at(x, team, d, date)", ""),
    ("80% bar strict", "hits / len(hist) >= HIT_AT - 1e-9", "hits / len(hist) > HIT_AT"),
    ("a push counts as a hit", "hits = sum(stat_of(r, market) > line for r in hist)", "hits = sum(stat_of(r, market) >= line for r in hist)"),
    ("no price cap", "if price is None or price < PRICE_MIN - 1e-9 or pid in out_all:\n        return None\n    starters = bd.starters",
     "if price is None or pid in out_all:\n        return None\n    starters = bd.starters"),
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
    ("step-in from any position", "if gx and self.groups.get(p) == gx and", "if gx and"),
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
    test_lineups()
    test_lineup_mutants()
    print("test_nba_boost: OK")
