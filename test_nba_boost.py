"""NBA_BOOST_PREREG.md: the BOOST rule on small fake seasons (no network). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_boost as BOOST

X, S2, S6, B, G4, F5 = 1, 2, 6, 3, 4, 5           # X a big starter, S2 a guard starter, S6 a forward starter, B a big
POS = {X: "C", S2: "G", S6: "F", B: "C-F", G4: "G", F5: "F"}
BASE = {X: (30, 15, 1, 10, 3, 18), S2: (32, 18, 3, 4, 7, 22), S6: (28, 12, 2, 6, 2, 14), B: (24, 8, 0, 8, 1, 10),
        G4: (22, 8, 2, 3, 4, 9), F5: (18, 5, 1, 4, 1, 6)}   # min, fga, fg3m, reb, ast, pts
BOX = ("min", "fga", "fg3m", "reb", "ast", "pts")
NAME = {X: "Xavier Big", S2: "Sam Guard", S6: "Sid Forward", B: "Bee Big", G4: "Gus Guard", F5: "Fay Forward"}


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
    print("test_nba_boost: OK")
