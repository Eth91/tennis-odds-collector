"""nba_pbp: assists and rebounds by court zone from the play-by-play (docs/pbp/{season}.json)."""
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_matchup as MU
import nba_pbp as PB


def shot(n, team, pid, kind, made, x, y, d, ast=None):
    return {"actionNumber": n, "actionType": kind, "teamTricode": team, "personId": pid, "shotResult": "Made" if made else "Missed",
            "xLegacy": x, "yLegacy": y, "shotDistance": d, **({"assistPersonId": ast} if ast else {})}


def test_zones():
    z = lambda kind, x, y, d: PB.zone({"actionType": kind, "xLegacy": x, "yLegacy": y, "shotDistance": d})
    assert z("3pt", -238, 21, 23.9) == 3 and z("3pt", 229, 92, 23.0) == 4 and z("3pt", 40, 250, 25.4) == 5   # left, right, top
    assert z("3pt", -229, 93, 23.1) == 5 and z("3pt", None, None, 24.0) == 5                                   # above the corner
    assert z("2pt", 21, 9, 2.3) == 0 and z("2pt", 50, 100, 11.2) == 1 and z("2pt", 150, 120, 19.2) == 2       # rim, paint, mid
    assert z("2pt", None, None, 9.0) == 1 and z("2pt", None, None, 17.0) == 2                                  # no position: by distance


def test_parse_assists_and_rebounds():
    acts = [shot(1, "BOS", 1, "3pt", True, -238, 21, 23.9, ast=2),         # Tatum's corner three, assisted by White
            shot(2, "BOS", 1, "2pt", True, 5, 5, 0.7),                      # unassisted at the rim
            shot(10, "MIA", 5, "2pt", False, 150, 120, 19.2),               # a missed mid-range jumper...
            {"actionNumber": 11, "actionType": "rebound", "subType": "defensive", "teamTricode": "BOS", "personId": 3, "shotActionNumber": 10},
            {"actionNumber": 20, "actionType": "freethrow", "teamTricode": "BOS", "personId": 1, "shotResult": "Missed"},
            {"actionNumber": 21, "actionType": "rebound", "subType": "offensive", "teamTricode": "BOS", "personId": 4, "shotActionNumber": 20},
            {"actionNumber": 22, "actionType": "rebound", "subType": "defensive", "teamTricode": "MIA", "personId": 0, "shotActionNumber": 20},
            {"actionNumber": 23, "actionType": "rebound", "subType": "defensive", "teamTricode": "MIA", "personId": 6, "shotActionNumber": 99},
            shot(30, "LAL", 9, "2pt", True, 0, 0, 0.0)]                     # not a team in this game
    makes, rebs = PB.parse(acts, "BOS", "MIA")
    assert makes == [("BOS", "MIA", 1, 2, 3, 3), ("BOS", "MIA", 1, None, 0, 2)]
    # off the mid-range miss (zone 2), off the free throw (zone 6); the team rebound and the one with no miss left out
    assert rebs == [("BOS", "MIA", 3, "d", 2), ("BOS", "MIA", 4, "o", PB.FT)]


