"""nba_injury_report.Resolver: the three surname shapes the league's PDF produces."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_injury_report as I

INDEX = {1641726: ("DAL", "Dereck Lively II", "C"), 1628991: ("MEM", "Jaren Jackson Jr.", "F-C"),
         1642000: ("CLE", "Ernest Udeh Jr.", "C"), 1628386: ("CLE", "Jarrett Allen", "C"),
         1642001: ("CLE", "Ernest Smith", "G")}


def test_surname_shapes():
    res = I.Resolver(INDEX)
    assert res("Dereck II", "DAL")[0] == 1641726          # "Lively II, Dereck" (suffix split off)
    assert res("Jaren Jr.", "MEM")[0] == 1628991          # "Jackson Jr., Jaren"
    assert res("Jr., Ernest Udeh", "CLE")[0] == 1642000   # "Udeh, Jr., Ernest" (suffix after comma)
    assert res("Jarrett Allen", "CLE")[0] == 1628386
    assert res("Ernest Nobody", "CLE")[0] is None          # never guess
