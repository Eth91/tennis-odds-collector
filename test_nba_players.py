"""nba_players: every player's page data, prop or not (docs/player/{pid}.json and the searchable index)."""
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_matchup as MU
import nba_players as PL
import nba_research as R


def test_build_writes_each_player_with_games_and_the_index():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) " \
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    for i, (gid, season, date) in enumerate((("a1", "2025-26", "2026-03-01"), ("b1", "2026-27", "2026-10-22"),
                                             ("b2", "2026-27", "2026-10-24"))):
        m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,100,90)",
                  (gid, season, date, "MIN", "WAS"))
        m.execute(PG, (gid, "MIN", 1, "C", 1, 30 + i, 15 + i, 7, 2, 1, 1, 1, 2, 12, 3, 4))
    m.commit()
    idx = {"1": ["MIN", "Naz Reid", "F-C"], "2": ["MIN", "No Games", "G"]}
    assert PL.build(m, d / "player", idx, "2026-27") == 1
    doc = json.loads((d / "player" / "1.json").read_text())
    assert doc["name"] == "Naz Reid" and doc["team"] == "MIN" and doc["pos"] == "F-C" and len(doc["logs"]) == 3
    # the same rows a prop's page charts (nba_research.game_logs): LOG_COLS order, oldest first, rest days filled
    assert [dict(zip(R.LOG_COLS, r))["pts"] for r in doc["logs"]] == [15, 16, 17]
    assert dict(zip(R.LOG_COLS, doc["logs"][2]))["rest"] == 1
    ix = json.loads((d / "player" / "index.json").read_text())
    assert ix["log_cols"] == list(R.LOG_COLS) and ix["players"] == [[1, "Naz Reid", "MIN", "F-C"]]   # no games: not listed
    assert not (d / "player" / "2.json").exists() and not list((d / "player").glob(".*.tmp"))


