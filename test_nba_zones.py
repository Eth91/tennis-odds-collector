"""NBA_ZONES_PREREG.md: shot zones from court position (tenths of a foot, basket at 0,0)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_zones as Z


def test_zones():
    assert Z.zone(0, 0) == "ra" and Z.zone(30, 20) == "ra"                  # under the rim, within 4 ft
    assert Z.zone(60, 100) == "paint" and Z.zone(-75, 140) == "paint"        # the lane, inside the free-throw line
    assert Z.zone(150, 100) == "mid" and Z.zone(0, 200) == "mid"             # elbow / top of the key, inside the arc
    assert Z.zone(225, 20) == "c3" and Z.zone(-230, 90) == "c3"              # corners, below the break
    assert Z.zone(0, 250) == "ab3" and Z.zone(200, 160) == "ab3"             # above the break, beyond 23.75 ft
    assert Z.zone(215, 20) == "mid"                                          # a long two from the corner
