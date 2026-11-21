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


def test_roles_last_3_games_against_the_season_average_once_the_season_has_games():
    # the median team has 8 games: past the switch to "recent" (RECENT_FROM); each last 3 against his season average
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
        # E: the same 30 minutes, but 8 more shots, 4 more threes and (tracking) 4 more potential assists lately
        m.execute(PG, (gid, "MIN", 5, "G", 1, 30, 14, 3, 4, 2, 0, 0, 1, 18 if late else 10, 8 if late else 4, 2))
        # G: 4 games, 10 -> 30 minutes: short of the SEASON_MIN_GP a season average needs. H: 5 games, the same: enough
        if i >= 4:
            m.execute(PG, (gid, "MIN", 7, "G", int(late), 30 if late else 10, 8, 2, 2, 1, 0, 0, 1, 8, 3, 1))
        if i >= 3:
            m.execute(PG, (gid, "MIN", 8, "G", int(late), 30 if late else 10, 8, 2, 2, 1, 0, 0, 1, 8, 3, 1))
        # D: 20 -> 26 minutes: 6 over the games before his last 3, but 3.75 over his season average (22.25): not listed
        m.execute(PG, (gid, "MIN", 9, "F", 0, 26 if late else 20, 8, 3, 1, 1, 0, 0, 1, 7, 2, 1))
        # F: new this season (3 games): too few of his own to compare his last 3 with (no last-season fallback here)
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
           "5": ["MIN", "Eee Five", "G"], "6": ["MIN", "Eff Six", "F"], "7": ["MIN", "Gee Seven", "G"],
           "8": ["MIN", "Aitch Eight", "G"], "9": ["MIN", "Dee Nine", "F"]}
    PL.build(m, d / "player", idx, "2026-27", tr)
    doc = json.loads((d / "player" / "roles.json").read_text())
    rows, th = doc["rows"], doc["thresholds"]
    assert doc["mode"] == "recent" and th == PL.ROLE_MOVE
    # not B (steady), R (out lately), C (not lately), F (3 games), G (4 games), D (under 4 over his season average)
    assert [r["pid"] for r in rows] == [1, 8, 5]
    moved = lambda k: [r["pid"] for r in rows if r["st"][k] and abs(r["st"][k][0] - r["st"][k][1]) >= th[k]]
    assert moved("min") == [1, 8] and moved("fga") == [5] and moved("fg3a") == [5] and moved("pot_ast") == [5] and moved("reb_ch") == []
    e = next(r for r in rows if r["pid"] == 5)
    assert e["st"]["fga"] == [18.0, 13.0] and e["st"]["fg3a"] == [8.0, 5.5] and e["st"]["pot_ast"] == [9.0, 5.0] and e["st"]["reb_ch"] == [6.0, 6.0]
    assert rows[0]["st"]["pot_ast"] is None                                  # 1 tracked recent game: left out, not a move
    a = rows[0]
    # 30 a game lately against 20.6 over his 8 (15 x 5, 30 x 3); his starts against the 5 games before his last 3
    assert a["d_min"] == 9.4 and a["min"] == [30.0, 20.6] and a["starts"] == [3, 0, 5, 3] and a["base"] == "this season"
    assert a["out"] == ["Reg Three", "Cee Four"] and a["was_team"] is None    # the regulars who sat 2+ of the team's last 3
    h = rows[1]
    assert h["min"] == [30.0, 22.0] and h["d_min"] == 8.0 and h["starts"] == [3, 0, 2, 3]


