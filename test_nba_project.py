"""The projection engine's guards (NBA_PROJECTION_PREREG.md, "Leakage guards") and its probability arithmetic.
Synthetic data only; mutants prove the leakage tests catch the bugs they exist for."""
import datetime as dt
import importlib
import math
import pathlib
import random
import sqlite3
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_proj_data as PD
import nba_project as NP

CFG = dict(NP.PROJ_CONFIG, K=20)


def synth(seed=1, seasons=(("2022-23", "2022-10-20"), ("2023-24", "2023-10-20"))):
    """Two seasons, four teams, 5 players each, ~2 games a week; player 101 is traded A -> B mid-2023-24."""
    rnd = random.Random(seed)
    rows = []
    teams = ["AAA", "BBB", "CCC", "DDD"]
    roster = {t: [100 + 10 * k + j for j in range(5)] for k, t in enumerate(teams)}
    for season, start in seasons:
        d0 = dt.date.fromisoformat(start)
        for g in range(60):
            date = (d0 + dt.timedelta(days=g * 3)).isoformat()
            a, b = (teams[g % 4], teams[(g + 1) % 4]) if g % 2 == 0 else (teams[(g + 2) % 4], teams[(g + 3) % 4])
            gid = f"{season[:4]}{g:04d}"
            for team, opp, home in ((a, b, 1), (b, a, 0)):
                for pid in roster[team]:
                    if pid == 101 and season == "2023-24" and g >= 30:
                        continue
                    if pid == 101 and team != "AAA":
                        continue
                    rows.append(_row(season, gid, date, team, opp, home, pid, rnd))
                if season == "2023-24" and g >= 30 and team == "BBB":
                    rows.append(_row(season, gid, date, team, opp, home, 101, rnd))
    rows.sort(key=lambda r: (r["date"], r["gid"], r["team"], r["pid"]))
    return rows


