"""nba_vs: the Matchup page's "Recent games vs <group> <market>" tables (docs/vs/{TEAM}.json)."""
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_matchup as MU
import nba_vs as VS


def quotes(d):
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    tip = "2026-10-25T23:00:00"
    rows = [("2026-10-25T15:00:00", "fd", 5, "points", 17.5, "over", 1.80), ("2026-10-25T15:00:00", "fd", 5, "points", 17.5, "under", 2.00),
            ("2026-10-25T20:00:00", "fd", 5, "points", 18.5, "over", 1.98), ("2026-10-25T20:00:00", "fd", 5, "points", 18.5, "under", 1.86),
            ("2026-10-25T20:00:00", "fd", 5, "points", 17.5, "over", None), ("2026-10-25T20:00:00", "fd", 5, "points", 17.5, "under", None),
            ("2026-10-25T23:30:00", "fd", 5, "points", 24.5, "over", 1.9), ("2026-10-25T23:30:00", "fd", 5, "points", 24.5, "under", 1.9),
            ("2026-10-25T20:00:00", "dk", 5, "points", 19.5, "over", 1.91), ("2026-10-25T20:00:00", "dk", 5, "points", 19.5, "under", 1.91),
            ("2026-10-25T20:00:00", "dk", 6, "rebounds", 7.5, "over", 2.1), ("2026-10-25T20:00:00", "dk", 6, "rebounds", 7.5, "under", 1.72)]
    q.executemany("INSERT INTO quotes VALUES (?,?,'G1',?,?,'',?,?,?,?)", [(t, b, tip, p, s, ln, sd, o) for t, b, p, s, ln, sd, o in rows])
    q.commit()
    return q


def test_closing_mains_takes_fanduel_before_tip():
    d = pathlib.Path(tempfile.mkdtemp())
    out = VS.closing_mains(quotes(d), ["G1", "G0"])
    # FD moved 17.5 -> 18.5 before tip and to 24.5 after it: 18.5 counts; DK's 19.5 loses to FD; DK alone counts alone
    assert out == {"G1": {"5|points": [18.5, 1.98, "fd"], "6|rebounds": [7.5, 2.1, "dk"]}, "G0": {}}


def box(gid, away, home):
    pl = lambda pid, name, mn, pts, reb=0, ast=0, fg3m=0: [pid, name, 1, mn, pts, reb, ast, 0, 0, fg3m, 0, 0, 0, 0, 0, 0, 0, 0]
    return {"gid": gid, "date": "2026-10-25", "status": "Final", "teams": [
        {"tri": away, "pts": 100, "home": False, "players": [pl(5, "Coby White", 30, 21, 3, 4, 2), pl(6, "Nikola V", 34, 12, 9),
                                                             pl(7, "Deep Bench", 4, 2)], "dnp": [], "tot": []},
        {"tri": home, "pts": 98, "home": True, "players": [pl(8, "Home Guy", 36, 25)], "dnp": [], "tot": []}]}


def test_team_rows_lists_the_other_side():
    rows = VS.team_rows("WAS", [("G1", "2026-10-25")], {"G1": box("G1", "CHI", "WAS")}, lambda pid, d: {5: "G", 6: "C"}.get(pid),
                        {"G1": {"5|points": [18.5, 1.98, "fd"], "5|assists": [4.5, 2.0, "fd"], "8|points": [24.5, 1.9, "fd"]}})
    # CHI's players who faced WAS, most minutes first; under 10 minutes left out; WAS's own player not listed
    assert [r[3] for r in rows] == [6, 5]
    assert rows[1] == ["2026-10-25", "G1", "CHI", 5, "Coby White", "G", 30, 21, 3, 4, 2,
                       {"points": [18.5, 1.98, "fd"], "assists": [4.5, 2.0, "fd"]}]
    assert rows[0][5] == "C" and rows[0][11] == {}


def test_build_writes_each_team_and_caches_closings():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES "
              "('G1', '2026-27', '2026-10-25', 'WAS', 'CHI', 98, 100), ('G9', '2026-27', '2026-10-26', 'WAS', 'CHI', NULL, NULL)")
    for pid, team, pos in ((5, "CHI", "G"), (6, "CHI", "C"), (8, "WAS", "F")):
        m.execute("INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) "
                  "VALUES ('G1', ?, ?, ?, 1, 30, 10, 5, 3, 1, 0, 0, 1, 10, 3, 2)", (team, pid, pos))
    m.commit()
    bx, out, cache = d / "box", d / "vs", d / "close.json"
    bx.mkdir()
    (bx / "G1.json").write_text(json.dumps(box("G1", "CHI", "WAS")))
    idx = {"5": ["CHI", "Coby White", "G"], "6": ["CHI", "Nikola V", "C"], "8": ["WAS", "Home Guy", "F"]}
    assert VS.build(m, quotes(d), bx, out, cache=cache, idx=idx) == 2
    was = json.loads((out / "WAS.json").read_text())
    assert was["team"] == "WAS" and [r[3] for r in was["rows"]] == [6, 5] and was["rows"][1][11]["points"] == [18.5, 1.98, "fd"]
    assert [r[3] for r in json.loads((out / "CHI.json").read_text())["rows"]] == [8]
    assert json.loads(cache.read_text())["G1"]["5|points"] == [18.5, 1.98, "fd"]           # the final's closings, kept
    assert VS.build(m, None, bx, out, cache=cache, idx=idx) == 2                              # no lines store: the cache serves
    assert json.loads((out / "WAS.json").read_text())["rows"][1][11]["points"] == [18.5, 1.98, "fd"]
