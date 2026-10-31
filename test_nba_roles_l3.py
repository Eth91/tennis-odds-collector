"""nba_roles_l3: the NBA_ROLES_L3_PREREG.md backtest (last 3 games against the season average; the new starter in the
first games a usual starter is out)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import nba_roles_l3 as RL


def row(gid, date, team, pid, starter, mn, pts=10, reb=4, ast=2, fg3m=1, fga=8, fg3a=3, season="2023-24"):
    return {"season": season, "gid": gid, "date": date, "team": team, "pid": pid, "starter": starter, "min": mn,
            "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m, "fga": fga, "fg3a": fg3a}


def fixture():
    """Team T, 8 games. 1-5 start every game but X (5) misses the last 2. 6 comes off the bench, 15 -> 30 minutes
    from g4. 7 starts for X. 8 started the first 6 at 40 minutes, then went to U (one U game before g6). 9 played
    g2-g5 only. 10 goes 20 -> 28 minutes from g3 (exactly 4 over his season average before g6).
    Team V, the same dates. 21-23, Y (25) and 26 start; Y misses v6 only, 26 misses v6 and v7 (traded: a U game
    in between). Z (27) starts v6 only."""
    rows = []
    for i in range(8):
        g, d = f"g{i}", f"2023-11-{i * 2 + 1:02d}"
        for p in (1, 2, 3, 4):
            rows.append(row(g, d, "T", p, 1, 30))
        if i < 6:
            rows.append(row(g, d, "T", 5, 1, 30))
            rows.append(row(g, d, "T", 8, 1, 40))
        rows.append(row(g, d, "T", 6, 0, 30 if i >= 4 else 15, pts=18 if i >= 6 else 8))
        rows.append(row(g, d, "T", 7, int(i >= 6), 20, pts=14, reb=5))
        if 2 <= i <= 5:
            rows.append(row(g, d, "T", 9, 0, 10))
        rows.append(row(g, d, "T", 10, 0, 28 if i >= 3 else 20))
        v = f"v{i}"
        for p in (21, 22, 23):
            rows.append(row(v, d, "V", p, 1, 30))
        if i != 6:
            rows.append(row(v, d, "V", 25, 1, 30))
        if i < 6:
            rows.append(row(v, d, "V", 26, 1, 30))
        rows.append(row(v, d, "V", 27, int(i == 6), 20, pts=12))
    rows.append(row("u0", "2023-11-12", "U", 8, 1, 35))
    rows.append(row("u1", "2023-11-14", "U", 26, 1, 30))
    return rows


def test_main_rung_is_the_over_nearest_even_with_both_sides_and_fanduels_no_vig():
    lb = {9.5: {"fanduel": [1.6, 2.3], "draftkings": [1.65, 2.25]},
          10.5: {"fanduel": [1.95, 1.87], "draftkings": [2.02, 1.8]},
          11.5: {"fanduel": [2.0, None]}}                        # one side only: not a rung
    line, over, under, nv = RL.main_rung(lb)
    assert (line, over, under) == (10.5, 2.02, 1.87) and abs(nv - (1 / 1.95) / (1 / 1.95 + 1 / 1.87)) < 1e-12
    assert RL.main_rung({10.5: {"draftkings": [1.9, 1.9]}})[3] == 0.5 and RL.main_rung({10.5: {"fanduel": [1.9, None]}}) is None


def test_grade_wins_at_the_price_pushes_and_unders():
    assert RL.grade(12, 10.5, "over", 1.9, 1.95, 0.48) == (0.8999999999999999, 0.48, True)
    assert RL.grade(9, 10.5, "over", 1.9, 1.95, 0.48)[0] == -1.0
    assert RL.grade(10, 10, "over", 1.9, 1.95, 0.48)[0] == 0.0 and RL.grade(10, 10, "over", 1.9, 1.95, 0.48)[2] is None
    u, p, win = RL.grade(9, 10.5, "under", 1.9, 1.95, 0.48)
    assert abs(u - 0.95) < 1e-12 and abs(p - 0.52) < 1e-12 and win


def test_moves_last_3_against_the_season_average_with_the_last_3_in_it():
    S = RL.Season(fixture(), "2023-24")
    # before g7: 15 x 4, 30 x 3 -> L3 30 against 150 / 7
    assert abs(S.moves(6, "T", "2023-11-15")["min"] - (30 - 150 / 7)) < 1e-9
    assert abs(S.moves(6, "T", "2023-11-13")["min"] - 5.0) < 1e-9          # before g6: 25 against 20
    assert S.moves(6, "T", "2023-11-09") is None                           # 4 games: under SEASON_MIN_GP
    assert S.moves(6, "T", "2023-11-11")["min"] == 2.0                     # 5 games: 20 against 18
    assert S.moves(9, "T", "2023-11-13") is None                           # 4 games, the median team 6: too few
    assert S.moves(5, "T", "2023-11-17") is None                           # X: missed 2 of the last 4


def test_usual_five_skips_a_player_now_elsewhere_and_absence_counts_games_in_a_row():
    S = RL.Season(fixture(), "2023-24")
    assert S.usual_five("T", "2023-11-13") == {1, 2, 3, 4, 5}             # not 8 (traded to U before g6)
    assert S.missing("T", "2023-11-13", S.usual_five("T", "2023-11-13")) == {5: 1}
    assert S.missing("T", "2023-11-15", S.usual_five("T", "2023-11-15")) == {5: 2}
    assert S.usual_five("T", "2023-11-05") is None                         # 2 games: under 3
    assert S.usual_five("T", "2023-11-07") == {8, 1, 2, 3, 4}             # 3 games: 8 on more minutes than 5
    # 26 is out too, but his next game is for U: traded, not missing
    assert S.missing("V", "2023-11-13", S.usual_five("V", "2023-11-13")) == {25: 1}


def test_run_flags_the_new_starter_in_game_1_and_2_and_b2_only_when_his_line_did_not_rise():
    L = lambda line: (line, 1.9, 1.9, 0.5)
    lines = {("2023-11-11", 7, "points"): L(13.5), ("2023-11-13", 7, "points"): L(13.5), ("2023-11-15", 7, "points"): L(15.5),
             ("2023-11-11", 7, "rebounds"): L(4.5), ("2023-11-13", 7, "rebounds"): L(5.5),
             ("2023-11-13", 6, "points"): L(12.5), ("2023-11-15", 6, "points"): L(20.5), ("2023-11-15", 6, "threes"): L(0.5),
             ("2023-11-13", 1, "points"): L(9.5), ("2023-11-13", 10, "points"): L(10.5),
             ("2023-11-13", 27, "points"): L(9.5), ("2023-11-15", 27, "points"): L(11.5)}
    bets, info = RL.run(fixture(), lines, seasons=("2023-24",))
    got = sorted((b["rule"], b["date"], b["pid"], b["market"], b["side"], b["u"]) for b in bets)
    assert got == [("A1", "2023-11-13", 6, "points", "over", 0.8999999999999999),     # 25 vs 20, 18 pts > 12.5
                   ("A1", "2023-11-13", 10, "points", "over", -1.0),                  # 28 vs 24: exactly 4
                   ("A1", "2023-11-15", 6, "points", "over", -1.0),                   # 18 < 20.5
                   ("A1", "2023-11-15", 6, "threes", "over", 0.8999999999999999),
                   ("B1", "2023-11-13", 7, "points", "over", 0.8999999999999999),     # game 1: 14 > 13.5
                   ("B1", "2023-11-13", 7, "rebounds", "over", -1.0),                 # 5 < 5.5
                   ("B1", "2023-11-13", 27, "points", "over", 0.8999999999999999),    # V's: Y out, Z starts
                   ("B1 n=2", "2023-11-15", 7, "points", "over", -1.0),               # game 2: 14 < 15.5
                   ("B2", "2023-11-13", 7, "points", "over", 0.8999999999999999)]     # 13.5 not above 13.5 (rebounds rose)
    # 1 (a usual starter) is a teammate, not a new starter
    assert sorted((b["pid"], b["market"]) for b in info["every teammate, n=1"]) == \
        [(1, "points"), (6, "points"), (7, "points"), (7, "rebounds"), (10, "points"), (27, "points")]
    # Z's game 2 line is not a game 2: Y was back
    assert sorted((b["market"], b["prev"] or 0, b["g1"], b["g2"] or 0) for b in info["bump"]) == \
        [("points", 0, 9.5, 0), ("points", 13.5, 13.5, 15.5), ("rebounds", 4.5, 5.5, 0)]


def test_pass_needs_both_seasons_the_bar_a_profit_and_a_hit_rate_over_fair():
    ok = {"n": 100, "roi": 0.01, "hit": 0.52, "nv": 0.51}
    assert RL.passes([ok, ok], 100)
    assert not RL.passes([ok, {**ok, "n": 99}], 100) and not RL.passes([ok, {**ok, "roi": 0.0}], 100)
    assert not RL.passes([ok, {**ok, "hit": 0.51}], 100) and RL.passes([ok, {**ok, "n": 50}], 50)
