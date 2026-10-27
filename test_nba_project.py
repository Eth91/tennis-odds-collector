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
         "        for j in t_by_date.get(d, []):\n            out_t[j] = predict(targets[j], parts=True)\n"
         "        update([rows[i] for i in by_date.get(d, [])])\n")
    b = ("        update([rows[i] for i in by_date.get(d, [])])\n        for i in by_date.get(d, []):\n"
         "            if keep is None or i in keep:\n                out[i] = predict(rows[i])\n"
         "        for j in t_by_date.get(d, []):\n            out_t[j] = predict(targets[j], parts=True)\n")
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


def test_input_breakdown_multiplies_to_the_projection():
    """The page's breakdown (minutes x rate x opponent x pace x home x b2b) must be the projection, not a story."""
    rows = synth()
    tgt = [{"season": "2023-24", "date": "2099-01-01", "pid": 102, "team": "AAA", "opp": "BBB", "home": h, "group": "C"}
           for h in (0, 1)]
    _, ot = NP.walk(rows, CFG, targets=tgt)
    for o in ot:
        hit = {"parts": [o["parts"]], "mu": [o["m1"]]}
        b = NP.inputs_of(hit, 0)
        assert b["min"] * b["min_f"]["home"] * b["min_f"]["b2b"] == pytest.approx(o["m1"][0], rel=1e-3)
        for k, st in enumerate(NP.STATS[1:], 1):
            assert b["min"] * np.prod(b[st]) == pytest.approx(o["m1"][k], rel=2e-3, abs=1e-3), st
    assert NP.inputs_of({"mu": [ot[0]["m1"]]}, 0) is None                    # an older cache: no breakdown, no guess


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


# ── the live path: payload contract, JS = Python, the prospective record ───────────────────────────────────
NODE = __import__("shutil").which("node")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_js_projection_probabilities_match_python():
    import json
    import subprocess
    import nba_research_ui as UI
    rnd = np.random.default_rng(3)
    v = np.zeros((1, 300, NP.NS))
    v[0, :, 1] = rnd.gamma(4, 4, 300)                          # points
    d = _dist(v)
    pm = NP.compact_pmf(d.pmf("points", 160)[0])
    lines = [9.5, 14.5, 15.0, 20.0, 27.5]
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "core.js").write_text(UI.JS_CORE)
    (tmp / "t.js").write_text("const C=require('./core.js');const a=JSON.parse(process.argv[2]);"
                              "console.log(JSON.stringify(a.lines.map(l=>C.projProbs(a.pm,l))));")
    js = json.loads(subprocess.run([NODE, str(tmp / "t.js"), json.dumps({"pm": pm, "lines": lines})], capture_output=True,
                                   text=True, check=True, cwd=tmp).stdout)
    for L, r in zip(lines, js):
        o, u, p = d.probs("points", [L])
        assert r["over"] == pytest.approx(o[0], abs=2e-3) and r["push"] == pytest.approx(p[0], abs=2e-3)
    assert js[3]["push"] > 0 and js[0]["push"] == 0                       # a whole line can push, a half cannot


def test_payload_never_invents_a_projection(monkeypatch):
    import datetime as dt_
    now = dt_.datetime(2026, 10, 26, 18, 0, tzinfo=dt_.timezone.utc)
    props = [{"id": "G|7|points", "gid": "G", "pid": 7, "market": "points", "team": "AAA", "opp": "BBB", "home": True, "books": {}}]
    games = [{"gid": "G", "date_et": "2026-10-26", "utc": "2026-10-27T00:00:00Z"}]
    monkeypatch.setattr(NP, "TUNED_ON", None)
    by, pl, meta = NP.for_payload(props, games, now)
    assert by == {} and meta["error"]                                     # not frozen: no numbers
    monkeypatch.setattr(NP, "TUNED_ON", "2023-24")
    d = pathlib.Path(tempfile.mkdtemp())
    by, pl, meta = NP.for_payload(props, games, now, cache=d / "none.pkl")
    assert by == {} and "not computed yet" in meta["error"]               # no cache: no numbers
    assert NP.refresh([{"gid": "G", "date": "2026-10-26", "pid": 7, "team": "AAA", "opp": "BBB", "home": 1}],
                      gamelogs=d / "x.sqlite", matchup=d / "y.sqlite", profiles=d / "z.sqlite", cache=d / "c.pkl") == "no box scores"


