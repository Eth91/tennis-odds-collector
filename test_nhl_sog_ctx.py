"""NHL_SOG_PREREG.md amendment 1 guards for nhl_sog_ctx.py: the context features read only games before the date (Cum,
TeamGD, the team's last 5 games), last game's linemates for C (tonight's only for T), and last season's EDGE.
MUTANTS in test_mutants()."""
import importlib
import json
import math
import pathlib
import sqlite3
import sys
import tempfile
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nhl_sog_ctx as X

D = ["2023-10-1%d" % i for i in range(1, 7)]          # games 1..6, 2023-24
GID = [2023020001 + i for i in range(6)]


def g(pid, i, grp="F", ev=15.0, att=4, team="AAA"):
    return {"gid": GID[i], "pid": pid, "date": D[i], "season": 2023, "po": False, "team": team, "opp": "BBB", "grp": grp,
            "att": att, "shots": 2, "min_ev": ev, "min_pp": 2.0, "min_sh": 0.0, "name": str(pid)}


def fixture(mod):
    """Player 1 plays games 1-2, misses 3-5, returns for 6. Player 2 (a regular) plays 1-5 and sits 6. Player 3 plays all
    and has 10 points in game 6. Player 4 debuts in 6. Linemates: game 2 -> 3, 2 (defenseman 11 skipped); game 6 first period -> 4, 3."""
    plays = {1: [0, 1, 5], 2: [0, 1, 2, 3, 4], 3: [0, 1, 2, 3, 4, 5], 4: [5], 5: [0, 1, 2, 3, 4, 5], 11: list(range(6))}
    by_pid = {p: [g(p, i, grp="D" if p == 11 else "F", ev=12.0 if p == 2 else 15.0) for i in ix] for p, ix in plays.items()}
    games = {GID[i]: (D[i], {"AAA": "BBB", "BBB": "AAA"}) for i in range(6)}
    recs = {(x["gid"], p): (x, {"mins": {"ev": 15.0}}) for p, gl in by_pid.items() for x in gl}
    db = pathlib.Path(tempfile.mkdtemp()) / "ctx.sqlite"
    con = sqlite3.connect(db)
    mod.ddl(con)
    for p, gl in by_pid.items():
        for x in gl:
            pts = 10 if (p == 3 and x["gid"] == GID[5]) else (2 if p == 3 else 1)
            con.execute("INSERT INTO sx VALUES (?,?,?,?,?,?)", (x["gid"], p, "H", 0, 0, pts))
            con.execute("INSERT INTO pz VALUES (?,?,?,?,?,?,?)", (x["gid"], p, "H", 0.5, 0.3, 0.2, 600))
    for i in range(6):
        con.execute("INSERT INTO tx VALUES (?,?,?,?,?,?)", (GID[i], 1, "H", 3, 1, "BBB"))
        con.execute("INSERT INTO tx VALUES (?,?,?,?,?,?)", (GID[i], 2, "R", 1, 3, "AAA"))
    for gid, p, q, a, f in ((GID[1], 1, 3, 800, 300), (GID[1], 1, 2, 700, 250), (GID[1], 1, 5, 100, 50), (GID[1], 1, 11, 850, 260),
                            (GID[5], 1, 4, 900, 300), (GID[5], 1, 3, 100, 200), (GID[5], 1, 5, 950, 0)):
        con.execute("INSERT INTO lm VALUES (?,?,?,?,?)", (gid, p, q, a, f))
    for s, oz in ((2022, 0.40), (2023, 0.60)):
        raw = {"skater-zone-time": {"zoneTimeDetails": [{"strengthCode": "all", "offensiveZonePctg": oz}], "zoneStarts": {}},
               "skater-shot-location-detail": {"shotLocationTotals": [{"locationCode": "all", "sog": 10}]},
               "skater-shot-speed-detail": {}, "skater-skating-speed-detail": {}}
        for ep, d in raw.items():
            con.execute("INSERT INTO edge VALUES (?,?,?,?)", (s, 1, ep, zlib.compress(json.dumps(d).encode())))
    con.commit()
    con.close()
    for p, gl in by_pid.items():                          # a 2022 game so EDGE 2022 has games played
        if p == 1:
            gl.insert(0, dict(g(p, 0), gid=2022020001, date="2022-10-11", season=2022))
    return by_pid, games, recs, db


