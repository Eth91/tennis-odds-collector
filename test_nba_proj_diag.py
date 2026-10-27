"""nba_proj_diag.py: the absence flag uses only earlier games, and the known-minutes rescale keeps per-minute
production (with a floor for zero-minute draws)."""
import numpy as np

import nba_proj_diag as D
import nba_project as NP


def _games(n, team="AAA", absent_from=None, star=1):
    rows = []
    for g in range(n):
        d = f"2024-01-{g + 1:02d}"
        for pid, mn in ((star, 34), (2, 30), (3, 12)):
            if pid == star and absent_from is not None and g >= absent_from:
                continue
            rows.append({"date": d, "gid": f"G{g}", "team": team, "pid": pid, "min": mn})
    return rows


def test_absence_flag_is_pregame_and_needs_ten_games():
    rows = _games(14, absent_from=12)
    flagged = {rows[i]["gid"] for i in D.absence_rows(rows)}
    assert flagged == {"G12", "G13"}                     # the regular is missing from game 12 on
    assert not D.absence_rows(_games(14))                # nobody missing: nothing flagged
    assert not D.absence_rows(_games(9, absent_from=8))  # fewer than 10 earlier games: no verdict


def test_bench_player_missing_is_not_a_regular():
    rows = [r for r in _games(14) if not (r["pid"] == 3 and r["gid"] in ("G12", "G13"))]
    assert not D.absence_rows(rows)                      # 12-minute player: not a regular


def test_known_minutes_keeps_per_minute_production():
    class R:
        Y = np.array([[30.0] + [0] * 7])
    d = NP.Dist.__new__(NP.Dist)
    d.vals = np.array([[[20.0, 10, 4, 2, 1, 1, 0, 2], [0.0, 1, 0, 0, 0, 0, 0, 0]]])
    d.mu = np.zeros((1, 8))
    k = D.known_minutes(R, d, np.array([0]))
    assert np.allclose(k.vals[0, 0], [30, 15, 6, 3, 1.5, 1.5, 0, 3])
    assert np.allclose(k.vals[0, 1, :2], [30, 30])       # a 0-minute draw is floored at 1 minute
    assert np.allclose(d.vals[0, 0, 0], 20)              # the input is not modified
