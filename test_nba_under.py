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
    import types
    rs = [{"reb": 20.0}] * 5 + [{"reb": float(r)} for r in (2, 4, 6, 8, 10)]   # his last 5 rebounds average 6
    fake = types.SimpleNamespace(his=lambda pid, date: rs)
    want(abs(mod.last5_ratio(fake, 1, TB.D, "rebounds", 9.0) - 1.5) < 1e-12, "last-5 ratio: the line over his last 5 games' average")
    want(mod.last5_ratio(types.SimpleNamespace(his=lambda pid, date: []), 1, TB.D, "rebounds", 9.0) is None and
         mod.last5_ratio(types.SimpleNamespace(his=lambda pid, date: [{"reb": 0.0}]), 1, TB.D, "rebounds", 9.0) is None,
         "no games or a zero average: no ratio")
    lo, hi = mod.L5_ZONE
    p5 = lambda l5, ratio=0.6: mod.pings_l5({"ratio": ratio, "price": 1.9}, "rebounds", l5)
    want(p5(None) and p5(lo) and not p5(lo + 1e-9) and not p5(1.2) and not p5(hi) and p5(hi + 1e-9) and p5(2.0) and not p5(2.0, 0.75),
         "pings_l5: skipped when the line is in (1.0565, 1.4167] times his last 5; no ratio: kept; outside the band: never")
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


def check_live(L, fake_model=True, l5=None):
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
    saved, real_l5 = U._MODEL.get("m"), U.last5_ratio
    U._MODEL["m"] = FAKE
    if l5 is not None:                                  # amendment 9: B's rebounds line sits l5 x his last 5
        U.last5_ratio = lambda *a: l5
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
        U.last5_ratio = real_l5
        if saved:
            U._MODEL["m"] = saved
    under = [b for b in sent if "UNDER" in b]
    notes = dict(((r[0], r[1]), r[2]) for r in sqlite3.connect(tmp / "role.sqlite").execute(
        "SELECT pid, market, note FROM idea_signals WHERE rule = 'UNDER20'"))
    if l5 is not None:                                  # in the zone: recorded with its ratio, not pinged
        assert under == [] and notes[(TB.B, "rebounds")].endswith(f" l5 {l5:.6f}"), (sent, notes)
        assert sqlite3.connect(tmp / "role.sqlite").execute(
            "SELECT pinged FROM idea_signals WHERE rule = 'UNDER20' AND pid = ? AND market = 'rebounds'", (TB.B,)).fetchall() == [(0,)]
        return
    stored = sqlite3.connect(tmp / "role.sqlite").execute(
        "SELECT line FROM idea_signals WHERE rule = 'UNDER20' AND pid = ? AND market = 'rebounds'", (TB.B,)).fetchone()[0]
    r5 = U.last5_ratio(bd, TB.B, TB.D, "rebounds", stored)
    assert r5 is not None and not (U.L5_ZONE[0] < r5 <= U.L5_ZONE[1]) and notes[(TB.B, "rebounds")].endswith(f" l5 {r5:.6f}"), (r5, notes)
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


def check_replay_l5(SR, l5):
    """UNDER3050 and UNDER3050L at the tip - 30 tick, B's rebounds at 60% of the line: both fire unless the line sits in
    amendment 9's zone over his last 5 (l5), when only UNDER3050 does."""
    import nba_boost as BOOST
    import nba_role as ROLE
    import nba_under as U
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = TB.live_stores(tmp)
    saved, real = (SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB), U.last5_ratio
    SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB = p["matchup"], p["gamelogs"]
    SR._RD.clear()
    if l5 is not None:
        U.last5_ratio = lambda *a: l5
    try:
        bd = BOOST.live_data(p["matchup"], p["gamelogs"], "2026-27")
        rd = ROLE.RoleData(p["matchup"], p["gamelogs"], "2026-27")
        line = round(U.projection(bd, rd, TB.B, "HOM", TB.D, {TB.X}, "rebounds")[1] / 0.6, 4)
        got = {}
        for cls in (SR.UNDER3050, SR.UNDER3050L):
            v = TB.FakeView({("G1", TB.B, "rebounds", "fd"): {(line, "over"): 1.9, (line, "under"): 1.9}})
            r = cls()
            r.start_day(v)
            r.on_report(v, "2026-11-01T16:00:04", [("HOM", TB.X, "Out")], {}, set())
            v.t = "2026-11-01T23:30:00"
            got[cls.name] = [(s["pid"], s["market"]) for s in r.on_tick(v, "G1", 30)]
    finally:
        SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB = saved
        U.last5_ratio = real
        SR._RD.clear()
    want = [(TB.B, "rebounds")]
    return got == {"UNDER3050": want, "UNDER3050L": [] if l5 is not None else want}


