"""NHL_SOG_PREREG.md guards for nhl_sog.py: a game's history is his games before its date only (a same-day game never
counts), last season is worth at most 20 games, 3+ games are needed, the opponent factor reads games before the date,
the main line is the two-sided rung closest to even, and a whole-number line is read given no push. MUTANTS in
test_mutants()."""
import importlib
import math
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nhl_sog as M


def game(gid, date, season, shots, ev=15.0, pp=2.0):
    g = {"gid": gid, "date": date, "season": season, "shots": shots, "att": 2 * shots, "att_ev": 2 * shots, "att_pp": 0,
         "att_sh": 0, "sog_ev": shots, "sog_pp": 0, "sog_sh": 0, "min_ev": ev, "min_pp": pp, "min_sh": 0.0}
    return g


def check_history(mod=M):
    last = [game(i, f"2022-{10 + i // 28:02d}-{1 + i % 28:02d}", 2022, 1) for i in range(40)]
    this = [game(100, "2023-10-10", 2023, 5, ev=20.0), game(101, "2023-10-12", 2023, 3), game(102, "2023-10-12", 2023, 9),
            game(103, "2023-10-14", 2023, 0)]
    h = {g["gid"]: f for g, f in mod.history(last + this)}
    ok = h[0] is None and h[2] is None and h[3] is not None              # 3+ games needed
    ok &= h[100]["Wn"] == 20 and h[100]["avg"] == 1.0                   # 40 games last season count as 20
    ok &= h[101]["Wn"] == 21 and math.isclose(h[101]["avg"], 25 / 21)
    ok &= h[102]["Wn"] == h[101]["Wn"] and h[102]["avg"] == h[101]["avg"]  # the same day's game is not history
    ok &= h[103]["Wn"] == 23 and math.isclose(h[103]["avg"], 37 / 23)
    ok &= h[101]["last1_ev"] == 20.0 and h[100]["last1_ev"] == 15.0     # last game across seasons
    short = [game(i, f"2022-11-{1 + i:02d}", 2022, 2) for i in range(4)] + [game(200, "2023-10-10", 2023, 0)]
    ok &= mod.history(short)[-1][1]["Wn"] == 4                          # under 20 games: each counts 1
    later = mod.history(last + this[:1] + [dict(this[1], shots=50)])    # a later game never reaches an earlier one
    ok &= later[40][1]["avg"] == h[100]["avg"]
    return bool(ok)


def check_opp(mod=M):
    tg = {"AAA": [("2023-10-10", 2023, 30.0), ("2023-10-12", 2023, 40.0)],
          "BBB": [("2022-11-01", 2022, 20.0), ("2023-10-10", 2023, 20.0), ("2023-10-12", 2023, 99.0)]}
    o = mod.Opp(tg)
    ok = o.blended("AAA", 2023, "2023-10-12") == 30.0                   # the game's own date is not read
    ok &= o.blended("BBB", 2023, "2023-10-12") == 20.0
    ok &= o.blended("AAA", 2023, "2023-10-10") is None
    ok &= math.isclose(o.factor("AAA", 2023, "2023-10-12"), 1 + 0.5 * (30 / 25 - 1))
    return bool(ok)


def check_p_over(mod=M):
    pois = 1 - 3 * math.exp(-2)
    ok = abs(mod.p_over(2.0, 1.5, 1e6) - pois) < 1e-4
    d = mod.st.nbinom(5.0, 5.0 / 7.0)
    ok &= math.isclose(mod.p_over(2.0, 2.0, 5.0), d.sf(2) / (1 - d.pmf(2)))
    return bool(ok)


def check_rungs(mod=M):
    db = pathlib.Path(tempfile.mkdtemp()) / "o.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE props (event_id, commence_time, home_team, away_team, book, market, player, side, line, price, snap_kind)")
    rows = [("fanduel", 2.5, "over", 1.80), ("fanduel", 2.5, "under", 2.05), ("draftkings", 2.5, "over", 1.85),
            ("draftkings", 2.5, "under", 1.95), ("fanduel", 3.5, "over", 2.60), ("fanduel", 3.5, "under", 1.50),
            ("draftkings", 1.5, "over", 2.00), ("betmgm", 2.5, "under", 3.00)]
    con.executemany("INSERT INTO props VALUES ('e1', '2024-01-02T01:00:00Z', 'Edmonton Oilers', 'Calgary Flames', ?, "
                    "'player_shots_on_goal', 'Connor McDavid', ?, ?, ?, 'tip')", [(b, s, l, p) for b, l, s, p in rows])
    con.commit()
    con.close()
    r = mod.main_rungs(db)[("e1", "connor mcdavid")]
    q = (1 / 1.80) / (1 / 1.80 + 1 / 2.05)
    return r[0] == "2024-01-01" and r[3:6] == (2.5, 1.85, 2.05) and math.isclose(r[6], q)


def check_bets(mod=M):
    b = {"p": 0.6, "over": 1.9, "under": 2.0, "act": 3, "line": 2.5}
    got = mod.bets_of([b, dict(b, p=0.5), dict(b, p=0.3, act=1)], "p")
    return [(x["side"], round(x["u"], 9)) for x in got] == [("over", 0.9), ("under", 1.0)]


def test_guards():
    assert check_history() and check_opp() and check_p_over() and check_rungs() and check_bets()


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
            ("same-day game as history", 'while j < len(games) and games[j]["date"] == games[i]["date"]:\n            j += 1',
             "j = i + 1", check_history),
            ("last season unweighted", "w = min(1.0, LAST_AS / nl) if nl else 0.0", "w = 1.0 if nl else 0.0", check_history),
            ("no game minimum", "if nt + nl >= MIN_GAMES and recent:", "if recent:", check_history),
            ("opponent reads the game day", "bisect.bisect_left(idx, (season, date))", "bisect.bisect_right(idx, (season, date + 'z'))",
             check_opp),
            ("opponent not pulled", "1 + OPP_PULL * (x / lg - 1)", "x / lg", check_opp),
            ("whole line counts the push", "d.sf(line) / (1 - d.pmf(line))", "d.sf(line)", check_p_over),
            ("one-sided rungs", "two = {b: v for b, v in bk.items() if v[0] and v[1]}",
             "two = {b: v for b, v in bk.items() if v[0] or v[1]}", check_rungs),
            ("UTC date", ".astimezone(ET).date()", ".date()", check_rungs),
            ("bets below 5%", "if max(eo, eu) >= EV_MIN:", "if max(eo, eu) >= 0:", check_bets)):
        assert not mutant(M.__file__, "nhl_sog_mut", a, b, check), tag