def check_features(mod=X):
    by_pid, games, recs, db = fixture(mod)
    f = mod.features(by_pid, games, recs, db)[(GID[5], 1)]
    hrs, hrs2 = 17.0 / 60, 14.0 / 60                      # even + power-play minutes a game (player 2 plays 12 + 2)
    c_expect = (2 * 5 / (5 * hrs) + 1 * 5 / (5 * hrs2)) / 2  # forwards 3 and 2 over games 1-5 (not game 6's 10 points)
    ok = math.isclose(f["c_pts"], c_expect) and f["c_missing"] == 0.0
    ok &= math.isclose(f["t_pts"], 2 * 5 / (5 * hrs))     # tonight: 4 (no history) and 3
    ok &= f["layoff"] == 1.0                              # missed games 3-5
    ok &= math.isclose(f["freed_ev"], 12.0 / 4)           # player 2's 12 minutes over the 4 forwards dressed
    ok &= f["e_oz_time"] == 0.40                          # last season's EDGE
    ok &= f["margin"] == 4.0                              # +2 a game against -2
    f2 = mod.features(by_pid, games, recs, db)[(GID[1], 1)]
    ok &= f2["layoff"] == 0.0 and math.isclose(f2["freed_ev"], 0.0)
    return bool(ok)


def check_cum(mod=X):
    rows = {7: [("2022-11-01", 2022, dict.fromkeys(mod.CUM_KEYS, 1.0)) for _ in range(40)]
            + [("2023-10-10", 2023, dict.fromkeys(mod.CUM_KEYS, 5.0)), ("2023-10-12", 2023, dict.fromkeys(mod.CUM_KEYS, 9.0))]}
    c = mod.Cum(rows)
    a, n = c.get(7, 2023, "2023-10-12")
    ok = n == 21 and a["att"] == 25.0                     # 40 games last season as 20; the date's own game not read
    ok &= c.get(7, 2023, "2023-10-10")[1] == 20
    t = mod.TeamGD([("2023-10-10", 2023, "AAA", 3, 1), ("2023-10-12", 2023, "AAA", 0, 5)])
    ok &= t.get("AAA", 2023, "2023-10-12") == 2.0 and t.get("AAA", 2023, "2023-10-10") is None
    return bool(ok)


def test_guards():
    assert check_cum() and check_features()


def mutant(path, name, a, b, check):
    src = pathlib.Path(path).read_text()
    assert src.count(a) == 1, (name, a)
    d = pathlib.Path(tempfile.mkdtemp())
    (d / f"{name}.py").write_text(src.replace(a, b))
    sys.path.insert(0, str(d))
    try:
        m_ = importlib.import_module(name)
        try:
            return check(m_)
        except Exception:
            return False
    finally:
        sys.path.remove(str(d))
        sys.modules.pop(name, None)


def test_mutants():
    for tag, a, b, check in (
            ("Cum reads the date", "i = bisect.bisect_left(ds, date)", "i = bisect.bisect_right(ds, date)", check_cum),
            ("Cum last season unweighted", "w = min(1.0, B.LAST_AS / len(ds))", "w = 1.0", check_cum),
            ("TeamGD reads the date", "bisect.bisect_left(idx, (season, date))]]", "bisect.bisect_right(idx, (season, date))]]",
             check_cum),
            ("C from tonight's game", "pg = gl[i - 1]", "pg = gl[i]", check_features),
            ("team games include tonight", 'sched[t][:bisect.bisect_left(sdates[t], g["date"])]',
             'sched[t][:bisect.bisect_right(sdates[t], g["date"])]', check_features),
            ("this season's EDGE", 'edge.get((g["season"] - 1, pid))', 'edge.get((g["season"], pid))', check_features),
            ("linemates any group", 'gmin[(gid, q)][2] == grp:', 'True:', check_features)):
        assert not mutant(X.__file__, "nhl_sog_ctx_mut", a, b, check), tag
