"""Amendment 20: the Kalshi collector reads threshold contracts right (line = floor_strike, the player's
team from the ticker, the date from the event), resolves players by full name only, stores changes
only and only before tip, de-vigs FanDuel correctly and finds volume jumps. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_pm as PM

M = {"ticker": "KXNBAPTS-26OCT24BKNCLE-CLEJALLEN31-25", "event_ticker": "KXNBAPTS-26OCT24BKNCLE",
     "title": "Jarrett Allen: 25+ points", "strike_type": "greater", "floor_strike": 24.5,
     "yes_bid_dollars": "0.3100", "yes_ask_dollars": "0.3500", "last_price_dollars": "0.3300",
     "volume_fp": "1200.00", "open_interest_fp": "900.00", "occurrence_datetime": "2026-10-24T23:30:00Z"}
INDEX = {1628386: ("CLE", "Jarrett Allen", "C"), 1: ("BKN", "Jarrett Allenn", "G"), 2: ("CLE", "Grayson Allen", "G")}
NOW = dt.datetime(2026, 10, 24, 22, 0, tzinfo=dt.timezone.utc)


def check(pm):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    p = pm.parse_market(M)
    want(p and p["line"] == 24.5 and p["stat"] == "points" and p["game_date"] == "2026-10-24"
         and (p["away"], p["home"], p["team"]) == ("BKN", "CLE", "CLE") and p["bid"] == 0.31,
         "parse: 25+ points = over 24.5, BKN @ CLE, his team CLE, 2026-10-24, bid 0.31")
    sched = [{"date_et": "2026-10-24", "away": "BKN", "home": "CLE", "utc": "2026-10-24T23:30:00Z", "gid": "G"}]
    late = dict(M, occurrence_datetime="2026-10-25T02:30:00Z")          # Kalshi's: ~tip + 3 h
    wt = pm.with_tips([dict(pm.parse_market(late), tip=late["occurrence_datetime"]), dict(p, home="NYK")], sched)
    want(len(wt) == 1 and wt[0]["tip"] == "2026-10-24T23:30:00Z" and wt[0]["gid"] == "G",
         "tip from the NBA schedule, not Kalshi's occurrence time; a game not on the schedule is dropped")
    p = wt[0]
    want(pm.parse_market(dict(M, strike_type="less")) is None and pm.parse_market(dict(M, ticker="KXNBAGAME-X")) is None,
         "only player threshold contracts are read")
    want(pm.resolve(p, INDEX) == 1628386, "resolve: exact full name within his team (not Grayson Allen)")
    solo = {1628386: ("CLE", "Jarrett Allen", "C"), 7: ("GSW", "Jimmy Butler III", "F")}
    want(pm.resolve(dict(p, player="Allen"), solo) is None, "a surname alone never resolves, even when unique")
    want(pm.resolve(dict(p, player="Jimmy Butler", team="GSW", away="GSW", home="PHX"), solo) == 7,
         "a suffix is ignored: Jimmy Butler == Jimmy Butler III")
    con = pm._db(pathlib.Path(tempfile.mkdtemp()) / "pm.sqlite")
    last = {}
    a = pm.store(con, [dict(p, pid=1628386)], NOW, last)
    b = pm.store(con, [dict(p, pid=1628386)], NOW + dt.timedelta(minutes=1), last)
    c = pm.store(con, [dict(p, pid=1628386, volume=3400.0)], NOW + dt.timedelta(minutes=2), last)
    d = pm.store(con, [dict(p, pid=1628386, volume=9999.0)], dt.datetime(2026, 10, 24, 23, 31, tzinfo=dt.timezone.utc), last)
    want((a, b, c, d) == (1, 0, 1, 0), f"store: changes only, never at/after tip ({(a, b, c, d)})")
    q = sqlite3.connect(":memory:")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT,"
              " stat TEXT, line REAL, side TEXT, odds REAL)")
    for side, o in (("over", 1.80), ("under", 2.00)):
        q.execute("INSERT INTO quotes VALUES ('2026-10-24T21:59:00','fd','G','',1628386,'','points',24.5,?,?)", (side, o))
    q.execute("INSERT INTO quotes VALUES ('2026-10-24T21:59:00','fd','G','',1628386,'','points',29.5,'over',4.0)")
    f1 = pm.fd_fair(q, "G", 1628386, "points", 24.5, "2026-10-24T22:00:00")
    f2 = pm.fd_fair(q, "G", 1628386, "points", 29.5, "2026-10-24T22:00:00")
    want(f1 and abs(f1[0] - (1 / 1.8) / (1 / 1.8 + 1 / 2.0)) < 1e-9 and f1[1] == "DEVIG",
         f"FD fair: de-vigged when both sides exist ({f1[0]:.4f} = 0.5263)" if f1 else "FD fair missing")
    want(f2 == (0.25, "RAW"), "FD fair: raw 1/odds for an over-only ladder rung")
    path = pathlib.Path(tempfile.mkdtemp()) / "pm.sqlite"
    con = pm._db(path)
    for i, (vol, bid, ask) in enumerate(((1000, .30, .34), (1100, .30, .34), (4100, .38, .42), (4150, .38, .42))):
        con.execute("INSERT INTO pm_quotes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"2026-10-24T21:5{i}:00", "kalshi", M["ticker"], "", "2026-10-24", "CLE", 1628386, "Jarrett Allen",
                     "points", 24.5, bid, ask, 0, vol, 0, "2026-10-24T23:30:00", "G"))
    con.commit()
    mo = pm.money(30, path=path, now=NOW)
    want(mo and mo[0]["dvol"] == 3000 and abs(mo[0]["dk"] - 0.08) < 1e-9,
         "money: the biggest jump is +3,000 contracts with the fair up 0.08")
    return ok


def test_pm():
    assert check(PM)


def test_mutants():
    src = pathlib.Path(PM.__file__).read_text()
    for tag, a, b in (
            ("line from the title (25) not floor_strike", '"line": float(m["floor_strike"])', '"line": float(m["floor_strike"]) + 0.5'),
            ("store every poll", "        if last.get(p[\"ticker\"]) == key:\n            continue\n", ""),
            ("store after tip", "if not tip or tip <= now or", "if not tip or"),
            ("tip from Kalshi", "out.append(dict(p, tip=t, gid=gid))", "out.append(dict(p, tip=p[\"tip\"] or t, gid=gid))"),
            ("no de-vig", "        return (1 / o) / ((1 / o) + (1 / u)), \"DEVIG\"", "        return 1 / o, \"DEVIG\""),
            ("surname match", "if t in teams and key(n) == want and \" \" in want]", "if t in teams and want in key(n)]")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_pm_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_pm_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_pm_mut", None)


if __name__ == "__main__":
    test_pm(); test_mutants()
    print("test_nba_pm: OK")