def test_refresh_then_payload_and_stale(monkeypatch):
    import datetime as dt_
    import os
    rows = synth()
    monkeypatch.setattr(NP.PD, "load_box", lambda *a, **k: (rows, [], {}))
    monkeypatch.setattr(NP, "availability_table", lambda *a, **k: {"Out": [0, 3]})
    d = pathlib.Path(tempfile.mkdtemp())
    for f in ("gl.sqlite", "mu.sqlite"):
        (d / f).write_text("x")
    kw = dict(gamelogs=d / "gl.sqlite", matchup=d / "mu.sqlite", cache=d / "c.pkl")
    tg = [{"gid": "G", "date": "2024-02-01", "pid": 102, "team": "AAA", "opp": "BBB", "home": 1}]
    assert NP.refresh(tg, news=d / "news.sqlite", **kw).startswith("projected 1 players")
    assert NP.refresh(tg, **kw).startswith("cache current")                  # nothing changed: skipped
    props = [{"id": "G|102|points", "gid": "G", "pid": 102, "market": "points", "team": "AAA", "opp": "BBB", "home": True,
              "books": {"fd": {"main": 9.5, "rungs": [[9.5, 1.9, 1.9]]}}},
             {"id": "G|999|points", "gid": "G", "pid": 999, "market": "points", "team": "AAA", "opp": "BBB", "home": True,
              "books": {}}]                                                   # not in the cache: left unprojected
    games = [{"gid": "G", "date_et": "2024-02-01", "utc": "2024-02-02T00:00:00Z"}]
    now = dt_.datetime(2024, 2, 1, 18, 0, tzinfo=dt_.timezone.utc)
    by, pl, meta = NP.for_payload(props, games, now, log_db=d / "log.sqlite", **kw)
    s = by["G|102|points"]
    assert meta["error"] is None and s["q10"] <= s["q50"] <= s["q90"] and sum(s["pmf"][1]) == pytest.approx(1, abs=2e-3)
    assert "G|999|points" not in by and meta["coverage"] == {"props": 2, "projected": 1, "thin_history": 0, "players": 1,
                                                             "unknown_position": 0}
    assert pl["102"]["inputs"]["mu"]["pts"] == pytest.approx(NP.load_cache(d / "c.pkl")["mu"][0][1], abs=.01)
    assert set(pl["102"]) >= {"min", "steals", "blocks", "turnovers"} and meta["logged"] == 1 and meta["drift"]["pts"] is not None
    assert meta["stale"] is False and not meta.get("refresh_pending") and meta["availability"] == {"Out": [0, 3]}
    os.utime(d / "mu.sqlite", (1, 2))                                        # new box scores since the refresh
    _, _, m2 = NP.for_payload(props, [dict(games[0], date_et="2024-06-01")], now, **kw)
    assert m2["refresh_pending"] is True and m2["stale"] is True and "days before the slate" in m2["stale_reason"]


def test_forecast_log_keeps_first_and_last_before_cutoff():
    import datetime as dt_
    db = pathlib.Path(tempfile.mkdtemp()) / "f.sqlite"
    it = lambda p: {"gid": "G", "pid": 7, "market": "points", "tip": "2026-10-27T00:00:00Z", "line": 20.5, "book": "fd",
                    "over": 1.9, "under": 1.9, "p_over": p, "p_push": 0.0, "p_blend": p, "mean": 21.0}
    for h, m, p in ((18, 0, .55), (23, 20, .60), (23, 40, .99)):              # the 23:40 build is past tip - 30
        NP.log_forecasts(db, [it(p)], dt_.datetime(2026, 10, 26, h, m, tzinfo=dt_.timezone.utc))
    rows = dict(sqlite3.connect(db).execute("SELECT kind, p_over FROM forecasts").fetchall())
    assert rows == {"first": .55, "cutoff": .60}


