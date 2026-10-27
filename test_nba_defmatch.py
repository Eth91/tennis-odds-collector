"""nba_defmatch: who guards whom, for the Matchup page (docs/matchups/{pid}.json)."""
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_defmatch as DM

HEAD = ["SEASON_ID", "OFF_PLAYER_ID", "OFF_PLAYER_NAME", "DEF_PLAYER_ID", "DEF_PLAYER_NAME", "GP", "MATCHUP_MIN", "PARTIAL_POSS",
        "PLAYER_PTS", "TEAM_PTS", "MATCHUP_AST", "MATCHUP_TOV", "MATCHUP_BLK", "MATCHUP_FGM", "MATCHUP_FGA", "MATCHUP_FG_PCT",
        "MATCHUP_FG3M", "MATCHUP_FG3A", "MATCHUP_FG3_PCT", "HELP_BLK", "HELP_FGM", "HELP_FGA", "HELP_FG_PERC", "MATCHUP_FTM",
        "MATCHUP_FTA", "SFL", "MATCHUP_TIME_SEC"]


def pair(off, dfn, dname, gp, poss, pts, fgm, fga, fg3m=0, fg3a=0):
    return ["22026", off, "O", dfn, dname, gp, "5:00", poss, pts, 0, 1, 0, 0, fgm, fga, 0, fg3m, fg3a, 0, 0, 0, 0, 0, 1, 2, 0, 300]


def test_fetch_store_write():
    d = pathlib.Path(tempfile.mkdtemp())
    con = sqlite3.connect(d / "dm.sqlite")
    con.executescript(DM.DDL)
    calls = []
    resp = {10: [pair(1, 50, "Wing Stopper", 2, 41.5, 9, 4, 11, 1, 4), pair(1, 51, "Brief Switch", 1, 2.0, 2, 1, 1)],
            20: [pair(2, 60, "Big", 3, 30.0, 12, 5, 8)]}

    def get(url):
        calls.append(url)
        tid = int(url.split("OffTeamID=")[1].split("&")[0])
        return {"resultSets": [{"name": "SeasonMatchups", "headers": HEAD, "rowSet": resp[tid]}]}
    assert DM.fetch(con, "2026-27", True, [10, 20], get=get, pause=0) == 3 and len(calls) == 2
    assert all("Season=2026-27" in u for u in calls)
    # cumulative totals: the next fetch replaces the pair rather than adding a second
    resp[10][0] = pair(1, 50, "Wing Stopper", 3, 60.0, 15, 6, 16, 2, 6)
    assert DM.fetch(con, "2026-27", True, [10], get=get, pause=0) == 2
    assert con.execute("SELECT COUNT(*), MAX(poss) FROM pairs WHERE off_pid=1").fetchone() == (2, 60.0)
    # a past season: only the teams not fetched yet
    calls.clear()
    assert DM.fetch(con, "2026-27", False, [10, 20], get=get, pause=0) == 0 and calls == []
    assert DM.write(con, d / "out", ("2026-27",)) == 2
    doc = json.loads((d / "out" / "1.json").read_text())
    # most possessions first, the 2-possession switch left out (under MIN_POSS)
    assert doc == {"pid": 1, "s": {"2026-27": [[50, "Wing Stopper", 3, 60.0, 15.0, 6.0, 16.0, 2.0, 6.0, 1.0, 0.0, 2.0, 300.0]]}}
