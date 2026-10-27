"""nba_shots: the six-zone shot data behind the Matchup page's shot chart (docs/shots/{season}.json)."""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_matchup as MU
import nba_shots as SH

CATS = ["Restricted Area", "In The Paint (Non-RA)", "Mid-Range", "Left Corner 3", "Right Corner 3", "Above the Break 3",
        "Backcourt", "Corner 3"]


def resp(lead_cols, rows):
    """A By Zone response in stats.nba.com's layout: lead columns, then FGM / FGA / FG_PCT for each of 8 categories."""
    return {"resultSets": {"name": "ShotLocations", "headers": [
        {"name": "SHOT_CATEGORY", "columnSpan": 3, "columnNames": CATS},
        {"name": "columns", "columnSpan": 1, "columnNames": lead_cols + ["FGM", "FGA", "FG_PCT"] * len(CATS)}],
        "rowSet": rows}}


def zone_row(lead, pairs):
    out = list(lead)
    for m, a in pairs:
        out += [m, a, (m / a) if a else None]
    return out


# 8 categories: the six zones, then Backcourt and Corner 3 (left + right), which the file leaves out
P = resp(["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "AGE", "NICKNAME"], [
    zone_row([1, "Naz Reid", 10, "MIN", 27.0, "Naz"], [(30, 45), (8, 20), (5, 14), (2, 5), (3, 6), (20, 55), (0, 1), (5, 11)]),
    zone_row([2, "Never Shot", 10, "MIN", 20.0, "N"], [(0, 0)] * 8)])
T = resp(["TEAM_ID", "TEAM_NAME"], [
    zone_row([10, "Minnesota"], [(100, 150), (40, 100), (30, 75), (10, 25), (12, 30), (60, 170), (0, 2), (22, 55)]),
    zone_row([20, "Washington"], [(130, 170), (50, 110), (20, 70), (14, 28), (11, 29), (70, 180), (0, 1), (25, 57)]),
    zone_row([99, "Unknown"], [(1, 1)] * 8)])


def test_zones_reads_the_six_by_name():
    z = SH.zones(P, 6)
    assert z[1] == [[30, 45], [8, 20], [5, 14], [2, 5], [3, 6], [20, 55]]          # not Backcourt, not the corner sum
    assert SH.zones(T, 2)[20][3] == [14, 28]


def test_build_and_write():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    m.executemany("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,?,?)",
                  [("g1", "2026-27", "2026-10-22", "MIN", "WAS", 100, 90), ("g2", "2026-27", "2026-10-24", "WAS", "CHI", 99, 98),
                   ("g3", "2026-27", "2026-10-26", "WAS", "MIN", None, None)])        # not final: not counted
    m.commit()
    calls = []

    def get(url):
        calls.append(url)
        return P if "playershotlocations" in url else T
    doc = SH.write(d / "shots", "2026-27", m, get=get, tri_of={10: "MIN", 20: "WAS"})
    assert any("MeasureType=Opponent" in u and "teamshotlocations" in u for u in calls) and all("Season=2026-27" in u for u in calls)
    assert set(doc["players"]) == {"1"}                                                # the player with no shot is left out
    assert doc["teams"] == {"MIN": {"gp": 1, "opp": [[100, 150], [40, 100], [30, 75], [10, 25], [12, 30], [60, 170]]},
                            "WAS": {"gp": 2, "opp": [[130, 170], [50, 110], [20, 70], [14, 28], [11, 29], [70, 180]]}}
    assert doc["league"][0] == [230, 320] and doc["league"][5] == [130, 350]           # the two teams' totals, zone by zone
    assert json.loads((d / "shots" / "2026-27.json").read_text())["season"] == "2026-27"
