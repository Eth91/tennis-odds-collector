"""nba_onoff: who was on the court, from the play-by-play (docs/onoff/{TEAM}.json)."""
import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_onoff as O
import nba_research_ui as UI

NODE = shutil.which("node")
A, B = (1, 2, 3, 4, 5, 6), (11, 12, 13, 14, 15)
TEAM = {**{p: "AAA" for p in A}, **{p: "BBB" for p in B}}
START = [1, 2, 3, 4, 5, 11, 12, 13, 14, 15]


def act(n, period, clock, kind, pid=None, sub=None, **kw):
    a = {"actionNumber": n, "orderNumber": n, "period": period, "clock": clock, "actionType": kind, "subType": sub,
         "personId": pid, "personIdsFilter": [pid] if pid else []}
    a.update(kw)
    return a


def game():
    """Two periods. Q1: 1's three (2 assists), 5 out for 6 at 6:00 after 1's free throw at 6:00, 6's two and 11's free
    throw at 4:00, 3's offensive rebound. Q2: 1 misses, 4 out for 5 at 11:00; 2, 3 and 6 never show up (the five who
    ended Q1 stand in), nor does BBB."""
    acts = [act(1, 1, "PT12M00.00S", "period", sub="start"),
            act(2, 1, "PT10M00.00S", "3pt", 1, shotResult="Made", assistPersonId=2, personIdsFilter=[1, 2]),
            act(51, 1, "PT06M00.00S", "substitution", 5, sub="out"),
            act(52, 1, "PT06M00.00S", "substitution", 6, sub="in"),
            act(60, 1, "PT04M00.00S", "2pt", 6, shotResult="Made"),
            act(61, 1, "PT04M00.00S", "freethrow", 11, sub="1 of 1", shotResult="Made"),
            act(62, 1, "PT03M00.00S", "rebound", 3, sub="offensive"),
            act(63, 1, "PT00M00.00S", "period", sub="end"),
            act(70, 2, "PT12M00.00S", "period", sub="start"),
            act(71, 2, "PT11M30.00S", "2pt", 1, shotResult="Missed"),
            act(72, 2, "PT11M00.00S", "substitution", 4, sub="out"),
            act(73, 2, "PT11M00.00S", "substitution", 5, sub="in"),
            act(80, 2, "PT00M00.00S", "period", sub="end"),
            act(81, 2, "PT00M00.00S", "game", sub="end"),
            act(49, 1, "PT06M00.00S", "freethrow", 1, sub="1 of 1", shotResult="Made")]   # edited in late: order 49
    return acts


def test_parse_follows_the_five_on_the_court():
    units, secs = O.parse(game(), TEAM, START)
    assert {k: round(v[0]) for k, v in units.items()} == {("AAA", (1, 2, 3, 4, 5)): 360, ("AAA", (1, 2, 3, 4, 6)): 420,
                                                          ("AAA", (1, 2, 3, 5, 6)): 660, ("BBB", B): 1440}
    assert round(secs[1]) == 1440 and round(secs[4]) == 780 and round(secs[5]) == 1020 and round(secs[6]) == 1080
    first, second = units[("AAA", (1, 2, 3, 4, 5))], units[("AAA", (1, 2, 3, 4, 6))]
    assert first[1:3] == [4, 0] and second[1:3] == [2, 1]          # the free throw at 6:00 came before the sub
    s = lambda u, p: dict(zip(O.STATS, u[3][p]))
    assert s(first, 1)["pts"] == 4 and s(first, 1)["fg3m"] == 1 and s(first, 1)["fga"] == 1 and s(first, 1)["fta"] == 1
    assert s(first, 2)["ast"] == 1 and s(second, 6)["pts"] == 2 and s(second, 3)["reb"] == 1 and s(second, 3)["oreb"] == 1
    assert units[("BBB", B)][1:3] == [1, 6]
    assert s(units[("AAA", (1, 2, 3, 4, 6))], 1)["fga"] == 1       # Q2's miss, before 4 went out


def test_a_period_without_five_is_unreadable():
    with pytest.raises(O.Unreadable):
        O.parse(game(), TEAM, [1, 2, 3, 4, 11, 12, 13, 14, 15])     # four AAA starters
    with pytest.raises(O.Unreadable):
        O.parse(game(), {p: "AAA" for p in A}, START)                # one team in the box score