def test_fetch_and_build():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    m.executemany("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,?,?)",
                  [("g1", "2026-27", "2026-10-22", "BOS", "MIA", 100, 90), ("g2", "2026-27", "2026-10-24", "MIA", "BOS", 99, 98),
                   ("g3", "2026-27", "2026-10-26", "BOS", "MIA", 101, 99), ("g0", "2025-26", "2026-03-01", "BOS", "MIA", 90, 80)])
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) VALUES (?,?,?,?,?,?,0,0,0,0,0,0,0,0,0,0)"
    m.executemany(PG, [(g, "BOS", 2, "G", 1, 30) for g in ("g1", "g2", "g3", "g0")] + [(g, "BOS", 3, "C", 1, 28) for g in ("g1", "g2")])
    m.commit()
    con = PB.connect(d / "pbp.sqlite")
    plays = {"g1": [shot(1, "BOS", 1, "3pt", True, -238, 21, 23.9, ast=2), shot(2, "MIA", 7, "2pt", True, 50, 100, 11.0, ast=8),
                    shot(3, "BOS", 1, "3pt", False, 40, 250, 25.0),
                    {"actionNumber": 4, "actionType": "rebound", "subType": "defensive", "teamTricode": "MIA", "personId": 8, "shotActionNumber": 3}],
             "g2": [shot(1, "BOS", 1, "2pt", True, 5, 5, 0.7, ast=2), shot(2, "MIA", 7, "2pt", False, 150, 120, 19.0),
                    {"actionNumber": 3, "actionType": "rebound", "subType": "defensive", "teamTricode": "BOS", "personId": 3, "shotActionNumber": 2}],
             "g3": [],                                                         # no feed yet: retried next run
             "g0": [shot(1, "BOS", 1, "3pt", True, 40, 250, 25.0, ast=2)]}
    asked = []

    def get(gid):
        asked.append(gid)
        return plays[gid]
    assert PB.fetch(con, m, ("2025-26", "2026-27"), get=get, workers=1) == (3, 1)
    asked.clear()
    assert PB.fetch(con, m, ("2025-26", "2026-27"), get=get, workers=1) == (0, 1) and asked == ["g3"]
    doc = PB.build(con, m, "2026-27")
    # 2 stored games: BOS and MIA 2 games each; assisted makes allowed by zone: BOS gave up MIA's paint basket, MIA BOS's
    # left-corner three and rim basket; rebounds allowed: MIA's player got one off BOS's top-of-the-key miss, BOS's one off
    # MIA's mid miss
    # misses: BOS's top-of-the-key miss (MIA's defensive board), MIA's mid miss (BOS's)
    assert doc["league"] == {"gp": 4, "ast": [1, 1, 0, 1, 0, 0], "reb": [0, 0, 1, 0, 0, 1, 0], "miss": [0, 0, 1, 0, 0, 1, 0]}
    assert doc["teams"]["BOS"] == [2, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0] + [0, 0, 0, 0, 0, 1, 0]
    assert doc["teams"]["MIA"] == [2, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0] + [0, 0, 1, 0, 0, 0, 0]
    # White: 2 games with minutes, assists at the rim and from the left corner; Smith: 2 games, a defensive rebound off a mid miss
    assert doc["players"]["2"] == [2, 1, 0, 0, 1, 0, 0] + [0] * 7 + [0] and doc["players"]["3"][0] == 2 and doc["players"]["3"][1 + 6 + 2] == 1
    assert "8" not in doc["players"]                       # no minutes in the box store: no per-game line, left out
    assert PB.build(con, m, "2025-26")["league"]["ast"] == [0, 0, 0, 0, 0, 1]   # last season stands apart


def test_an_older_store_is_refilled():
    path = pathlib.Path(tempfile.mkdtemp()) / "pbp.sqlite"
    old = sqlite3.connect(path)                            # version 1: the corners together, no user_version
    old.executescript(PB.DDL)
    old.execute("INSERT INTO games VALUES ('g1', '2026-27', '2026-10-22')")
    old.execute("INSERT INTO makes VALUES ('g1', 'BOS', 'MIA', 1, 2, 3, 3)")
    old.commit()
    old.close()
    con = PB.connect(path)
    assert con.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0 and con.execute("SELECT COUNT(*) FROM makes").fetchone()[0] == 0
    assert con.execute("PRAGMA user_version").fetchone()[0] == PB.VERSION
    con.execute("INSERT INTO games VALUES ('g1', '2026-27', '2026-10-22')")
    con.commit()
    con.close()
    assert PB.connect(path).execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1          # a current store is kept


def test_misses_go_to_the_shooters_team():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES ('g1', '2026-27', '2026-10-22', 'BOS', 'MIA', 100, 90)")
    m.commit()
    con = PB.connect(d / "p.sqlite")
    con.execute("INSERT INTO games VALUES ('g1', '2026-27', '2026-10-22')")
    # a Celtic's offensive board off a Celtics miss from the top; his defensive board off a Heat miss at the rim
    con.executemany("INSERT INTO rebs VALUES (?,?,?,?,?,?)", [("g1", "BOS", "MIA", 3, "o", 5), ("g1", "BOS", "MIA", 3, "d", 0)])
    doc = PB.build(con, m, "2026-27")
    assert doc["teams"]["BOS"][-7:] == [0, 0, 0, 0, 0, 1, 0] and doc["teams"]["MIA"][-7:] == [1, 0, 0, 0, 0, 0, 0]
    assert doc["teams"]["MIA"][1 + 6:1 + 6 + 7] == [1, 0, 0, 0, 0, 1, 0]      # both boards were Celtics': MIA allowed them
