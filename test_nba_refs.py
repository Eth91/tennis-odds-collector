"""nba_refs: tonight's crews and how each official's games have run (docs/refs.json)."""
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_matchup as MU
import nba_refs as RF


def test_fits_reads_cities_and_the_la_nicknames():
    assert RF.fits("Washington", "WAS") and RF.fits("Oklahoma City", "OKC") and RF.fits("Golden State", "GSW")
    assert RF.fits("LA Clippers", "LAC") and RF.fits("L.A. Lakers", "LAL") and RF.fits("Los Angeles Lakers", "LAL")
    assert RF.fits("Washington Wizards", "WAS") and RF.fits("Utah Jazz", "UTA")                 # a full name still finds it
    assert not RF.fits("Golden State", "OKC") and not RF.fits("LA Clippers", "LAL") and not RF.fits("New York", "BKN")
    assert not RF.fits("Los Angeles", "LAC") and not RF.fits("Washingtonian", "WAS")


PAGE = """<h2>NBA Referee Assignments</h2><table class="table"><tr><th>Game</th><th>Crew Chief</th><th>Referee</th><th>Umpire</th><th>Alternate</th></tr>
<tr><td>Washington @ Charlotte</td><td><a href="#">Ed Malloy (#7)</a></td><td>Eric Dalen (#37)</td><td>Biniam Maru (#94)</td><td></td></tr>
<tr><td>L.A. Lakers @ Golden State</td><td>Scott Foster (#48)</td><td>New Guy (#99)</td><td>Karl Lane (#77)</td><td></td></tr>
<tr><td>Miami @ Boston</td><td>Tony Brothers (#25)</td><td>Eric Lewis (#42)</td><td>John Conley (#56)</td><td></td></tr></table>
<h2>WNBA Referee Assignments</h2><table><tr><td>Atlanta @ Golden State</td><td>Tiara Cruse (#5)</td><td>A (#1)</td><td>B (#2)</td><td>C (#3)</td></tr></table>"""


def test_parse_and_match_the_nba_table_only():
    rows = RF.parse_assign(PAGE)
    assert [r[:2] for r in rows] == [("Washington", "Charlotte"), ("L.A. Lakers", "Golden State"), ("Miami", "Boston")]
    assert rows[0][2] == [("Ed Malloy", "Crew Chief"), ("Eric Dalen", "Referee"), ("Biniam Maru", "Umpire")]
    games = [{"gid": "G1", "away": "WAS", "home": "CHA"}, {"gid": "G2", "away": "LAL", "home": "GSW"},
             {"gid": "G3", "away": "ATL", "home": "GSW"}]
    m = RF.match(rows, games)
    assert set(m) == {"G1", "G2"} and m["G2"][1] == ("New Guy", "Referee")            # Miami @ Boston: not on the slate


def box(status, home, away, officials):
    team = lambda s: {"statistics": dict(zip(("points", "foulsPersonal", "freeThrowsAttempted", "fieldGoalsAttempted",
                                              "reboundsOffensive", "turnoversTotal"), s))}
    return {"gameStatus": status, "homeTeam": team(home), "awayTeam": team(away),
            "officials": [{"personId": p, "name": n} for p, n in officials]}


def test_game_row_totals_both_teams():
    (pts, pf, fta, poss), crew = RF.game_row(box(3, (110, 20, 25, 88, 10, 14), (100, 22, 20, 90, 12, 12), [(7, "Ed Malloy")]))
    assert (pts, pf, fta) == (210, 42, 45) and abs(poss - ((88 + 11 - 10 + 14) + (90 + 8.8 - 12 + 12)) / 2) < 1e-9
    assert crew == [(7, "Ed Malloy")] and RF.game_row(box(2, (0,) * 6, (0,) * 6, [])) is None


def test_store_and_build():
    d = pathlib.Path(tempfile.mkdtemp())
    m = MU.connect(d / "m.sqlite")
    m.executemany("INSERT INTO games (gid, season, date, home, away, home_pts, away_pts) VALUES (?,?,?,?,?,?,?)",
                  [("A", "2025-26", "2026-01-10", "BOS", "MIA", 100, 90), ("B", "2026-27", "2026-10-22", "CHA", "WAS", 120, 110),
                   ("C", "2026-27", "2026-10-24", "GSW", "LAL", 101, 99), ("D", "2026-27", "2026-10-25", "GSW", "LAL", 101, 99),
                   ("E", "2026-27", "2026-10-26", "CHA", "WAS", None, None)])            # not final: not fetched
    m.commit()
    con = sqlite3.connect(d / "r.sqlite")
    con.executescript(RF.DDL)
    boxes = {"A": box(3, (100, 20, 20, 80, 10, 10), (90, 20, 20, 80, 10, 10), [(7, "Ed Malloy"), (48, "Scott Foster")]),
             "B": box(3, (120, 25, 30, 80, 10, 10), (110, 25, 30, 80, 10, 10), [(7, "Ed Malloy"), (84, "Nate Cearley")]),
             "C": box(3, (101, 15, 10, 80, 10, 10), (99, 15, 10, 80, 10, 10), [(48, "Scott Foster"), (72, "J.T. Orr"), (84, "Nate Cearly")]),
             "D": box(3, (101, 15, 10, 80, 10, 10), (99, 15, 10, 80, 10, 10), [])}                # no officials: retried
    asked = []

    def get(gid):
        asked.append(gid)
        return boxes[gid]
    assert RF.fetch_games(con, m, ("2025-26", "2026-27"), get=get, workers=1) == (3, 1) and "E" not in asked
    asked.clear()
    assert RF.fetch_games(con, m, ("2025-26", "2026-27"), get=get, workers=1) == (0, 1) and asked == ["D"]
    RF.store_assign(con, {"E": [("Ed Malloy", "Crew Chief"), ("New Guy", "Referee"), ("JT Orr", "Umpire")],
                          "Y": [("Nate Cearley", "Crew Chief")]}, "t")
    doc = RF.build(con, ("2025-26", "2026-27"), ["E", "C", "Y", "Z"], "t")
    assert doc["league"] == [3, 206.7, 40.0, 40.0, 88.8]      # A 190 / B 230 / C 200 points, both teams
    assert doc["refs"]["7"] == ["Ed Malloy", 2, 210.0, 45.0, 50.0, 91.0] and doc["refs"]["48"][1:4] == [2, 195.0, 35.0]
    # tonight's crew: a known official by name, a new one without an id; a final game falls back to its box's officials
    assert doc["games"]["E"] == [[7, "Ed Malloy", "Crew Chief"], [None, "New Guy", "Referee"], [72, "JT Orr", "Umpire"]]
    assert doc["games"]["Y"] == [[84, "Nate Cearley", "Crew Chief"]]                  # the box spelled him two ways
    assert doc["games"]["C"][0] == [48, "Scott Foster", "Crew Chief"] and "Z" not in doc["games"]
    assert RF.build(con, ("2026-27",), [], "t")["refs"]["7"][1] == 1                       # the seasons asked for only
