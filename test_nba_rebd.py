"""nba_rebd: how far from the hoop each player secures his rebounds (docs/rebd/{season}.json)."""
import datetime as dt
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_rebd as RB

H = ["PLAYER_ID", "G", "REB", "OREB", "C_REB"]


def resp(g, reb, oreb, creb, dist, shot, miss3):
    rs = lambda name, col, labels, vals: {"name": name, "headers": ["PLAYER_ID", "G", col, "REB"],
                                          "rowSet": [[1, g, lab, v] for lab, v in zip(labels, vals)]}
    return {"resultSets": [{"name": "OverallRebounding", "headers": H, "rowSet": [[1, g, reb, oreb, creb]]},
                           rs("ShotTypeRebounding", "SHOT_TYPE_RANGE", ("Miss 2FG", "Miss 3FG"), (reb - miss3, miss3)),
                           rs("ShotDistanceRebounding", "SHOT_DIST_RANGE", RB.SHOT, shot),
                           rs("RebDistanceRebounding", "REB_DIST_RANGE", RB.DIST, dist)]}


def team_resp(*rows):
    """A teamdashptreb (TeamID=0, OpponentTeamID) response: a row for each team that played the opponent."""
    js = [resp(*r)["resultSets"] for r in rows]
    return {"resultSets": [dict(js[0][k], rowSet=[x for j in js for x in j[k]["rowSet"]]) for k in range(len(js[0]))]}


def test_row_of():
    assert RB.row_of(resp(70, 737, 265, 341, (352, 256, 79, 50), (152, 135, 44, 353), 335)) == \
        [70, 737, 265, 341, 352, 256, 79, 50, 152, 135, 44, 353, 335]
    assert RB.row_of({"resultSets": [{"name": "OverallRebounding", "headers": H, "rowSet": []}]}) is None     # a rookie, last season
    part = resp(3, 10, 2, 4, (5, 3, 2), (6, 4), 1)                    # a range with no boards is left out of NBA.com's rows
    assert RB.row_of(part)[4:12] == [5, 3, 2, 0, 6, 4, 0, 0]
    # a team's opponents: every team's rows summed, a range one of them lacks included
    both = team_resp((2, 90, 20, 30, (25, 30, 20, 15), (20, 15, 15, 40), 35), (1, 40, 12, 18, (12, 14, 9), (10, 8, 6, 16), 15))
    assert RB.row_of(both) == [3, 130, 32, 48, 37, 44, 29, 15, 30, 23, 21, 56, 50]
    assert "teamdashptreb?TeamID=0&" in RB.OPP_URL and "OpponentTeamID={pid}" in RB.OPP_URL and "PlayerID" not in RB.OPP_URL


def test_due_fetch_and_build():
    con = sqlite3.connect(":memory:")
    con.executescript(RB.DDL)
    now = dt.datetime(2026, 10, 28, 12, tzinfo=dt.timezone.utc)
    answers = {1: resp(4, 40, 10, 18, (20, 10, 6, 4), (10, 10, 5, 15), 14), 2: resp(4, 20, 2, 6, (4, 6, 6, 4), (2, 4, 4, 10), 9),
               3: {"resultSets": [{"name": "OverallRebounding", "headers": H, "rowSet": []}]}}
    asked = []

    def get(url):
        pid = int(url.split("PlayerID=")[1].split("&")[0])
        asked.append(pid)
        if pid == 9:
            raise RuntimeError("refused")
        return answers[pid]
    todo = [(1, "2026-27", 4), (2, "2026-27", 5), (3, "2025-26", None), (9, "2026-27", 1)]
    assert RB.fetch(con, todo, get, now, pace=0) == (3, 1)
    # last season: once, a rookie's empty answer included; this season: after a new game, or NBA.com's count trailing
    assert not RB.due(con, 3, "2025-26", None, now) and RB.due(con, 3, "2024-25", None, now)
    assert not RB.due(con, 1, "2026-27", 4, now) and RB.due(con, 1, "2026-27", 5, now)
    assert not RB.due(con, 2, "2026-27", 5, now + dt.timedelta(hours=2))          # 4 of 5 games posted: not every run...
    assert RB.due(con, 2, "2026-27", 5, now + dt.timedelta(hours=3))              # ...but every 3 hours
    assert RB.due(con, 9, "2026-27", 1, now)                                      # a failed call is asked again
    doc = RB.build(con, "2026-27", now)
    assert doc["players"]["1"] == [4, 40, 10, 18, 20, 10, 6, 4, 10, 10, 5, 15, 14] and set(doc["players"]) == {"1", "2"}
    # shares of all 60 rebounds: 24 at 0-3 ft, 16 / 12 / 8 further out; 24 contested; 23 off threes
    assert doc["avg"] == {"dist": [0.4, 0.2667, 0.2, 0.1333], "shot": [0.2, 0.2333, 0.15, 0.4167], "contested": 0.4, "miss3": 0.3833}
    assert RB.build(con, "2025-26", now)["players"] == {} and doc["teams"] == {}


def test_teams_are_their_opponents_rebounds():
    con = sqlite3.connect(":memory:")
    con.executescript(RB.DDL)
    now = dt.datetime(2026, 10, 28, 12, tzinfo=dt.timezone.utc)
    urls = []

    def get(url):
        urls.append(url)
        return team_resp((2, 90, 20, 30, (25, 30, 20, 15), (20, 15, 15, 40), 35), (1, 40, 12, 18, (12, 14, 9, 5), (10, 8, 6, 16), 15))
    assert RB.fetch(con, [(1610612738, "2026-27", 3)], get, now, pace=0, table="opp") == (1, 0)
    assert "OpponentTeamID=1610612738" in urls[0] and "teamdashptreb" in urls[0]
    assert con.execute("SELECT COUNT(*) FROM reb").fetchone()[0] == 0         # kept apart from the players
    assert not RB.due(con, 1610612738, "2026-27", 3, now, "opp") and RB.due(con, 1610612738, "2026-27", 4, now, "opp")
    assert RB.due(con, 1610612738, "2026-27", 3, now) and RB.due(con, 1610612752, "2026-27", 3, now, "opp")
    doc = RB.build(con, "2026-27", now, {1610612738: "BOS", 1610612752: "NYK"})
    assert doc["teams"] == {"BOS": [3, 130, 32, 48, 37, 44, 29, 20, 30, 23, 21, 56, 50]} and doc["players"] == {}


def test_targets_are_rebound_lines_only():
    p = pathlib.Path(tempfile.mkdtemp()) / "props.json"
    p.write_text(json.dumps({"props": [{"pid": 1, "market": "rebounds"}, {"pid": 2, "market": "points"}, {"pid": 3, "market": "pra"},
                                       {"pid": 1, "market": "pts_reb"}, {"pid": 4, "market": "assists"}, {"pid": 5, "market": "reb_ast"}]}))
    assert RB.targets(p) == [1, 3, 5]
