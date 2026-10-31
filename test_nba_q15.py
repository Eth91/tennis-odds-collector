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


# ── TEST B: the live path (nba_q15_live) ────────────────────────────────────────────────────────────────────────────
import nba_q15_live as L  # noqa: E402

TEAM = [(1, "2023-11-01", "g1", 30.0, 20.0), (2, "2023-11-01", "g1", 30.0, 8.0), (1, "2023-11-03", "g2", 20.0, 10.0),
        (2, "2023-11-03", "g2", 30.0, 9.0), (1, "2023-11-05", "g3", 40.0, 30.0), (2, "2023-11-05", "g3", 30.0, 7.0),
        (1, "2023-11-06", "g4", 35.0, 25.0), (3, "2023-11-06", "g4", 10.0, 2.0)]
TONIGHT = ("2023-11-08", "g5")


def prior():
    b = box(TEAM)
    for c in ("fga", "fta", "tov", "oreb", "fg3a"):
        b[c] = 0.0
    return b, Q.team_totals(b)


def test_live_features_are_the_box_features_before_tonight():
    b, t = prior()
    live = L.player_frame(b, t, TONIGHT[0], [(1, "BOS", "NYK", TONIGHT[1])], "2023-24")[1]
    full = box(TEAM + [(1, TONIGHT[0], TONIGHT[1], 33.0, 41.0)])
    ref = at(Q.player_features(full), TONIGHT[1])
    for c in ("min_l3", "min_l5", "min_l10", "points_l5", "points_season_sum", "gp_season", "rest", "points_rate", "min_season_avg"):
        assert live[c] == ref[c] or (np.isnan(live[c]) and np.isnan(ref[c])), c
    assert live["missed"] == 0


def test_an_out_rotation_player_is_vacated_and_extra_candidates_change_nothing():
    b, t = prior()
    night = L.Night(b, t, TONIGHT[0], [(p, "BOS", "NYK", TONIGHT[1]) for p in (1, 2, 3, 99)], "2023-24")
    f = night.frame([(1, "BOS", "NYK", TONIGHT[1]), (3, "BOS", "NYK", TONIGHT[1])])     # 2 is Out
    assert (f[1]["vac_min"], f[1]["vac_n"]) == (30.0, 1) and 2 not in f and 99 not in f
    assert f[3]["missed"] == 0
    alone = L.player_frame(b, t, TONIGHT[0], [(1, "BOS", "NYK", TONIGHT[1]), (3, "BOS", "NYK", TONIGHT[1])], "2023-24")
    assert {k: v for k, v in alone[1].items() if v == v} == {k: v for k, v in f[1].items() if v == v}
    f2 = night.frame([(p, "BOS", "NYK", TONIGHT[1]) for p in (1, 2, 3)])                # 2 plays
    assert (f2[1]["vac_min"], f2[1]["vac_n"]) == (0, 0)


def test_the_exported_model_is_impute_scale_logistic():
    m = {"features": ["a", "b"], "median": [1.0, 2.0], "mean": [0.0, 1.0], "scale": [2.0, 1.0], "coef": [0.5, -1.0], "intercept": 0.1}
    X = pd.DataFrame({"b": [3.0, np.nan], "a": [np.nan, 4.0]})
    z = np.array([0.1 + 0.5 * 0.5 - 1.0 * 2.0, 0.1 + 0.5 * 2.0 - 1.0 * 1.0])
    assert np.allclose(QM.predict(m, X), 1 / (1 + np.exp(-z)))


def test_props_take_fanduels_main_line_else_draftkings_and_score_in_range():
    b, t = prior()
    pf = L.player_frame(b, t, TONIGHT[0], [(1, "BOS", "NYK", TONIGHT[1])], "2023-24")
    props = [(1, "points", (24.5, 1.9, 1.9), (25.5, 1.95, 1.85)), (1, "rebounds", None, (4.5, 1.9, 1.9)), (1, "assists", None, None),
             (7, "points", (9.5, 1.9, 1.9), None)]
    d = L.props_frame(pf, props, {TONIGHT[1]: "BOS"}, TONIGHT[0])
    assert list(zip(d["market"], d["line"])) == [("points", 24.5), ("rebounds", 4.5)] and list(d["home_flag"]) == [1, 1]
    d, p = L.score(d, {(TONIGHT[0], 1, "points"): (12.0, 30.0), (TONIGHT[0], 1, "rebounds"): (4.0, 30.0)})
    assert len(p) == 2 and ((p > 0) & (p < 1)).all()
    assert list(d["line"]) == [24.5, 4.5]
    pr, who = Q.price_at(d, "under", ("fd", "dk"))
    assert list(pr) == [1.9, 1.9] and list(who) == ["fd", "dk"]          # DraftKings' 25.5 is not FanDuel's line


def test_a_store_without_the_tables_gives_no_box(tmp_path):
    assert L.box_from_matchup(tmp_path / "none.sqlite", ("2026-27",), "2026-11-01") == (None, None)
    import sqlite3
    db = tmp_path / "m.sqlite"
    sqlite3.connect(db).executescript("CREATE TABLE games (gid); CREATE TABLE player_games (gid);").close()
    assert L.box_from_matchup(db, ("2026-27",), "2026-11-01") == (None, None)