def _stores():
    con = O.connect(":memory:")
    mcon = sqlite3.connect(":memory:")
    mcon.execute("CREATE TABLE games (gid TEXT, season TEXT, date TEXT, home TEXT, away TEXT, home_pts INTEGER, away_pts INTEGER)")
    mcon.execute("CREATE TABLE player_games (gid TEXT, team TEXT, pid INTEGER, starter INTEGER)")
    for gid, d in (("g1", "2026-10-22"), ("g2", "2026-10-24"), ("g3", "2026-10-26"), ("g4", "2026-10-28")):
        mcon.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'AAA', 'BBB', 100, 90)", (gid, d))
        for p in A + B:
            starter = p in START and not (gid == "g3" and p == 5)
            mcon.execute("INSERT INTO player_games VALUES (?, ?, ?, ?)", (gid, TEAM[p], p, int(starter)))
    mcon.execute("INSERT INTO games VALUES ('g5', '2026-27', '2026-10-30', 'AAA', 'BBB', NULL, NULL)")   # not final
    return con, mcon


def test_fetch_stores_each_final_game_once_and_build_sums_the_lineups():
    con, mcon = _stores()
    asked = []

    def get(gid):
        asked.append(gid)
        if gid == "g2":
            return [a for a in game() if a["actionType"] != "game"]         # the feed not at its end yet
        return game()
    assert O.fetch(con, mcon, "2026-27", get, workers=1, today="2026-10-24") == (3, 1, 1)   # g3: four AAA starters
    assert sorted(asked) == ["g1", "g2", "g3", "g4"]
    assert con.execute("SELECT gid, ok FROM games ORDER BY gid").fetchall() == [("g1", 1), ("g3", 0), ("g4", 1)]
    asked.clear()
    assert O.fetch(con, mcon, "2026-27", get, workers=1, today="2026-10-24") == (0, 1, 0) and asked == ["g2"]   # only g2 again
    # a feed that never gets its game end: from the next day, its last period's end will do (a 4th or later)
    four = [act(100 + 2 * q, q, c, "period", sub=e) for q in (1, 2, 3, 4) for c, e in (("PT12M00.00S", "start"), ("PT00M00.00S", "end"))]
    assert O.complete(four, "2026-10-24", "2026-10-25") and not O.complete(four, "2026-10-24", "2026-10-24")
    assert not O.complete(four[:-1], "2026-10-24", "2026-10-25")                       # the 4th not over
    assert not O.complete(four + [act(200, 5, "PT05M00.00S", "period", sub="start")], "2026-10-24", "2026-10-25")   # overtime on
    docs = O.build(con, "2026-27")
    a = docs["AAA"]
    assert a["games"] == 2 and a["stats"] == list(O.STATS) and a["gp"]["5"] == 2 and a["gp"]["1"] == 2
    assert [(L[0], L[1], L[2], L[3]) for L in a["lineups"]] == [([1, 2, 3, 5, 6], 1320, 0, 0), ([1, 2, 3, 4, 6], 840, 4, 2),
                                                                ([1, 2, 3, 4, 5], 720, 8, 0)]
    assert a["lineups"][2][4][0][O.S["pts"]] == 8                         # 1's points with that five, over the 2 games
    with tempfile.TemporaryDirectory() as d:
        O.write(d, docs)
        assert json.loads((pathlib.Path(d) / "BBB.json").read_text())["lineups"][0][:4] == [list(B), 2880, 2, 12]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_wowy_split_sums_a_player_with_and_without_a_teammate():
    lineups = [[[1, 2, 3, 4, 5], 600, 20, 10, [[10, 1], [4, 2], [0, 0], [0, 0], [0, 0]]],
               [[1, 2, 3, 4, 6], 300, 6, 9, [[9, 0], [1, 1], [0, 0], [0, 0], [2, 0]]],
               [[2, 3, 4, 5, 6], 120, 2, 2, [[3, 3], [0, 0], [0, 0], [0, 0], [0, 0]]]]
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "core.js").write_text(UI.JS_CORE)
    (d / "t.js").write_text("const C = require('./core.js');\nconsole.log(JSON.stringify(C.wowySplit(%s, 5, 2)));" % json.dumps(lineups))
    out = json.loads(subprocess.run([NODE, str(d / "t.js")], capture_output=True, text=True, check=True, cwd=d).stdout)
    assert out["team"] == {"on": [720, 22, 12], "off": [300, 6, 9]}
    assert out["players"]["1"] == {"on": [600, [10, 1]], "off": [300, [9, 0]]}
    assert out["players"]["2"] == {"on": [720, [7, 5]], "off": [300, [1, 1]]}
    assert out["players"]["5"]["off"][0] == 0                                         # his own time: all "on"