def test_prospective_grading_voids_and_clv_sign():
    import json
    import nba_proj_eval as E
    d = pathlib.Path(tempfile.mkdtemp())
    lg = sqlite3.connect(d / "log.sqlite")
    lg.execute("CREATE TABLE forecasts (kind TEXT, logged_at TEXT, gid TEXT, pid INTEGER, market TEXT, tip TEXT, line REAL, "
               "book TEXT, over REAL, under REAL, p_over REAL, p_push REAL, p_blend REAL, mean REAL, version TEXT)")
    tip = "2026-10-27T00:00:00Z"
    for kind, pid, line, o, u, p in (("first", 1, 20.5, 1.9, 1.9, .60), ("cutoff", 1, 20.5, 1.8, 2.0, .62),
                                     ("cutoff", 2, 9.5, 1.9, 1.9, .40), ("cutoff", 3, 6.0, 1.9, 1.9, .50)):
        lg.execute("INSERT INTO forecasts VALUES (?, 't', 'G', ?, 'points', ?, ?, 'fd', ?, ?, ?, 0, ?, 0, ?)",
                   (kind, pid, tip, line, o, u, p, p, NP.VERSION))
    lg.commit()
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    for side, odds in (("over", 1.7), ("under", 2.15)):                    # the close moved toward the over
        q.execute("INSERT INTO quotes VALUES ('2026-10-26T23:50:00','fd','G',?,1,'','points',20.5,?,?)", (tip, side, odds))
    q.commit()
    m = sqlite3.connect(d / "mu.sqlite")
    m.execute("CREATE TABLE games (gid TEXT, season TEXT, date TEXT, home TEXT, away TEXT, home_pts REAL, away_pts REAL)")
    m.execute("CREATE TABLE player_games (gid TEXT, team TEXT, pid INTEGER, pos TEXT, starter INTEGER, min REAL, pts REAL, "
              "reb REAL, ast REAL, fg3m REAL, stl REAL, blk REAL, tov REAL, fga REAL, fg3a REAL, fta REAL)")
    m.execute("INSERT INTO games VALUES ('G','2026-27','2026-10-26','AAA','BBB',100,99)")
    m.execute("INSERT INTO player_games VALUES ('G','AAA',1,'G',1,34,25,1,1,1,0,0,1,0,0,0)")    # over
    m.execute("INSERT INTO player_games VALUES ('G','AAA',2,'G',1,0,0,0,0,0,0,0,0,0,0,0)")      # DNP: void
    m.execute("INSERT INTO player_games VALUES ('G','AAA',3,'G',1,20,6,0,0,0,0,0,0,0,0,0)")     # 6 on 6.0: push, void
    m.commit()
    out = E.prospective(d / "log.sqlite", d / "lines.sqlite", d / "mu.sqlite", d / "o.json")
    assert out["graded"] == 1 and out["with_close"] == 1
    p_then, p_close = NP.no_vig(1.9, 1.9), NP.no_vig(1.7, 2.15)
    assert out["clv"]["n"] == 1 and out["clv"]["mean"] == pytest.approx(p_close - p_then) and out["clv"]["mean"] > 0
    assert json.loads((d / "o.json").read_text())["graded"] == 1
    assert out["reliability_model"][6] == [1, pytest.approx(.62), 1.0] and sum(n for n, _, _ in out["reliability_close"]) == 1


