"""NBA_UNDER_PREREG.md: UNDER20 and UNDERML, live at tip - 30 and in the side-by-side (no network). MUTANTS in
test_mutants()."""
import importlib
import pathlib
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_under as UNDER
import test_nba_boost as TB

N = len(UNDER.FEATURES)
FAKE = {"features": list(UNDER.FEATURES), "median": [0.0] * N, "mean": [0.0] * N, "scale": [1.0] * N, "coef": [0.0] * N,
        "intercept": -3.0}                               # p(over) = 0.047 everywhere: every under clears 5% EV at 1.9


def check(mod):
    import nba_boost as BOOST
    import nba_role as ROLE
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")

    tmp = pathlib.Path(tempfile.mkdtemp())
    p = TB.live_stores(tmp)
    bd = BOOST.live_data(p["matchup"], p["gamelogs"], "2026-27")
    rd = ROLE.RoleData(p["matchup"], p["gamelogs"], "2026-27")
    v3, proj = mod.projection(bd, rd, TB.B, "HOM", TB.D, {TB.X}, "rebounds")
    want(abs(proj - v3 * BOOST.rates(bd, TB.B, TB.D)["reb"]) < 1e-9, "projection = V3 minutes x his rebounds per minute")
    line = proj / 0.79
    f = mod.under20(bd, rd, TB.D, "HOM", TB.B, "rebounds", line, 1.9, {TB.X})
    want(f and f["side"] == "under" and abs(f["ratio"] - 0.79) < 1e-9, "79% of the line: an UNDER20 flag")
    want(mod.under20(bd, rd, TB.D, "HOM", TB.B, "rebounds", proj / 0.81, 1.9, {TB.X}) is None, "81% of the line: none")
    want(not mod.strong(f) and mod.strong(mod.under20(bd, rd, TB.D, "HOM", TB.B, "rebounds", proj / 0.69, 1.9, {TB.X})),
         "under 70% of the line (69%), not at 79%")
    pg = lambda ratio, price=1.9, mk="rebounds": mod.pings({"ratio": ratio, "price": price}, mk)
    want(pg(0.6) and pg(0.5) and not pg(0.49) and not pg(0.7) and not pg(0.6, 1.5) and not pg(0.6, mk="threes"),
         "pings: 30-50% below (ratio 0.50-0.70), -150 or better, not threes")
    want(mod.under20(bd, rd, TB.D, "HOM", TB.B, "rebounds", line, 1.9, {TB.X, TB.B}) is None, "a player listed out is not judged")
    x = mod.features(bd, rd, TB.D, "HOM", TB.B, "rebounds", line, 0.5, {TB.X})
    want(x[0] == 0.0 and x[2] == 0.79 and x[UNDER.FEATURES.index("mk_rebounds")] == 1.0, "features: logit(q), proj/line, the market")
    m = dict(FAKE, coef=[0.0] * N)
    m["coef"][1], m["median"][1] = 1.0, 2.0              # only the line matters; a missing line takes the median (2.0)
    xs = [0.0] * N
    xs[1] = float("nan")
    want(abs(mod.predict(m, xs) - 1 / (1 + __import__("math").exp(-(-3.0 + 2.0)))) < 1e-12, "a missing input takes its median")
    g = mod.underml(bd, rd, TB.D, "HOM", TB.B, "rebounds", line, 1.9, 1.9, {TB.X}, model=FAKE)
    want(g and g["side"] == "under" and g["price"] == 1.9, "UNDERML: p(over) 0.047 -> the under")
    hi = dict(FAKE, intercept=3.0)
    want((mod.underml(bd, rd, TB.D, "HOM", TB.B, "rebounds", line, 1.9, 1.9, {TB.X}, model=hi) or {}).get("side") == "over",
         "p(over) 0.953 -> the over")
    even = dict(FAKE, intercept=0.0)
    want(mod.underml(bd, rd, TB.D, "HOM", TB.B, "rebounds", line, 1.9, 1.9, {TB.X}, model=even) is None, "p 0.5 at 1.9: under 5% EV, none")
    return ok