def check_early(SR):
    """Amendment 10: UNDER3050L_E60 fires at FanDuel's first observation in [tip - 60, tip - 30): not before, not on a
    DraftKings observation, once per game, never at the tip - 30 tick; UNDER3050L_E300's window ends at tip - 270."""
    import nba_boost as BOOST
    import nba_role as ROLE
    import nba_under as U
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = TB.live_stores(tmp)
    saved = SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB
    SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB = p["matchup"], p["gamelogs"]
    SR._RD.clear()
    try:
        bd = BOOST.live_data(p["matchup"], p["gamelogs"], "2026-27")
        rd = ROLE.RoleData(p["matchup"], p["gamelogs"], "2026-27")
        line = round(U.projection(bd, rd, TB.B, "HOM", TB.D, {TB.X}, "rebounds")[1] / 0.6, 4)
        v = TB.FakeView({("G1", TB.B, "rebounds", "fd"): {(line, "over"): 1.9, (line, "under"): 1.9}})

        def run(cls, steps):
            r = cls()
            r.start_day(v)
            r.on_report(v, "2026-11-01T16:00:04", [("HOM", TB.X, "Out")], {}, set())
            got = []
            for t, kind, arg in steps:
                v.t = t
                got.append([(s["pid"], s["market"]) for s in (r.on_obs(v, arg, {"G1"}) if kind == "obs" else r.on_tick(v, "G1", arg))])
            return got
        e60 = run(SR.UNDER3050L_E60, [("2026-11-01T22:59:00", "obs", "fd"), ("2026-11-01T23:00:30", "obs", "dk"),
                                      ("2026-11-01T23:01:00", "obs", "fd"), ("2026-11-01T23:05:00", "obs", "fd"),
                                      ("2026-11-01T23:30:00", "tick", 30)])
        e300 = run(SR.UNDER3050L_E300, [("2026-11-01T19:30:00", "obs", "fd")])
        e300b = run(SR.UNDER3050L_E300, [("2026-11-01T19:29:59", "obs", "fd")])
    finally:
        SR.MATCHUP_DB, SR.ROLE_GAMELOGS_DB = saved
        SR._RD.clear()
    b = [(TB.B, "rebounds")]
    return e60 == [[], [], b, [], []] and e300 == [[]] and e300b == [b]


def test_under():
    import nba_role_open as L
    import nba_sxs_rules as SR
    assert check(UNDER)
    check_live(L)
    check_live(L, l5=1.2)
    check_replay(SR)
    assert check_replay_l5(SR, None) and check_replay_l5(SR, 1.2)
    check_phone_default(L)
    assert SR.REGISTRY["UNDER3050L"][1] == SR.fingerprint(SR.UNDER3050L)
    assert check_early(SR)
    for k in (60, 120, 180, 240, 300):
        rule = getattr(SR, f"UNDER3050L_E{k}")
        assert rule.early == k and SR.REGISTRY[rule.name][1] == SR.fingerprint(rule), rule.name


