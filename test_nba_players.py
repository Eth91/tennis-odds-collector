"""nba_players: every player's page data, prop or not (docs/player/{pid}.json and the searchable index)."""
import json
import pathlib
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
    m.commit()
    idx = {"1": ["MIN", "Aye One", "F"], "2": ["MIN", "Bee Two", "G"], "3": ["MIN", "Reg Three", "C"], "4": ["MIN", "Cee Four", "F"]}
    PL.build(m, d / "player", idx, "2026-27")
    rows = json.loads((d / "player" / "roles.json").read_text())["rows"]
    assert [r["pid"] for r in rows] == [1]          # not B (steady), not R (out, no recent games), not C (not lately)
    a = rows[0]
    assert a["d_min"] == 15.0 and a["min"] == [30.0, 15.0] and a["starts"] == [3, 0, 5] and a["base"] == "this season"
    assert a["out"] == ["Reg Three", "Cee Four"]      # the regulars who sat 2+ of the team's last 3