def test_prospective_close_follows_a_rescheduled_tip():
    """A postponed game keeps its gid; the close is the board before the new tip, not the original date's."""
    import nba_proj_eval as E
    d = pathlib.Path(tempfile.mkdtemp())
    lg = sqlite3.connect(d / "log.sqlite")
    lg.execute("CREATE TABLE forecasts (kind TEXT, logged_at TEXT, gid TEXT, pid INTEGER, market TEXT, tip TEXT, line REAL, "
               "book TEXT, over REAL, under REAL, p_over REAL, p_push REAL, p_blend REAL, mean REAL, version TEXT)")
    old, new = "2026-10-26T00:00:00Z", "2026-10-28T00:00:00Z"
    for kind in ("first", "cutoff"):
        lg.execute("INSERT INTO forecasts VALUES (?, 't', 'G', 1, 'points', ?, 20.5, 'fd', 1.9, 1.9, .6, 0, .6, 0, ?)",
                   (kind, new, NP.VERSION))
    lg.commit()
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    for seen, tip, o, u in (("2026-10-25T23:00:00", old, 1.9, 1.9), ("2026-10-27T23:50:00", new, 1.7, 2.15)):
        for side, odds in (("over", o), ("under", u)):
            q.execute("INSERT INTO quotes VALUES (?,'fd','G',?,1,'','points',20.5,?,?)", (seen, tip, side, odds))
    q.commit()
    m = sqlite3.connect(d / "mu.sqlite")
    m.execute("CREATE TABLE games (gid TEXT, season TEXT, date TEXT, home TEXT, away TEXT, home_pts REAL, away_pts REAL)")
    m.execute("CREATE TABLE player_games (gid TEXT, team TEXT, pid INTEGER, pos TEXT, starter INTEGER, min REAL, pts REAL, "
              "reb REAL, ast REAL, fg3m REAL, stl REAL, blk REAL, tov REAL, fga REAL, fg3a REAL, fta REAL)")
    m.execute("INSERT INTO games VALUES ('G','2026-27','2026-10-27','AAA','BBB',100,99)")
    m.execute("INSERT INTO player_games VALUES ('G','AAA',1,'G',1,34,25,1,1,1,0,0,1,0,0,0)")
    m.commit()
    out = E.prospective(d / "log.sqlite", d / "lines.sqlite", d / "mu.sqlite", d / "o.json")
    assert out["clv"]["mean"] == pytest.approx(NP.no_vig(1.7, 2.15) - NP.no_vig(1.9, 1.9))


def test_verdicts_follow_the_prereg_lines():
    import nba_proj_eval as E
    rel_ok = [[300, .5, .51]] * 3
    good = {"norm_crps_m1_minus_b2": [-.01, -.02, -.005], "norm_crps_m1_minus_b1": [-.01, -.02, -.005],
            "stats": {"pts": {"pit_deciles": [.1] * 10}},
            "market": {"n": 5000, "blend_minus_market_ll": [-.002, -.003, -.001], "m1_minus_market_ll": [-.002, -.003, -.001],
                       "reliability_m1": rel_ok, "reliability_blend": rel_ok}}
    P = {E.TEST_A: good, E.TEST_B: good, E.TEST_C: dict(good, label="replay")}
    v = E.verdicts(P)                                           # no prospective record: C is not established
    assert "YES" in v[0] and "YES" in v[1] and "YES" in v[2]
    assert "NOT ESTABLISHED" in v[4] and "(C has 0 graded props" in v[4] and v[5].endswith("NO.")
    pro = {"with_close": 2500, "blend_minus_close": [-.001, -.002, -.0005], "model_minus_close": [-.001, -.002, -.0004]}
    v = E.verdicts(P, prospective=pro)
    assert "YES" in v[4] and v[5].endswith("YES.")
    touches = dict(good, norm_crps_m1_minus_b2=[-.01, -.02, .001])           # CI reaching 0: not a win
    assert "NO" in E.verdicts({E.TEST_A: touches, E.TEST_B: good})[0]


def test_verdicts_never_pass_on_missing_data():
    import nba_proj_eval as E
    v = E.verdicts({})
    assert all(("NO" in x or "NOT ESTABLISHED" in x) for x in v) and "fails" in v[2]


def test_cli_guard_comes_after_every_definition():
    """The nightly grader once died with NameError: main() ran before prospective() was defined."""
    import ast
    for f in ("nba_project.py", "nba_proj_eval.py", "nba_proj_data.py"):
        body = ast.parse((pathlib.Path(__file__).parent / f).read_text()).body
        guards = [i for i, n in enumerate(body) if isinstance(n, ast.If) and "__main__" in ast.dump(n.test)]
        assert all(i == len(body) - 1 for i in guards), f