def _row(season, gid, date, team, opp, home, pid, rnd):
    mn = 20 + (pid % 10) * 3 + rnd.randint(-4, 4)
    return {"season": season, "gid": gid, "date": date, "team": team, "opp": opp, "home": home, "pid": pid,
            "name": f"P{pid}", "group": "GFC"[pid % 3], "min": float(mn), "pts": rnd.randint(0, mn // 2),
            "reb": rnd.randint(0, 8), "ast": rnd.randint(0, 6), "fg3m": rnd.randint(0, 3), "stl": rnd.randint(0, 2),
            "blk": rnd.randint(0, 2), "tov": rnd.randint(0, 3), "fga": 10, "fta": 3, "team_poss": 100.0}


def test_no_future_data_reaches_a_prediction():
    rows = synth()
    out, _ = NP.walk(rows, CFG)
    cut = "2023-12-01"
    poisoned = [dict(r, pts=r["pts"] * 9 + 40, min=48.0, reb=30) if r["date"] >= cut else r for r in rows]
    out2, _ = NP.walk(poisoned, CFG)
    for i, r in enumerate(rows):
        if r["date"] <= cut:                       # on the cutoff date itself too: predicted before it updates
            for k in ("b1", "b2", "m1"):
                assert np.allclose(out[i][k], out2[i][k]), (r["date"], k)
    later = [i for i, r in enumerate(rows) if r["date"] > cut]
    assert any(not np.allclose(out[i]["m1"], out2[i]["m1"]) for i in later)      # the poison is visible later


def test_mutant_update_before_predict_is_caught():
    src = pathlib.Path(NP.__file__).read_text()
    a = ("        for i in by_date.get(d, []):\n            if keep is None or i in keep:\n                out[i] = predict(rows[i])\n"
         "        for j in t_by_date.get(d, []):\n            out_t[j] = predict(targets[j])\n"
         "        update([rows[i] for i in by_date.get(d, [])])\n")
    b = ("        update([rows[i] for i in by_date.get(d, [])])\n        for i in by_date.get(d, []):\n"
         "            if keep is None or i in keep:\n                out[i] = predict(rows[i])\n"
         "        for j in t_by_date.get(d, []):\n            out_t[j] = predict(targets[j])\n")
    assert src.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_project.py").write_text(src.replace(a, b))
    sys.path.insert(0, str(d))
    saved = sys.modules.pop("nba_project")
    try:
        globals()["NP"] = importlib.import_module("nba_project")
        with pytest.raises(AssertionError):
            test_no_future_data_reaches_a_prediction()
    finally:
        globals()["NP"] = saved
        sys.modules["nba_project"] = saved
        sys.path.remove(str(d))


def test_live_targets_match_the_walk():
    rows = synth()
    last = rows[-1]["date"]
    tgt = [{"season": "2023-24", "date": "2099-01-01", "pid": 102, "team": "AAA", "opp": "BBB", "home": 1, "group": "C"}]
    _, ot = NP.walk(rows, CFG, targets=tgt)
    _, ot2 = NP.walk(rows + [dict(rows[-1], date="2099-01-02", gid="Z")], CFG, targets=tgt)
    assert np.allclose(ot[0]["m1"], ot2[0]["m1"]) and ot[0]["n_hist"] > 0 and last < "2099-01-01"


def test_traded_player_keeps_his_history_and_faces_tonights_opponent():
    rows = synth()
    out, _ = NP.walk(rows, CFG)
    first_b = next(i for i, r in enumerate(rows) if r["pid"] == 101 and r["team"] == "BBB")
    assert out[first_b]["n_hist"] > 40                          # his AAA games follow him to BBB
    base = {"season": "2023-24", "date": "2099-01-01", "pid": 101, "team": "BBB", "home": 1, "group": "F"}
    boosted = [dict(r, pts=r["pts"] + 30) if r["opp"] == "CCC" and r["group"] == "F" else r for r in rows]
    _, ot = NP.walk(boosted, dict(CFG, a_opp=1.0), targets=[dict(base, opp="CCC"), dict(base, opp="DDD")])
    assert ot[0]["m1"][1] > ot[1]["m1"][1] * 1.2                 # CCC gave forwards 30 more: his tonight


def test_dnp_is_never_an_outcome():
    d = pathlib.Path(tempfile.mkdtemp())
    g = sqlite3.connect(d / "gl.sqlite")
    g.execute("CREATE TABLE logs_full (season, game_id, date, team, player_id, player, min, fgm, fga, fg3m, fg3a, ftm, fta, "
              "oreb, dreb, reb, ast, stl, blk, tov, pf, pts, plus_minus)")
    g.execute("CREATE TABLE positions (player_id, player, position)")
    for pid, team, mn in ((1, "AAA", 30), (3, "BBB", 25)):
        g.execute("INSERT INTO logs_full VALUES ('2023-24','G1','2023-11-01',?,?,?,?,5,10,1,3,2,3,1,4,5,3,1,0,2,2,13,0)",
                  (team, pid, f"P{pid}", mn))
    g.execute("INSERT INTO logs_full VALUES ('2023-24','G1','2023-11-01','AAA',2,'P2',0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)")
    g.commit()
    rows, dnps, _ = PD.load_box(d / "gl.sqlite", d / "none.sqlite", d / "none2.sqlite")
    assert [r["pid"] for r in rows] == [1, 3] and dnps == [("2023-11-01", "G1", "AAA", 2)]
    assert rows[0]["opp"] == "BBB" and rows[0]["team_poss"] == pytest.approx(10 + .44 * 3 - 1 + 2)   # FGA+.44FTA-OREB+TOV


def _dist(vals):
    d = NP.Dist.__new__(NP.Dist)
    d.vals = np.asarray(vals, float)
    d.mu = d.vals.mean(1)
    return d


def test_probabilities_are_exact_and_sum_to_one():
    # one target, two analogs: points 2.3 and 4.0 (rebounds etc. zero) — stochastic rounding of 2.3 = 2 or 3
    v = np.zeros((1, 2, NP.NS))
    v[0, 0, 1], v[0, 1, 1] = 2.3, 4.0
    d = _dist(v)
    o, u, p = d.probs("points", [2.5])
    assert o[0] == pytest.approx((0.3 + 1.0) / 2) and p[0] == 0 and o[0] + u[0] + p[0] == pytest.approx(1)
    o, u, p = d.probs("points", [3.0])                         # whole line: X=3 pushes
    assert p[0] == pytest.approx(0.3 / 2) and o[0] == pytest.approx(0.5) and o[0] + u[0] + p[0] == pytest.approx(1)
    pm = d.pmf("points", 10)
    assert pm.sum() == pytest.approx(1) and pm[0, 2] == pytest.approx(0.35) and pm[0, 3] == pytest.approx(0.15)


def test_combos_come_from_the_same_draw():
    # pts and reb perfectly offsetting across analogs: PRA is constant, the independent sum would not be
    v = np.zeros((1, 4, NP.NS))
    for k, (pts, reb) in enumerate(((10, 0), (0, 10), (6, 4), (4, 6))):
        v[0, k, 1], v[0, k, 2] = pts, reb
    d = _dist(v)
    assert np.allclose(d.market_vals("pts_reb"), 10.0)
    o, u, p = d.probs("pts_reb", [9.5])
    assert o[0] == 1.0


def test_analog_rescale_moves_the_mean_and_keeps_zero_floor():
    pool_mu = np.array([[30, 10, 5, 3, 1, 1, 0.5, 2.0]])
    pool_y = np.array([[30, 0, 5, 3, 1, 1, 0, 2.0]])
    d = NP.Dist(np.array([[30, 20, 5, 3, 1, 1, 0.5, 2.0]]), pool_mu, pool_y, np.array([[0]]))
    assert d.vals[0, 0, 1] == pytest.approx(max(0, (0 + .25) * (20.25 / 10.25) - .25))
    assert (d.vals >= 0).all()


def test_crps_and_scores():
    pm = np.zeros((2, 5))
    pm[0, 2] = 1.0
    pm[1, 1], pm[1, 3] = .5, .5
    c = NP.crps_pmf(pm, np.array([2, 2]))
    assert c[0] == 0 and c[1] == pytest.approx(0.25 + 0.25)
    nb = NP.nb_pmf(np.array([4.0, 10.0]), 5.0, 80)
    assert np.allclose(nb.sum(1), 1) and np.allclose((nb * np.arange(80)).sum(1), [4.0, 10.0], atol=1e-3)
    assert NP.no_vig(1.9, 1.9) == pytest.approx(0.5) and NP.no_vig(1.5, 2.6) == pytest.approx((1 / 1.5) / (1 / 1.5 + 1 / 2.6))
    assert NP.blend(np.array([.7]), np.array([.5]), 1.0)[0] == pytest.approx(.5)


def test_name_matching_never_guesses():
    rows = [{"season": "2023-24", "team": "NOP", "pid": 1, "name": "Herbert Jones"},
            {"season": "2023-24", "team": "NOP", "pid": 2, "name": "Trey Murphy III"},
            {"season": "2023-24", "team": "POR", "pid": 3, "name": "Jabari Walker"},
            {"season": "2023-24", "team": "POR", "pid": 4, "name": "Jalen Walker"}]
    full, short = PD.names_by_team_season(rows)
    m = lambda n: PD.match_player(n, "2023-24", ("NOP", "POR"), full, short)
    assert m("Herb Jones") == 1 and m("Trey Murphy") == 2 and m("T. Murphy") == 2
    assert m("J Walker") is None                                 # two Walkers: ambiguous, dropped
    assert PD.norm("R.J. Barrett") == PD.norm("RJ Barrett")


def test_live_lines_stop_at_the_cutoff():
    d = pathlib.Path(tempfile.mkdtemp())
    q = sqlite3.connect(d / "l.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    tip = "2026-10-26T00:00:00Z"
    for t, ln in (("2026-10-25T20:00:00", 20.5), ("2026-10-25T23:45:00", 24.5)):      # the 23:45 move is after T-30
        for side in ("over", "under"):
            q.execute("INSERT INTO quotes VALUES (?, 'fd', 'G', ?, 7, '', 'points', ?, ?, 1.9)", (t, tip, ln, side))
    q.execute("INSERT INTO quotes VALUES ('2026-10-25T23:45:00','fd','G',?,7,'','points',20.5,'over',NULL)", (tip,))
    q.commit()
    out = PD.load_live_lines(d / "l.sqlite", cutoff_min=30)
    assert [(r["line"], r["snap"]) for r in out] == [(20.5, "2026-10-25T20:00:00")]


def test_analog_pool_is_strictly_earlier():
    import nba_proj_eval as E
    rows = synth()
    run = E.Run(rows, CFG)
    idx = np.array([i for i, r in enumerate(rows) if r["season"] == "2023-24"])
    seen = []
    orig = E.NP.neighbors
    def spy(tf, pf, K, scale):
        seen.append(len(pf))
        return orig(tf, pf, K, scale)
    E.NP.neighbors = spy
    try:
        for mth in sorted({run.date[i][:7] for i in idx}):
            pool = E.pool_index(run, mth + "-01")
            assert (run.date[pool] < mth + "-01").all() and len(pool)
        run.dist(idx)
    finally:
        E.NP.neighbors = orig
    assert seen and all(n > 0 for n in seen)