def test_roles_finds_minute_jumps_and_why():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) " \
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    for i in range(8):
        gid = f"g{i}"
        m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,100,90)",
                  (gid, "2026-27", f"2026-10-{21 + i}", "MIN", "WAS"))
        late = i >= 5                                                   # the last 3 games
        m.execute(PG, (gid, "MIN", 1, "", int(late), 30 if late else 15, 12, 4, 2, 1, 0, 0, 1, 10, 3, 2))   # A: up 15
        m.execute(PG, (gid, "MIN", 2, "G", 1, 33, 20, 4, 6, 2, 1, 0, 2, 16, 6, 4))                        # B: steady
        if not late:
            m.execute(PG, (gid, "MIN", 3, "C", 1, 32, 18, 10, 2, 0, 1, 2, 2, 13, 0, 5))                   # R: out lately
        if i < 6:
            m.execute(PG, (gid, "MIN", 4, "", 0, 20 if i < 3 else 28, 8, 3, 1, 1, 0, 0, 1, 7, 2, 1))       # C: gone lately
        # E: the same 30 minutes, but 6 more shots, 3 more threes and (tracking) 4 more potential assists lately
        m.execute(PG, (gid, "MIN", 5, "G", 1, 30, 14, 3, 4, 2, 0, 0, 1, 16 if late else 10, 7 if late else 4, 2))
        # F: new this season (3 games), so his baseline is last season's games for MIN
        if late:
            m.execute(PG, (gid, "MIN", 6, "F", 1, 30, 12, 9, 2, 1, 0, 0, 1, 12, 3, 2))
    for i in range(5):
        m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,100,90)",
                  (f"p{i}", "2025-26", f"2026-03-0{i + 1}", "MIN", "WAS"))
        m.execute(PG, (f"p{i}", "MIN", 6, "F", 1, 20, 6, 4, 1, 0, 0, 0, 1, 6, 1, 1))
    m.commit()
    tr = sqlite3.connect(d / "trk.sqlite")
    tr.execute("CREATE TABLE tracking (date TEXT, player_id INTEGER, potential_ast REAL, reb_chances REAL)")
    tr.executemany("INSERT INTO tracking VALUES (?,?,?,?)", [(f"2026-10-{21 + i}", 5, 9 if i >= 5 else 5, 6) for i in range(8)])
    # A: tracked in his first 5 games but only 1 of his last 3: too few to say his potential assists moved
    tr.executemany("INSERT INTO tracking VALUES (?,?,?,?)", [(f"2026-10-{21 + i}", 1, 2 if i < 5 else 9, 3) for i in (0, 1, 2, 3, 4, 7)])
    tr.executemany("INSERT INTO tracking VALUES (?,?,?,?)", [(f"2026-03-0{i + 1}", 6, 2, 6) for i in range(5)] +
                   [(f"2026-10-{21 + i}", 6, 6, 18) for i in (5, 6, 7)])
    tr.commit()
    idx = {"1": ["MIN", "Aye One", "F"], "2": ["MIN", "Bee Two", "G"], "3": ["MIN", "Reg Three", "C"], "4": ["MIN", "Cee Four", "F"],
           "5": ["MIN", "Eee Five", "G"], "6": ["MIN", "Eff Six", "F"]}
    PL.build(m, d / "player", idx, "2026-27", tr)
    doc = json.loads((d / "player" / "roles.json").read_text())
    rows, th = doc["rows"], doc["thresholds"]
    assert th == PL.ROLE_MOVE and [r["pid"] for r in rows] == [1, 6, 5]   # not B (steady), R (out lately), C (not lately)
    moved = lambda k: [r["pid"] for r in rows if r["st"][k] and abs(r["st"][k][0] - r["st"][k][1]) >= th[k]]
    assert moved("min") == [1, 6] and moved("fga") == [6, 5] and moved("fg3a") == [6, 5] and moved("pot_ast") == [6, 5] and moved("reb_ch") == []
    f = next(r for r in rows if r["pid"] == 6)
    # against last season: potential assists compare (the same count both seasons), rebound chances don't (counted differently now)
    assert f["base"] == "last season" and f["st"]["pot_ast"] == [6.0, 2.0] and f["st"]["reb_ch"] is None
    e = next(r for r in rows if r["pid"] == 5)
    assert e["st"]["fga"] == [16.0, 10.0] and e["st"]["fg3a"] == [7.0, 4.0] and e["st"]["pot_ast"] == [9.0, 5.0] and e["st"]["reb_ch"] == [6.0, 6.0]
    assert rows[0]["st"]["pot_ast"] is None                                  # 1 tracked recent game: left out, not a move
    a = rows[0]
    assert a["d_min"] == 15.0 and a["min"] == [30.0, 15.0] and a["starts"] == [3, 0, 5] and a["base"] == "this season"
    assert a["out"] == ["Reg Three", "Cee Four"]      # the regulars who sat 2+ of the team's last 3


def test_game_logs_drop_impossible_tracking_values():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    for i, mn in enumerate((30, 30, 3)):
        m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,100,90)",
                  (f"g{i}", "2026-27", f"2026-10-2{i}", "MIN", "WAS"))
        m.execute("INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (f"g{i}", "MIN", 7, "G", 1, mn, 10, 5, 5, 1, 0, 0, 1, 10, 4, 2))
    m.commit()
    tr = sqlite3.connect(d / "trk.sqlite")
    tr.execute("CREATE TABLE tracking (date TEXT, player_id INTEGER, potential_ast REAL, reb_chances REAL)")
    # a real night; a stored season total (517 in 30 minutes); a 3-minute cameo (too few minutes to judge, kept)
    tr.executemany("INSERT INTO tracking VALUES (?,?,?,?)", [("2026-10-20", 7, 12, 14), ("2026-10-21", 7, 517, 45), ("2026-10-22", 7, 4, 5)])
    tr.commit()
    C = {c: k for k, c in enumerate(R.LOG_COLS)}
    logs = R.game_logs(m, [7], ("2026-27",), tr)[7]
    assert [(l[C["pot_ast"]], l[C["reb_ch"]]) for l in logs] == [(12, 14), (None, None), (4, 5)]   # 45 / 30 min > 1.4 too