def test_prospective_moved_line_pulled_postponed_and_fd_filter():
    """Audit fixes C2/C5/C6: a moved line is graded at the close's main line from the logged pmf; a pulled
    market has no close; a forecast for the wrong ET date is void; the FanDuel-only metrics leave DraftKings out."""
    import json
    import datetime as dt_
    import nba_proj_eval as E
    d = pathlib.Path(tempfile.mkdtemp())
    tip = "2026-10-27T00:00:00Z"
    pm = [10, [0.1] * 10]                                       # uniform over 10..19
    items = [{"gid": "G", "pid": 1, "market": "points", "tip": tip, "line": 13.5, "book": "fd", "over": 1.9, "under": 1.9,
              "p_over": .6, "p_push": 0, "p_blend": .55, "mean": 14.5, "pmf": pm},          # line moves to 15.5
             {"gid": "G", "pid": 2, "market": "points", "tip": tip, "line": 13.5, "book": "fd", "over": 1.9, "under": 1.9,
              "p_over": .6, "p_push": 0, "p_blend": .55, "mean": 14.5, "pmf": pm},          # market pulled
             {"gid": "G", "pid": 3, "market": "points", "tip": tip, "line": 13.5, "book": "dk", "over": 1.9, "under": 1.9,
              "p_over": .6, "p_push": 0, "p_blend": .55, "mean": 14.5, "pmf": pm},          # DraftKings, unmoved
             {"gid": "H", "pid": 4, "market": "points", "tip": "2026-10-30T00:00:00Z", "line": 13.5, "book": "fd",
              "over": 1.9, "under": 1.9, "p_over": .6, "p_push": 0, "p_blend": .55, "mean": 14.5, "pmf": pm}]  # postponed
    NP.log_forecasts(d / "log.sqlite", items, dt_.datetime(2026, 10, 26, 18, tzinfo=dt_.timezone.utc))
    q = sqlite3.connect(d / "lines.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT, stat TEXT, "
              "line REAL, side TEXT, odds REAL)")
    ins = lambda t, bk, pid, line, side, odds: q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,'','points',?,?,?)",
                                                        (t, bk, "G", tip, pid, line, side, odds))
    for side in ("over", "under"):
        ins("2026-10-26T18:00:00", "fd", 1, 13.5, side, 1.9)
        ins("2026-10-26T18:00:00", "fd", 2, 13.5, side, 1.9)
        ins("2026-10-26T18:00:00", "dk", 3, 13.5, side, 1.9)
    ins("2026-10-26T23:00:00", "fd", 1, 13.5, "over", None); ins("2026-10-26T23:00:00", "fd", 1, 13.5, "under", None)
    ins("2026-10-26T23:00:00", "fd", 1, 15.5, "over", 2.0); ins("2026-10-26T23:00:00", "fd", 1, 15.5, "under", 1.8)
    ins("2026-10-26T23:10:00", "fd", 2, 13.5, "over", None); ins("2026-10-26T23:10:00", "fd", 2, 13.5, "under", None)
    q.commit()
    m = sqlite3.connect(d / "mu.sqlite")
    m.execute("CREATE TABLE games (gid TEXT, season TEXT, date TEXT, home TEXT, away TEXT, home_pts REAL, away_pts REAL)")
    m.execute("CREATE TABLE player_games (gid TEXT, team TEXT, pid INTEGER, pos TEXT, starter INTEGER, min REAL, pts REAL, "
              "reb REAL, ast REAL, fg3m REAL, stl REAL, blk REAL, tov REAL, fga REAL, fg3a REAL, fta REAL)")
    m.execute("INSERT INTO games VALUES ('G','2026-27','2026-10-26','AAA','BBB',100,99)")
    m.execute("INSERT INTO games VALUES ('H','2026-27','2026-10-28','AAA','BBB',100,99)")             # played on the 28th
    for pid, g in ((1, "G"), (2, "G"), (3, "G"), (4, "H")):
        m.execute("INSERT INTO player_games VALUES (?,'AAA',?,'G',1,30,17,0,0,0,0,0,0,0,0,0)", (g, pid))
    m.commit()
    recs = []
    out = E.prospective(d / "log.sqlite", d / "lines.sqlite", d / "mu.sqlite", d / "o.json", recs_out=recs)
    by = {r["key"][1]: r for r in recs}
    assert out["counts"]["void_postponed"] == 1 and 4 not in by
    assert by[1]["moved"] and by[1]["key"][3] == 15.5 and by[1]["p"] == pytest.approx(0.4) and by[1]["pb"] is None
    assert by[1]["pc"] == pytest.approx(NP.no_vig(2.0, 1.8)) and by[1]["y"] == 1.0                 # 17 > 15.5
    assert by[2]["pc"] is None and out["counts"]["pulled_before_tip"] == 1
    assert out["with_close"] == 2 and out["with_close_fd"] == 1                                    # DraftKings row left out
    assert by[1]["date"] == "2026-10-26"                                                           # ET date, not UTC
