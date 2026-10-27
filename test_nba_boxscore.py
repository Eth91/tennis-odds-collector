"""nba_boxscore: one small box score per final game for the props page (docs/box/{gid}.json)."""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_boxscore as BX
import nba_matchup as MU


def player(pid, name, starter, minutes, pts, played="1", desc=None, **kw):
    s = {"minutes": minutes, "points": pts, "reboundsTotal": kw.get("reb", 0), "assists": kw.get("ast", 0),
         "fieldGoalsMade": kw.get("fgm", 0), "fieldGoalsAttempted": kw.get("fga", 0), "threePointersMade": 0,
         "threePointersAttempted": 0, "freeThrowsMade": 0, "freeThrowsAttempted": 0, "steals": 0, "blocks": 0,
         "turnovers": 0, "foulsPersonal": 0, "plusMinusPoints": kw.get("pm", 0)}
    return {"personId": pid, "name": name, "starter": "1" if starter else "0", "played": played, "statistics": s,
            "notPlayingDescription": desc}


def game(gid="0022600112", status=3):
    tot = lambda pts: {"points": pts, "reboundsTotal": 40, "assists": 20, "fieldGoalsMade": 40, "fieldGoalsAttempted": 85,
                       "threePointersMade": 12, "threePointersAttempted": 33, "freeThrowsMade": 18, "freeThrowsAttempted": 22,
                       "steals": 7, "blocks": 4, "turnovers": 13, "foulsPersonal": 19}
    return {"gameId": gid, "gameStatus": status, "gameStatusText": "Final/OT", "gameTimeUTC": "2026-10-26T02:00:00Z",
            "awayTeam": {"teamTricode": "LAL", "score": 132, "statistics": tot(132),
                         "players": [player(1, "Away Starter", 1, "PT36M30.00S", 30, reb=9, ast=7, fgm=11, fga=20, pm=6),
                                     player(2, "Away Sitter", 0, "PT00M00.00S", 0, played="0", desc="Left Ankle; Sprain")]},
            "homeTeam": {"teamTricode": "UTA", "score": 123, "statistics": tot(123),
                         "players": [player(3, "Home Bench", 0, "PT12M10.00S", 4, pm=-6),
                                     player(4, "Home Coach DNP", 0, "", 0, played="0")]}}


def test_compact_box():
    b = BX.compact(game())
    assert b["gid"] == "0022600112" and b["status"] == "Final/OT" and b["date"] == "2026-10-25"   # ET date of a 10 PM tip
    away, home = b["teams"]
    assert (away["tri"], away["pts"], away["home"], home["tri"], home["home"]) == ("LAL", 132, False, "UTA", True)
    assert away["players"] == [[1, "Away Starter", 1, 37, 30, 9, 7, 11, 20, 0, 0, 0, 0, 0, 0, 0, 0, 6]]
    assert home["players"][0][:5] == [3, "Home Bench", 0, 12, 4] and home["players"][0][-1] == -6
    assert away["dnp"] == [["Away Sitter", "Left Ankle; Sprain"]] and home["dnp"] == [["Home Coach DNP", "DNP"]]
    assert away["tot"] == [132, 40, 20, 40, 85, 12, 33, 18, 22, 7, 4, 13, 19]
    assert BX.compact(game(status=2)) is None                                      # live: not written yet


def test_write_missing_writes_each_final_once():
    d = pathlib.Path(tempfile.mkdtemp())
    con = MU.connect(d / "m.sqlite")
    for gid, pts in (("0022600112", 123), ("0022600113", 99), ("0022600114", None)):     # the last not final
        con.execute("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,?,?)",
                    (gid, "2026-27", "2026-10-25", "UTA", "LAL", pts, pts))
    con.commit()
    calls = []

    def get(gid):
        calls.append(gid)
        if gid == "0022600113":
            raise OSError("cdn down")
        return game(gid)
    out = d / "box"
    assert BX.write_missing(con, out, get=get) == (1, 1)
    assert sorted(calls) == ["0022600112", "0022600113"]                            # finals only
    assert json.loads((out / "0022600112.json").read_text())["teams"][0]["tri"] == "LAL"
    assert not list(out.glob(".*.tmp"))
    calls.clear()
    assert BX.write_missing(con, out, get=get) == (0, 1) and calls == ["0022600113"]   # the written one is not fetched again