def test_roles_this_season_against_last_early_on():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) " \
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    G = "INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,100,90)"
    for i in range(12):                                      # last season: 12 MIN games and 12 ATL games
        m.execute(G, (f"m{i}", "2025-26", f"2026-01-{i + 1:02d}", "MIN", "WAS"))
        m.execute(G, (f"a{i}", "2025-26", f"2026-02-{i + 1:02d}", "ATL", "BOS"))
        m.execute(PG, (f"m{i}", "MIN", 1, "F", 0, 20, 8, 4, 2, 1, 0, 0, 1, 7, 2, 1))       # P1: a bench player last season
        m.execute(PG, (f"a{i}", "ATL", 2, "G", 0, 15, 6, 2, 2, 1, 0, 0, 1, 5, 2, 1))       # P2: in Atlanta last season
        m.execute(PG, (f"m{i}", "MIN", 3, "G", 1, 30, 15, 4, 4, 2, 0, 0, 1, 12, 5, 3))     # P3: the same 30 minutes
        if i < 6:
            m.execute(PG, (f"m{i}", "MIN", 4, "C", 0, 10, 4, 4, 0, 0, 0, 0, 0, 3, 0, 1))   # P4: 6 games: too few to compare
    for i in range(4):                                       # this season: 4 games each, under the switch to "recent"
        m.execute(G, (f"g{i}", "2026-27", f"2026-10-{21 + i}", "MIN", "WAS"))
        m.execute(PG, (f"g{i}", "MIN", 1, "F", 1, 31, 15, 6, 3, 2, 0, 0, 1, 12, 4, 3))     # P1: starting, 31 minutes
        m.execute(PG, (f"g{i}", "MIN", 2, "G", 1, 30, 14, 3, 5, 2, 0, 0, 1, 12, 5, 2))     # P2: a Timberwolf now
        m.execute(PG, (f"g{i}", "MIN", 3, "G", 1, 30, 15, 4, 4, 2, 0, 0, 1, 12, 5, 3))
        m.execute(PG, (f"g{i}", "MIN", 4, "C", 1, 28, 12, 9, 1, 0, 0, 1, 1, 9, 0, 3))
    m.commit()
    tr = sqlite3.connect(d / "trk.sqlite")
    tr.execute("CREATE TABLE tracking (date TEXT, player_id INTEGER, potential_ast REAL, reb_chances REAL)")
    tr.executemany("INSERT INTO tracking VALUES (?,?,?,?)", [(f"2026-01-{i + 1:02d}", 1, 3, 5) for i in range(12)] +
                   [(f"2026-10-{21 + i}", 1, 8, 9) for i in range(4)])
    tr.commit()
    idx = {"1": ["MIN", "Pee One", "F"], "2": ["MIN", "Pee Two", "G"], "3": ["MIN", "Pee Three", "G"], "4": ["MIN", "Pee Four", "C"]}
    PL.build(m, d / "player", idx, "2026-27", tr)
    doc = json.loads((d / "player" / "roles.json").read_text())
    rows = {r["pid"]: r for r in doc["rows"]}
    assert doc["mode"] == "season" and sorted(rows) == [1, 2]        # not P3 (steady), not P4 (6 games last season)
    p1, p2 = rows[1], rows[2]
    assert p1["base"] == "last season" and p1["min"] == [31.0, 20.0] and p1["starts"] == [4, 0, 12, 4] and p1["was_team"] is None
    # potential assists compare across seasons; rebound chances don't (the NBA counts them differently this season)
    assert p1["st"]["pot_ast"] == [8.0, 3.0] and p1["st"]["reb_ch"] is None
    assert p2["was_team"] == "ATL" and p2["st"]["min"] == [30.0, 15.0] and p2["st"]["fga"] == [12.0, 5.0]   # a new team


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


def test_roles_only_players_with_a_line_this_season():
    d = pathlib.Path(tempfile.mkdtemp())
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    q.executemany("INSERT INTO quotes VALUES (?, 'fd', 'g', '', ?, '', 'points', 10.5, 'over', 1.9)",
                  [("2026-10-23T01:00:00", 1), ("2026-10-24T01:00:00", 1), ("2026-04-01T01:00:00", 2), ("2026-10-23T01:00:00", None)])
    assert PL.lined_players(q, "2026-27") == {1}           # 2 only had lines last season; an unmatched quote is skipped
    m = MU.connect(d / "m.sqlite")
    PG = "INSERT INTO player_games (gid, team, pid, pos, starter, min, pts, reb, ast, fg3m, stl, blk, tov, fga, fg3a, fta) " \
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    for i in range(12):
        m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,100,90)",
                  (f"m{i}", "2025-26", f"2026-01-{i + 1:02d}", "MIN", "WAS"))
        for pid in (1, 2):
            m.execute(PG, (f"m{i}", "MIN", pid, "F", 0, 15, 6, 3, 1, 1, 0, 0, 1, 6, 2, 1))
    for i in range(4):
        m.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,100,90)",
                  (f"g{i}", "2026-27", f"2026-10-{21 + i}", "MIN", "WAS"))
        for pid in (1, 2):
            m.execute(PG, (f"g{i}", "MIN", pid, "F", 1, 30, 14, 6, 3, 2, 0, 0, 1, 12, 4, 3))     # both up 15 minutes
    m.commit()
    idx = {"1": ["MIN", "Has Line", "F"], "2": ["MIN", "No Line", "F"]}
    PL.build(m, d / "player", idx, "2026-27", lined=PL.lined_players(q, "2026-27"))
    assert [r["pid"] for r in json.loads((d / "player" / "roles.json").read_text())["rows"]] == [1]
    PL.build(m, d / "player", idx, "2026-27")                                      # no lines store: everyone
    assert sorted(r["pid"] for r in json.loads((d / "player" / "roles.json").read_text())["rows"]) == [1, 2]


def test_roles_switch_to_the_last_3_games_when_the_median_team_has_5():
    assert PL.roles_mode({"MIN": list(range(5)), "WAS": list(range(5)), "ATL": list(range(4))}) == "recent"
    assert PL.roles_mode({"MIN": list(range(4)), "WAS": list(range(4)), "ATL": list(range(5))}) == "season"
    assert PL.roles_mode({}) == "season"