def check_live(L, fake_model=True):
    """At 23:00 FanDuel posts B's rebounds with his projection at 60% of the line, B's points at 60.5 (far over: under
    50%), S2's points at 5.5, B's threes at 2.5 and G4's assists at 20.5 with the under at -200. The 23:31 run (tip - 29)
    records UNDER20 for all but S2's points and pings only B's rebounds (30-50% below, -150 or better, not threes:
    amendment 4); UNDERML is recorded silently."""
    import nba_under as U
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = TB.live_stores(tmp)
    sent = []
    kw = dict(phone=L.ALL_RULES, lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=tmp / "none.sqlite", index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    saved = U._MODEL.get("m")
    U._MODEL["m"] = FAKE
    try:
        L.process(now="2026-11-01T14:00:00", **kw)
        import nba_boost as BOOST
        import nba_role as ROLE
        bd = BOOST.live_data(p["matchup"], p["gamelogs"], "2026-27")
        rd = ROLE.RoleData(p["matchup"], p["gamelogs"], "2026-27")
        reb_line = U.projection(bd, rd, TB.B, "HOM", TB.D, {TB.X}, "rebounds")[1] / 0.6
        TB.post(p, "fd", "2026-11-01T23:00:00", ((TB.B, "Bee Big", "rebounds", reb_line), (TB.S2, "Sam Guard", "points", 5.5),
                                                  (TB.B, "Bee Big", "threes", 2.5), (TB.B, "Bee Big", "points", 60.5)))
        q = sqlite3.connect(p["lines"])                  # G4's assists: under 80% of the line, but the under is -200
        q.executemany("INSERT INTO board (book, collected_at, gid, tip_utc, home, away, pid, player, stat, line, side, odds) "
                      "VALUES ('fd', '2026-11-01T23:00:00', 'G1', ?, 'HOM', 'AWY', ?, 'Gus Guard', 'assists', 20.5, ?, ?)",
                      [(TB.TIP, TB.G4, "over", 1.8), (TB.TIP, TB.G4, "under", 1.5)])
        q.commit()
        L.process(now="2026-11-01T23:31:00", **kw)
        L.process(now="2026-11-01T23:40:00", **kw)
    finally:
        U._MODEL.pop("m", None)
        if saved:
            U._MODEL["m"] = saved
    under = [b for b in sent if "UNDER" in b]
    assert len(under) == 1 and re.fullmatch(r"🔵 UNDER Bee Big REB u[\d.]+ -111 FD · proj [\d.]+ \(60% of the line\), \d+ min · shadow",
                                            under[0]), sent
    rows = sqlite3.connect(tmp / "role.sqlite").execute(
        "SELECT rule, pid, market, pinged FROM idea_signals WHERE rule LIKE 'UNDER%' ORDER BY rule, pid").fetchall()
    u20 = [(r[1], r[2], r[3]) for r in rows if r[0] == "UNDER20"]
    assert sorted(u20) == sorted([(TB.B, "rebounds", 1), (TB.B, "threes", 0), (TB.G4, "assists", 0), (TB.B, "points", 0)]), rows


def check_phone_default(L):
    """With the default routing only UNDER20 reaches the phone: B's BOOST flag (DraftKings' rebounds opener, 5 of 5) is
    recorded with pinged = 0 and sends nothing; the tip - 30 UNDER20 ping still goes out."""
    import nba_boost as BOOST
    import nba_role as ROLE
    import nba_under as U
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = TB.live_stores(tmp)
    sent = []
    kw = dict(lines_db=p["lines"], news_db=p["news"], matchup_db=p["matchup"], gamelogs_db=p["gamelogs"], tracking_db=tmp / "t.sqlite",
              lineups_db=tmp / "none.sqlite", index_json=tmp / "none.json", db=tmp / "role.sqlite", sender=lambda b: sent.append(b) or True)
    bd = BOOST.live_data(p["matchup"], p["gamelogs"], "2026-27")
    rd = ROLE.RoleData(p["matchup"], p["gamelogs"], "2026-27")
    reb_line = U.projection(bd, rd, TB.B, "HOM", TB.D, {TB.X}, "rebounds")[1] / 0.6
    L.process(now="2026-11-01T14:00:00", **kw)
    TB.post(p, "dk", "2026-11-01T16:10:00", ((TB.B, "Bee Big", "rebounds", 9.5),))
    L.process(now="2026-11-01T16:11:00", **kw)
    TB.post(p, "fd", "2026-11-01T23:00:00", ((TB.B, "Bee Big", "rebounds", reb_line),))
    L.process(now="2026-11-01T23:31:00", **kw)
    assert len(sent) == 1 and sent[0].startswith("🔵 UNDER Bee Big REB"), sent
    c = sqlite3.connect(tmp / "role.sqlite")
    assert c.execute("SELECT pinged FROM ratio_signals WHERE rule = 'BOOST' AND pid = ?", (TB.B,)).fetchall() == [(0,)]
    assert c.execute("SELECT pinged FROM idea_signals WHERE rule = 'UNDER20' AND pid = ?", (TB.B,)).fetchall() == [(1,)]


def check_replay(SR):
    """The side-by-side's UNDER20 at the tip - 30 tick: B's rebounds under; S2's points not."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = TB.live_stores(tmp)
    saved = SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB
    SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB = p["matchup"], p["gamelogs"]
    try:
        v = TB.FakeView({("G1", TB.B, "rebounds", "fd"): {(30.5, "over"): 1.9, (30.5, "under"): 1.9},
                         ("G1", TB.S2, "points", "fd"): {(5.5, "over"): 1.9, (5.5, "under"): 1.9}})
        r = SR.UNDER20()
        r.start_day(v)
        r.on_report(v, "2026-11-01T16:00:04", [("HOM", TB.X, "Out")], {}, set())
        v.t = "2026-11-01T23:30:00"
        got = r.on_tick(v, "G1", 30)
        none = r.on_tick(v, "G1", 5)
    finally:
        SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB = saved
    assert none == () and [(s["pid"], s["market"], s["side"], s["line"]) for s in got] == [(TB.B, "rebounds", "under", 30.5)], got


def test_under():
    import nba_role_open as L
    import nba_sxs_rules as SR
    assert check(UNDER)
    check_live(L)
    check_replay(SR)
    check_phone_default(L)


def test_mutants():
    src = pathlib.Path(UNDER.__file__).read_text()
    for tag, a, b in (("the 80% cut", "if pr and pr[1] < RATIO_AT * line:", "if pr and pr[1] < line:"),
                      ("a missing input is 0", "v = med if v != v else v", "v = 0.0 if v != v else v"),
                      ("no star cut", 'return f["ratio"] < STRONG_AT', 'return f["ratio"] < RATIO_AT'),
                      ("no 50% floor on pings", "PING_FLOOR <= f[\"ratio\"] < STRONG_AT", "f[\"ratio\"] < STRONG_AT"),
                      ("pings at 20%+", "PING_FLOOR <= f[\"ratio\"] < STRONG_AT", "PING_FLOOR <= f[\"ratio\"] < RATIO_AT"),
                      ("no EV bar", 'if p * over - 1 >= EV_AT:\n        return {"side": "over"', 'if p * over - 1 >= -1:\n        return {"side": "over"')):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_under_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_under_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_under_mut", None)
    # (UNDER20's dedupe is not mutated: tip30_done already runs each game once, so it cannot be told apart.)
    import nba_role_open as L
    lsrc = pathlib.Path(L.__file__).read_text()
    a = "if cur.rowcount and UNDER.pings(u20, mk):"
    assert lsrc.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_role_open_umut.py").write_text(lsrc.replace(a, "if cur.rowcount:"))
    sys.path.insert(0, str(d))
    try:
        check_live(importlib.import_module("nba_role_open_umut"))
    except AssertionError:
        pass
    else:
        raise AssertionError("mutant survived: every UNDER20 flag pings")
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("nba_role_open_umut", None)

if __name__ == "__main__":
    test_under()
    test_mutants()
    print("test_nba_under: OK")
