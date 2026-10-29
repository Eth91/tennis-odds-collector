"""NBA_REBMATCH_PREREG.md: miss-distance bands, last season's rebound profile, and the opportunity factor from games
before the date only, on a small fake season (no network). MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_rebmatch as RM

B = 7    # the player: a rim rebounder on HOM


def stores():
    """2023-24: HOM plays AWY on 11-01..11-06 (six games), then OPP on 11-07. OPP misses a lot at the rim (20 short misses
    a game in its own games vs AWY's 5). B's line on 11-07 is 9.5; on 11-07 itself OPP misses 99 short shots, which no
    feature may see."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    g = sqlite3.connect(tmp / "g.sqlite")
    g.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, reb)")
    rows, shots = [], []
    for i in range(6):
        gid, d = f"G{i}", f"2023-11-0{i + 1}"
        rows += [("2023-24", gid, d, "HOM", B, "Bee Seven", 30, 10), ("2023-24", gid, d, "AWY", 8, "Ex", 30, 5)]
        shots += [(gid, 8, 10, 10, 0)] * 5 + [(gid, B, 250, 0, 0)] * 3           # AWY: 5 short misses; HOM: 3 long
        o, d2 = f"O{i}", f"2023-10-2{i + 1}"                                   # OPP's earlier games vs ZZZ
        rows += [("2023-24", o, d2, "OPP", 9, "Opp Nine", 30, 6), ("2023-24", o, d2, "ZZZ", 10, "Zed", 30, 6)]
        shots += [(o, 9, 10, 10, 0)] * 20 + [(o, 10, 10, 10, 0)] * 5
    rows += [("2023-24", "G9", "2023-11-07", "HOM", B, "Bee Seven", 30, 12), ("2023-24", "G9", "2023-11-07", "OPP", 9, "Opp Nine", 30, 6)]
    shots += [("G9", 9, 10, 10, 0)] * 99
    rows += [("2022-23", f"P{i}", f"2023-01-{i + 1:02d}", "HOM", B, "Bee Seven", 30, 10) for i in range(25)]
    g.executemany("INSERT INTO logs_full VALUES (?,?,?,?,?,?,?,?)", rows)
    g.commit()
    s = sqlite3.connect(tmp / "s.sqlite")
    s.execute("CREATE TABLE shots (season TEXT, gid TEXT, event INTEGER, pid INTEGER, team_id INTEGER, date TEXT, x INTEGER, y INTEGER, made INTEGER)")
    s.executemany("INSERT INTO shots VALUES ('2023-24', ?, ?, ?, 0, '', ?, ?, ?)", [(gid, k, pid, x, y, m) for k, (gid, pid, x, y, m) in enumerate(shots)])
    s.commit()
    o = sqlite3.connect(tmp / "o.sqlite")
    o.execute("CREATE TABLE props (game_date, player, market, line, side, price, book)")
    o.executemany("INSERT INTO props VALUES ('2023-11-07', 'Bee Seven', 'player_rebounds', ?, ?, ?, ?)",
                  [(9.5, "over", 1.9, "fanduel"), (9.5, "under", 1.9, "fanduel"), (10.5, "over", 2.4, "fanduel"),
                   (10.5, "under", 1.55, "fanduel"), (9.5, "over", 1.95, "draftkings"), (9.5, "under", 1.85, "draftkings")])
    o.commit()
    r = sqlite3.connect(tmp / "r.sqlite")
    r.executescript(RM.DDL)
    prof = [("miss_dist", "0-6 Feet", 150, 50, 100), ("miss_dist", "7-13 Feet", 50, 0, 50), ("miss_dist", "13-19 Feet", 25, 0, 25),
            ("miss_dist", "19+ Feet", 25, 0, 25), ("grab_dist", "0-3 Feet", 150, 0, 0), ("grab_dist", "3-6 Feet", 50, 0, 0),
            ("grab_dist", "6-10 Feet", 25, 0, 0), ("grab_dist", "10+ Feet", 25, 0, 0),
            ("contested", "0 Contesting Rebounders", 125, 0, 0), ("contested", "1 Contesting Rebounder", 125, 0, 0)]
    r.executemany("INSERT INTO rebdist VALUES ('2022-23', ?, ?, ?, ?, ?, ?)", [(B,) + x for x in prof])
    r.commit()
    return tmp


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    want([mod.band(x, 0) for x in (0, 69, 70, 129, 130, 189, 190, 250)] == [0, 0, 1, 1, 2, 2, 3, 3], "miss-distance bands")
    tmp = stores()
    pr = mod.profiles(tmp / "r.sqlite", tmp / "g.sqlite")[("2022-23", B)]
    want(pr["near"] == 0.8 and pr["open"] == 0.5, "near = within 6 ft of grab-distance boards; open = uncontested share")
    want(pr["dreb"] == [4.0, 2.0, 1.0, 1.0] and pr["oreb"] == [2.0, 0, 0, 0], "last season's boards per game by miss band")
    rows = mod.build(tmp / "g.sqlite", tmp / "s.sqlite", tmp / "o.sqlite", tmp / "r.sqlite")
    rows = [r for r in rows if r["date"] == "2023-11-07"]
    want(len(rows) == 1, "one prop: B on 11-07")
    if not rows:
        return False
    r = rows[0]
    want(r["line"] == 9.5 and r["over"] == 1.95 and r["under"] == 1.9, "the main closest to even; best prices across books")
    want(r["reb_r"] == 10 / 9.5 and r["mpg"] == 30, "volume from B's six earlier games only (not 11-07's 12)")
    # league before 11-07: 24 team-games (HOM, AWY, OPP, ZZZ x 6); short misses 30 (AWY) + 120 (OPP) + 30 (ZZZ) = 180 -> 7.5 a
    # game. OPP: (120 + 10 x 7.5) / (6 + 10) / 7.5 = 1.625 (the 99 on 11-07 are not seen). Long: HOM's 18 -> 0.75 a game.
    want(abs(r["f_short"] - 1.625) < 1e-9, "the opponent's short misses, shrunk k=10, before the date")
    f_opp_long, f_own_short = (0 + 10 * 0.75) / 16 / 0.75, (0 + 10 * 7.5) / 16 / 7.5
    m = (4 * 1.625 + 2 * 1.0 + 1 * 1.0 + 1 * f_opp_long + 2 * f_own_short) / 10     # no misses at 7-19 ft: factor 1
    want(abs(r["M"] - m) < 1e-9, "M weights defensive boards by the opponent's misses and offensive by his team's")
    want(r["opp_short_top"] and not r["opp_long_top"] and not r["opp_long_bottom"],
         "OPP is top third for short misses; tied for fewest long misses puts it in no third")
    want(r["u"] == 0.95 and r["u_under"] == -1.0, "12 rebounds: the over wins at 1.95")
    return ok


def test_rebmatch():
    assert check(RM)


def test_mutants():
    src = pathlib.Path(RM.__file__).read_text()
    for tag, a, b in (
            ("same-day misses leak", "            for gid in {x[0] for x in by_date[d]}:                # the date's games join",
             "            for gid in []:                # the date's games join"),
            ("no shrinkage", "return (mine + K_TEAM * lg) / (self.n[team] + K_TEAM) / lg", "return mine / max(self.n[team], 1) / lg"),
            ("opponent and own swapped", "f_opp = [M.factor(opp, b) for b in range(4)]", "f_opp = [M.factor(team, b) for b in range(4)]"),
            ("ties put a team in a third", 'return "top" if sum(x < me for x in v)', 'return "top" if sum(x <= me for x in v)'),
            ("grab distance from all boards", "sum(rows.get((\"grab_dist\", b), (0, 0, 0))[0] for b in NEAR_BANDS) / grab",
             "sum(rows.get((\"grab_dist\", b), (0, 0, 0))[0] for b in GRAB_BANDS) / grab")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_rebmatch_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_rebmatch_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_rebmatch_mut", None)


if __name__ == "__main__":
    test_rebmatch()
    test_mutants()
    print("test_nba_rebmatch: OK")
