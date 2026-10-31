"""NBA_Q15: features from games before tonight only, grading, prices at the consensus line, the under-bet filter."""
import numpy as np
import pandas as pd

import nba_q15 as Q
import nba_q15_model as QM


def box(rows):
    """Box rows (pid, date, game, min, pts) with every PARTS column, for one team."""
    b = pd.DataFrame([{"pid": p, "date": d, "game_id": g, "team": "BOS", "opp": "NYK", "season": "2023-24", "post": 0,
                       "min": m, "pts": pts, "reb": 4.0, "ast": 2.0, "fg3m": 1.0} for p, d, g, m, pts in rows])
    for m, ps in Q.PARTS.items():
        b["s_" + m] = sum(b[x] for x in ps)
    return b


GAMES = [(1, "2023-11-01", "g1", 30.0, 20.0), (1, "2023-11-03", "g2", 20.0, 10.0), (1, "2023-11-05", "g3", 40.0, 30.0),
         (1, "2023-11-06", "g4", 35.0, 25.0)]


def at(f, g):
    return f[f["game_id"] == g].iloc[0]


def test_features_use_only_the_games_before_tonight():
    f = Q.player_features(box(GAMES))
    g3 = at(f, "g3")
    assert g3["min_l3"] == 25.0 and g3["min_l5"] == 25.0          # g1 and g2, not g3's 40
    assert g3["points_l5"] == 15.0 and g3["points_l10"] == 15.0
    assert g3["gp_season"] == 2 and g3["min_season_sum"] == 50.0 and g3["points_season_sum"] == 30.0
    assert g3["points_season_avg"] == 15.0 and g3["min_season_avg"] == 25.0
    assert g3["rest"] == 2 and at(f, "g4")["rest"] == 1
    assert at(f, "g4")["min_l3"] == 30.0                            # g1-g3
    assert np.isnan(at(f, "g1")["min_l3"]) and at(f, "g1")["gp_season"] == 0


def test_tonights_box_never_changes_tonights_features():
    a = Q.player_features(box(GAMES))
    b = Q.player_features(box(GAMES[:2] + [(1, "2023-11-05", "g3", 4.0, 0.0)] + GAMES[3:]))
    cols = [c for c in a.columns if c not in ("min",) and not c.startswith("s_")]
    pd.testing.assert_series_equal(at(a, "g3")[cols], at(b, "g3")[cols], check_names=False)
    assert at(a, "g4")["min_l3"] != at(b, "g4")["min_l3"]          # it is in the next game's


def test_split_of():
    assert Q.split_of("2024-01-10", 0) == "TRAIN" and Q.split_of("2025-01-10", 0) == "VALIDATE"
    assert Q.split_of("2024-05-10", 1) == "TEST_A" and Q.split_of("2024-04-14", 0) == "TRAIN"
    assert Q.split_of("2024-07-01", 0) == "OTHER"


def props(**kw):
    base = {"line": [10.5, 10.0, 10.5], "actual": [9.0, 10.0, 12.0], "fd_line": [10.5, 10.0, 10.5], "dk_line": [10.5, 10.0, 11.5],
            "fd_o": [1.9, 1.9, 1.9], "fd_u": [1.9, 1.95, 1.8], "dk_o": [1.8, 1.8, 2.5], "dk_u": [2.0, 1.9, 2.5]}
    base.update(kw)
    return pd.DataFrame(base)


def test_grade_win_push_loss():
    u, w = Q.grade(props(), "under", np.array([1.9, 1.9, 1.9]))
    assert np.allclose(u, [0.9, 0.0, -1.0]) and w[0] == 1 and np.isnan(w[1]) and w[2] == 0
    u, _ = Q.grade(props(), "over", np.array([2.0, 2.0, 2.0]))
    assert list(u) == [-1.0, 0.0, 1.0]


def test_price_is_the_better_book_at_the_consensus_line_only():
    p, who = Q.price_at(props(), "under", ("fd", "dk"))
    assert list(p) == [2.0, 1.95, 1.8] and list(who) == ["dk", "fd", "fd"]   # DK's 11.5 is not the line


def test_under_bets_need_the_ev_the_minutes_and_the_under_side():
    n = 4
    d = props(actual=[9.0] * n, line=[10.5] * n, fd_line=[10.5] * n, dk_line=[10.5] * n,
              fd_u=[2.0] * n, dk_u=[1.9] * n, fd_o=[1.8] * n, dk_o=[1.8] * n)
    d["e_min"] = [30.0, 11.9, 12.0, 30.0]
    p = pd.Series([0.455, 0.455, 0.455, 0.465])                     # under EV at 2.0: 9%, 9%, 9%, 7%
    b = QM.under_bets(d, p, 0.08)
    assert list(b.index) == [0, 2] and set(b["side"]) == {"under"} and set(b["price"]) == {2.0}
    assert len(QM.under_bets(d, pd.Series([0.6] * n), 0.0)) == 0      # the over is the better side


def test_engine_features_compare_the_projection_with_the_line():
    d = pd.DataFrame({"date": ["2024-01-01"], "pid": [7], "market": ["points"], "line": [20.5]})
    X = pd.DataFrame(index=d.index)
    d, X = QM.with_engine(d, X, {("2024-01-01", 7, "points"): (10.0, 24.0)})
    assert np.isclose(X["e_r"][0], np.log(10.5 / 21.0)) and X["e_r_neg"][0] == X["e_r"][0] and X["e_min"][0] == 24.0
    d2, X2 = QM.with_engine(d[["date", "pid", "market", "line"]].copy(), pd.DataFrame(index=d.index), {})
    assert np.isnan(X2["e_r"][0])