def test_mutants():
    src = pathlib.Path(UNDER.__file__).read_text()
    for tag, a, b in (("the 80% cut", "if pr and pr[1] < RATIO_AT * line:", "if pr and pr[1] < line:"),
                      ("a missing input is 0", "v = med if v != v else v", "v = 0.0 if v != v else v"),
                      ("no star cut", 'return f["ratio"] < STRONG_AT', 'return f["ratio"] < RATIO_AT'),
                      ("no 50% floor on pings", "PING_FLOOR <= f[\"ratio\"] < STRONG_AT", "f[\"ratio\"] < STRONG_AT"),
                      ("pings at 20%+", "PING_FLOOR <= f[\"ratio\"] < STRONG_AT", "PING_FLOOR <= f[\"ratio\"] < RATIO_AT"),
                      ("no EV bar", 'if p * over - 1 >= EV_AT:\n        return {"side": "over"', 'if p * over - 1 >= -1:\n        return {"side": "over"'),
                      ("zone ignored", "return pings(f, market) and not (l5 is not None and L5_ZONE[0] < l5 <= L5_ZONE[1])", "return pings(f, market)"),
                      ("zone's low edge closed", "L5_ZONE[0] < l5 <= L5_ZONE[1]", "L5_ZONE[0] <= l5 <= L5_ZONE[1]"),
                      ("zone's high edge open", "L5_ZONE[0] < l5 <= L5_ZONE[1]", "L5_ZONE[0] < l5 < L5_ZONE[1]"),
                      ("no ratio skipped", "not (l5 is not None and L5_ZONE", "l5 is not None and not (L5_ZONE"),
                      ("last 10 games", "l5 = bd.his(pid, date)[-5:]", "l5 = bd.his(pid, date)[-10:]")):
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
    a = "if cur.rowcount and UNDER.pings_l5(u20, mk, l5):"
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
    a = "if cur.rowcount and UNDER.pings_l5(u20, mk, l5):"           # amendment 9: the zone ignored live
    assert lsrc.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_role_open_umut.py").write_text(lsrc.replace(a, "if cur.rowcount and UNDER.pings(u20, mk):"))
    sys.path.insert(0, str(d))
    try:
        check_live(importlib.import_module("nba_role_open_umut"), l5=1.2)
    except AssertionError:
        pass
    else:
        raise AssertionError("mutant survived: the line filter is ignored live")
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("nba_role_open_umut", None)
    import nba_sxs_rules as SR                         # UNDER3050L without the zone
    ssrc = pathlib.Path(SR.__file__).read_text()
    a = "return f if f and UNDER_M.pings_l5(f, mk, UNDER_M.last5_ratio(bd, p, date, mk, m[0])) else None"
    assert ssrc.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_sxs_rules_umut.py").write_text(ssrc.replace(a, "return f if f and UNDER_M.pings(f, mk) else None"))
    sys.path.insert(0, str(d))
    try:
        assert not check_replay_l5(importlib.import_module("nba_sxs_rules_umut"), 1.2), "mutant survived: UNDER3050L ignores the zone"
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("nba_sxs_rules_umut", None)
    for tag, a, b in (("early: any book", '        if book != "fd":\n            return ()\n        out, games = [], v.games()\n        for gid in sorted(seen):\n            g = games.get(gid)\n            if g and gid not in self.done',
                       '        out, games = [], v.games()\n        for gid in sorted(seen):\n            g = games.get(gid)\n            if g and gid not in self.done'),
                      ("early: no window end", " <= v.t < RP.minus(g[\"tip\"], self.early - 30):", " <= v.t:"),
                      ("early: every observation", "if g and gid not in self.done and", "if g and"),
                      ("early: also at the tick", "    def on_tick(self, v, gid, minutes):\n        return ()\n\n\nclass UNDER3050L_E120", "\n\nclass UNDER3050L_E120")):
        assert ssrc.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_sxs_rules_umut.py").write_text(ssrc.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            assert not check_early(importlib.import_module("nba_sxs_rules_umut")), f"mutant survived: {tag}"
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_sxs_rules_umut", None)

if __name__ == "__main__":
    test_under()
    test_mutants()
    print("test_nba_under: OK")
