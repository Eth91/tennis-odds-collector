"""nba_reaction (amendment 5) and nba_watch.follow_due: reaction times from the change log, the
team/control split, pre-moves, pulls, price-only moves, poll-gap resolution, the reading rules, and the
replay's agreement with nba_clv.close_of. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F
import nba_reaction as RX
import nba_watch as W

HERE = pathlib.Path(__file__).resolve().parent
T0 = "2026-01-09T22:00:04"
TIP1, TIP2 = "2026-01-10T00:30:00Z", "2026-01-10T01:00:00Z"        # 7:30 / 8:00 PM ET on Jan 9


def build(mod):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "idx.json").write_text(json.dumps({"players": {
        "1": ["AAA", "One", "G"], "2": ["AAA", "Two", "F"], "6": ["AAA", "Six", "C"], "9": ["AAA", "Star Nine", "F"],
        "3": ["BBB", "Three", "G"], "4": ["CCC", "Four", "G"], "5": ["CCC", "Five", "F"]}}))
    q = sqlite3.connect(d / "q.sqlite")
    q.executescript("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT,"
                    " stat TEXT, line REAL, side TEXT, odds REAL);"
                    "CREATE TABLE cycles (ts TEXT, book TEXT, status TEXT, rows INTEGER, events INTEGER, "
                    "matched_events INTEGER, resolved INTEGER, unresolved INTEGER, detail TEXT);")
    polls = [f"2026-01-09T21:{m:02d}:20" for m in range(0, 60, 10)]
    polls += [f"2026-01-09T22:{m:02d}:20" for m in range(0, 21)] + ["2026-01-09T22:30:00", "2026-01-09T22:40:00"]
    for p in polls:
        q.execute("INSERT INTO cycles (ts, book, status) VALUES (?,?,?)", (p, "fd", "ok"))
    q.execute("INSERT INTO cycles (ts, book, status) VALUES (?,?,?)", ("2026-01-09T22:02:50", "dk", "ok"))

    def rung(t, gid, pid, stat, line, over, under=1.91, book="fd"):
        tip = TIP1 if gid == "G1" else TIP2
        for side, o in (("over", over), ("under", under if over is not None else None)):
            q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", (t, book, gid, tip, pid, "", stat, line, side, o))
    # pid 1 points: 20.5 -> 22.5 at 22:03:20 (old rung pulled): LINE at 3.27 min, gap 1.0
    rung("2026-01-09T21:00:20", "G1", 1, "points", 20.5, 1.91)
    rung("2026-01-09T22:03:20", "G1", 1, "points", 20.5, None)
    rung("2026-01-09T22:03:20", "G1", 1, "points", 22.5, 1.87)
    rung("2026-01-09T22:02:50", "G1", 1, "points", 24.5, 1.95, book="dk")    # DraftKings: never in the FD clock
    # pid 1 rebounds: pulled at 22:01:20
    rung("2026-01-09T21:00:20", "G1", 1, "rebounds", 5.5, 1.91)
    rung("2026-01-09T22:01:20", "G1", 1, "rebounds", 5.5, None)
    # pid 2 rebounds: moved 21:50 (inside PRE_MIN): pre-moved, then held
    rung("2026-01-09T21:20:20", "G1", 2, "rebounds", 6.5, 1.91)
    rung("2026-01-09T21:50:20", "G1", 2, "rebounds", 6.5, None)
    rung("2026-01-09T21:50:20", "G1", 2, "rebounds", 7.5, 1.91)
    # pid 2 assists: price-only move at 22:05:20
    rung("2026-01-09T21:00:20", "G1", 2, "assists", 4.5, 1.91)
    rung("2026-01-09T22:05:20", "G1", 2, "assists", 4.5, 1.80, 2.02)
    # pid 2 points: TWO two-sided rungs at once (main 10.5 @1.91 + alt 11.5 @2.30): the rule must pick 10.5
    rung("2026-01-09T21:00:20", "G1", 2, "points", 10.5, 1.91)
    rung("2026-01-09T21:00:20", "G1", 2, "points", 11.5, 2.30, 1.60)
    # pid 3 (BBB, the opponent): moves at 22:02:20 but is NOT affected
    rung("2026-01-09T21:00:20", "G1", 3, "points", 15.5, 1.91)
    rung("2026-01-09T22:02:20", "G1", 3, "points", 15.5, None)
    rung("2026-01-09T22:02:20", "G1", 3, "points", 16.5, 1.91)
    # pid 6 (AAA): posted only after T0 -> not measurable
    rung("2026-01-09T22:10:20", "G1", 6, "points", 8.5, 1.91)
    # control game G2: pid 4 moves at 22:30, pid 5 holds
    rung("2026-01-09T21:00:20", "G2", 4, "points", 12.5, 1.91)
    rung("2026-01-09T22:30:00", "G2", 4, "points", 12.5, None)
    rung("2026-01-09T22:30:00", "G2", 4, "points", 13.5, 1.91)
    rung("2026-01-09T21:00:20", "G2", 5, "points", 9.5, 1.91)
    q.commit()
    n = sqlite3.connect(d / "n.sqlite")
    n.execute(W.TRIG_DDL)
    n.execute("INSERT INTO triggers (mark, published_at, detected_at, fresh) VALUES (?,?,?,?)",
              ("2026-01-09T17:00", T0 + "+00:00", "2026-01-09T22:00:09.5+00:00",
               json.dumps(["Star Nine (AAA, 2026-01-09)"])))
    n.commit()
    sh = F._shadow(d / "s.sqlite")
    for fid, at, x in (("f1", "2026-01-09T22:00:25", "Star Nine"), ("f0", "2026-01-09T20:00:00", "Star Nine")):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, gtime, pid) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (fid, at, "2026-01-09", "wowy", "AAA", x, "One", "pts",
                                                         20.5, 1.91, "G1", TIP1, 1))
    sh.commit()
    mod.NEWS, mod.LINES, mod.SHADOW, mod.INDEX = d / "n.sqlite", d / "q.sqlite", d / "s.sqlite", d / "idx.json"
    return mod.run(now="2026-01-09T23:30:00"), d


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    res, d = build(mod)
    want(len(res) == 1, "one trigger read")
    u = res[0]["units"] if res else {"affected": [], "control": [], "flagged": []}
    a = {(x["pid"], x["stat"]): x for x in u["affected"]}
    c = {(x["pid"], x["stat"]): x for x in u["control"]}
    p1 = a.get((1, "points"), {})
    want(p1.get("line_min") is not None and abs(p1["line_min"] - 3.2667) < 0.01 and p1.get("gap_min") == 1.0,
         "line move timed from the change log (3.27 min) with a 1-min poll gap; DraftKings ignored")
    want(a.get((1, "rebounds"), {}).get("pull_min") is not None and a[(1, "rebounds")]["line_min"] is None,
         "a pulled prop is a PULL, not a line move")
    r2 = a.get((2, "rebounds"), {})
    want(r2.get("pre_moved") is True and r2.get("line_min") is None, "moved 10 min before the report = PRE-MOVED")
    a2 = a.get((2, "assists"), {})
    want(a2.get("price_min") is not None and a2.get("line_min") is None, "same line, price 1.91 -> 1.80 = PRICE only")
    want((3, "points") not in a, "the opponent is not 'affected'")
    want((6, "points") not in a, "no FanDuel main at T0 -> not measurable")
    want(set(c) == {(4, "points"), (5, "points")} and abs(c[(4, "points")]["line_min"] - 29.93) < 0.01
         and c[(5, "points")]["line_min"] is None, "control = the untouched game only; its move timed")
    want([(x["pid"], x["stat"]) for x in u["flagged"]] == [(1, "points")],
         "flagged cell = the flag that trigger created (stat spelling canonicalised), not the older one")
    # the replay agrees with nba_clv.close_of(..., books=("fd",)) at every checkpoint
    spec = importlib.util.spec_from_file_location("_clv_for_test", HERE / "nba_clv.py")
    V = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(V)
    q = sqlite3.connect(d / "q.sqlite")
    agree = True
    want(a.get((2, "points"), {}).get("line0") == 10.5, "main rung = the line nearest even money, not the alt")
    for gid, pid, stat in (("G1", 1, "points"), ("G1", 2, "rebounds"), ("G1", 2, "assists"), ("G1", 1, "rebounds"),
                           ("G1", 2, "points")):
        tl = mod.timeline(q.execute("SELECT seen_at, line, side, odds FROM quotes WHERE book='fd' AND gid=? AND pid=? "
                                    "AND stat=?", (gid, pid, stat)).fetchall())
        for t in ("2026-01-09T21:30:00", "2026-01-09T21:55:00", "2026-01-09T22:02:00", "2026-01-09T22:04:00",
                  "2026-01-09T22:06:00"):
            cl = V.close_of(q, gid, pid, stat, t, books=("fd",))
            agree &= (mod.main_at(tl, t) == (cl[:2] if cl else None))
    want(agree, "replayed main rung == nba_clv.close_of(books=fd) at every checkpoint")
    return ok


def test_reaction():
    assert check(RX)


def test_reading_rules():
    def unit(line_min, pre=False):
        return {"pid": 1, "line_min": line_min, "pre_moved": pre, "pull_min": None, "price_min": None, "gap_min": 1.0}

    def results(aff, ctl, n=RX.READ_AT):
        return [{"units": {"affected": aff, "control": ctl, "flagged": []}} for _ in range(n)]
    held = [unit(None)] * 9
    assert RX.reading(results([unit(1)], [unit(5)] + held, n=RX.READ_AT - 1))[0] == "NOT YET"
    assert RX.reading(results([unit(1), unit(1.5), unit(30)], [unit(5)] + held))[0] == "FAST"
    assert RX.reading(results([unit(12), unit(15), unit(30)], [unit(5)] + held))[0] == "WINDOW"
    assert RX.reading(results([unit(4), unit(5), unit(6)], [unit(5)] + held))[0] == "A FEW MINUTES"
    assert RX.reading(results([unit(1)] + [unit(None)] * 9, [unit(1)] + held))[0] == "NO REACTION"
    assert "PRE-MOVED" in RX.reading(results([unit(None, True)] * 3 + [unit(1)], [unit(5)] + held))[0]


def test_follow_due():
    con = sqlite3.connect(":memory:")
    con.execute(W.TRIG_DDL)
    now = dt.datetime(2026, 1, 9, 22, 0, tzinfo=dt.timezone.utc)
    assert not W.follow_due(con, now)
    for mins, want in ((5, True), (19.9, True), (20.1, False)):
        con.execute("DELETE FROM triggers")
        con.execute("INSERT INTO triggers (detected_at) VALUES (?)", ((now - dt.timedelta(minutes=mins)).isoformat(),))
        assert W.follow_due(con, now) is want, mins
    con.execute("DELETE FROM triggers")
    con.execute("INSERT INTO triggers (detected_at) VALUES (?)", ("2026-01-09T21:55:00",))   # naive = UTC
    assert W.follow_due(con, now)


def test_mutants():
    src = pathlib.Path(RX.__file__).read_text()
    for name, a, b in (
            ("main rung = highest over", "if best is None or abs(odds - EVEN) < abs(best[1] - EVEN):",
             "if best is None or odds > best[1]:"),
            ("no pre-move window", "pre = main_at(tl, _add(t0, -PRE_MIN))", "pre = main_at(tl, t0)"),
            ("opponents counted", "if team_of.get(pid) not in x_teams:", "if False:"),
            ("control keeps busy games", "if g in busy or tip[g] <= t0", "if tip[g] <= t0"),
            ("gap from the wrong poll", 'out["gap_min"] = _mins(polls[i - 1], ts) if i else None',
             'out["gap_min"] = _mins(polls[i - 2], ts) if i else None'),
            ("price noise counted", "and abs(m[1] - m0[1]) >= PRICE_EPS", "and m[1] != m0[1] and False"),
            ("UTC date for the game", "if _et_date(tip[g]) == x[\"date\"]", "if tip[g][:10] == x[\"date\"]")):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_reaction_mut.py").write_text(src.replace(a, b).replace(
            "HERE = Path(__file__).resolve().parent", f"HERE = Path({str(HERE)!r})"))
        sys.path.insert(0, str(d))
        try:
            mut = importlib.import_module("nba_reaction_mut")
            print(f"MUTANT ({name}) — must fail:")
            try:
                survived = check(mut)
            except Exception as e:
                print(f"   (crashed: {type(e).__name__})")
                survived = False
            assert not survived, name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_reaction_mut", None)


if __name__ == "__main__":
    test_reaction()
    test_reading_rules()
    test_follow_due()
    test_mutants()
    print("test_nba_reaction: OK")
