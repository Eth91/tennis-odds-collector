"""NBA_SXS_PREREG.md amendment 8: a replayed decision at t reads only games final by t (tip + 3 h; without a tip, the
end of the game's ET date + 3 h) and tracking dates stored by t. A back-to-back on the side-by-side's synthetic day:
last night's game P (tip 23:30 UTC, final by 02:30) and game Q (no tip stored, final by 07:00) against overnight
openers. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_replay as RP
import nba_sxs as S
import nba_sxs_rules as SR
import test_nba_sxs as T

D, P, Q, F = T.D, "P1", "Q1", 6                          # F: an AWY player who played Q
P_TIP = "2026-10-31T23:30:00Z"                          # 7:30 pm ET on 10-31: final by 2026-11-01T02:30 UTC
EARLY = ("E1", "2026-10-25"), ("E2", "2026-10-27"), ("E3", "2026-10-29")
OPENERS = (("2026-11-01T02:00:00", T.B, "points", 12.5),   # before P is final: B's 40 FGA there must not count
           ("2026-11-01T03:00:00", T.C, "points", 12.5),   # after: C's 40 FGA in P counts
           ("2026-11-01T03:00:00", T.B, "assists", 3.5),   # after P is final; P's tracking stored by then or not
           ("2026-11-01T05:00:00", T.O, "points", 12.5),   # Q has no tip: not final until 07:00
           ("2026-11-01T07:30:00", F, "points", 12.5))


def stores(tmp, p_tracking_at="2026-11-02T11:20:00+00:00"):
    p = T.stores(tmp)
    m = sqlite3.connect(p["matchup"])
    for g, d in EARLY:                                   # 9 FGA a game for everyone before last night
        m.execute("INSERT INTO games VALUES (?, '2026-27', ?, 'HOM', 'AWY', 100, 99)", (g, d))
        m.executemany("INSERT INTO player_games (gid, team, pid, min, pts, reb, ast, fga) VALUES (?,?,?,?,?,?,?,?)",
                      [(g, tm, pid, 30, 10, 4, 2, 9) for pid, tm in ((T.B, "HOM"), (T.C, "HOM"), (T.O, "AWY"), (F, "AWY"))])
    m.execute("INSERT INTO games VALUES (?, '2026-27', '2026-10-31', 'HOM', 'OP1', 100, 99)", (P,))
    m.execute("INSERT INTO games VALUES (?, '2026-27', '2026-10-31', 'AWY', 'OP2', 100, 99)", (Q,))
    m.executemany("INSERT INTO player_games (gid, team, pid, min, pts, reb, ast, fga) VALUES (?,?,?,?,?,?,?,?)",
                  [(P, "HOM", T.B, 40, 30, 4, 2, 40), (P, "HOM", T.C, 40, 30, 4, 2, 40),
                   (Q, "AWY", T.O, 40, 30, 4, 2, 40), (Q, "AWY", F, 40, 30, 4, 2, 40)])
    m.commit()
    q = sqlite3.connect(p["lines"])
    q.execute("INSERT INTO quotes VALUES ('2026-10-31T20:00:00', 'fd', ?, ?, ?, '', 'points', 20.5, 'over', 1.9)", (P, P_TIP, T.B))
    q.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [(at, "fd", T.G, T.TIP, pid, "", st, ln, sd, 1.9) for at, pid, st, ln in OPENERS for sd in ("over", "under")])
    q.executemany("INSERT INTO cycles (ts, book, status) VALUES (?, 'fd', 'ok')", sorted({(at,) for at, *_ in OPENERS}))
    q.commit()
    p["tracking"] = tmp / "trk.sqlite"
    t = sqlite3.connect(p["tracking"])
    t.executescript("CREATE TABLE tracking (date TEXT, player_id INTEGER, potential_ast REAL, reb_chances REAL);"
                    "CREATE TABLE fetched (date TEXT, measure TEXT, rows INTEGER, fetched_at TEXT)")
    for d, pa, at in [(d, 4.0, f"{d[:8]}{int(d[8:]) + 1:02d}T11:20:00+00:00") for _g, d in EARLY] + [("2026-10-31", 30.0, p_tracking_at)]:
        t.executemany("INSERT INTO fetched VALUES (?, ?, 1, ?)", [(d, "Passing", at), (d, "Rebounding", at)])
        t.execute("INSERT INTO tracking VALUES (?, ?, ?, 0.0)", (d, T.B, pa))
    t.commit()
    return p


def setup(mod_sr, tmp, **kw):
    p = stores(tmp, **kw)
    T.isolate(mod_sr, tmp)
    mod_sr.MATCHUP_DB, mod_sr.TRACKING_DB = p["matchup"], p["tracking"]
    return p


def ratio(mod_rp, mod_sr, **kw):
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = setup(mod_sr, tmp, **kw)
    day = mod_rp.Day(D, p["lines"], p["news"], p["matchup"], mod_rp.History(p["gamelogs"], p["matchup"]))
    sig = mod_rp.run_day(day, [c() for c in mod_sr.RULES if c.name in ("RATIO_FGA", "RATIO_PA")])
    restored = (mod_sr.MATCHUP_DB, mod_sr.TRACKING_DB) == (p["matchup"], p["tracking"])
    return sorted((s["rule"], s["pid"], s["t"]) for s in sig), restored, p


def last10_at(mod_rp, p, clock):
    day = mod_rp.Day(D, p["lines"], p["news"], p["matchup"], mod_rp.History(p["gamelogs"], p["matchup"]))
    day.clock = clock
    return mod_rp.View(day).last10_min(T.B)


def check(mod_rp=RP, mod_sr=SR):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    sig, restored, p = ratio(mod_rp, mod_sr)
    want(sig == [("RATIO_FGA", T.B, "2026-11-01T15:00:30"), ("RATIO_FGA", T.C, "2026-11-01T03:00:00"),
                 ("RATIO_FGA", F, "2026-11-01T07:30:00")],
         "openers: P counts from 02:30 (C at 03:00 and B at DraftKings' 15:00:30 opener, not B at FanDuel's 02:00); Q, "
         "with no tip, from 07:00 (F at 07:30, not O at 05:00); P's tracking, stored the day after, never (no RATIO_PA)")
    want(restored, "the rules' store paths are restored after the day")
    stored, _r, _p = ratio(mod_rp, mod_sr, p_tracking_at="2026-11-01T02:45:00+00:00")
    want(("RATIO_PA", T.B, "2026-11-01T03:00:00") in stored, "P's tracking stored at 02:45 counts at 03:00")
    unstamped, _r, _p = ratio(mod_rp, mod_sr, p_tracking_at=None)
    want(not any(r == "RATIO_PA" for r, *_ in unstamped), "tracking with no stored time never counts")
    # B's last 10: seven 25-minute logs and three 30s, then P's 40 replaces the oldest log once P is final
    want(last10_at(mod_rp, p, "2026-11-01T02:00:00") == (26.5, 10) and last10_at(mod_rp, p, "2026-11-01T03:00:00") == (28.0, 10),
         "the View's history: P is not an appearance at 02:00, it is at 03:00")
    return ok


class Probe(SR.Rule):
    """Records which games its module's store holds at each FanDuel observation."""
    name = "PROBE"

    def start_day(self, v):
        self.seen = {}

    def on_obs(self, v, book, seen):
        c = sqlite3.connect(PROBE_DB)
        self.seen[v.t] = (str(PROBE_DB), {g for (g,) in c.execute("SELECT gid FROM games")})
        c.close()
        return ()


PROBE_DB = None
PIT_STORES = {"PROBE_DB": "matchup"}                   # this module's own store, swapped by the replay like SR's


def test_amendment_8():
    try:
        assert check()
    finally:
        T.isolate(SR, pathlib.Path(tempfile.mkdtemp()))


def test_store_copies():
    global PROBE_DB
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = setup(SR, tmp)
    PROBE_DB = p["matchup"]
    day = RP.Day(D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
    probe = Probe()
    try:
        RP.run_day(day, [probe])
    finally:
        T.isolate(SR, tmp)
    every = {g for (g,) in sqlite3.connect(p["matchup"]).execute("SELECT gid FROM games")}
    at = lambda t: probe.seen[t]
    assert at("2026-11-01T02:00:00")[1] == every - {P, Q} and at("2026-11-01T03:00:00")[1] == every - {Q}
    assert at("2026-11-01T07:30:00") == (str(p["matchup"]), every)          # nothing unknown: the store itself
    assert PROBE_DB == p["matchup"] and not pathlib.Path(at("2026-11-01T02:00:00")[0]).exists()   # restored, copies removed
    assert {g for (g,) in sqlite3.connect(p["matchup"]).execute("SELECT gid FROM games")} == every   # the store is untouched


def test_runner_redoes_days_run_before_amendment_8():
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = setup(SR, tmp)
    db = tmp / "sxs.sqlite"
    ran = lambda: dict(sqlite3.connect(db).execute("SELECT rule, ran_at FROM days WHERE date = ?", (D,)).fetchall())
    try:
        S.run(db=db, since=D, until="2026-11-10", stores=p)             # D is not among the last 3 days: kept once run
        con = sqlite3.connect(db)
        con.execute("UPDATE days SET ran_at = 'before', apparatus = NULL")  # as stored before amendment 8
        con.commit()
        S.run(db=db, since=D, until="2026-11-10", stores=p)
        assert ran() and "before" not in ran().values()                    # every rule redone
        con.execute("UPDATE days SET ran_at = 'after'")
        con.commit()
        S.run(db=db, since=D, until="2026-11-10", stores=p)
        assert set(ran().values()) == {"after"}                          # same apparatus and fingerprints: not redone
    finally:
        T.isolate(SR, tmp)


def test_registrations_unchanged():
    for cls in SR.RULES:
        assert SR.REGISTRY[cls.name][1] == SR.fingerprint(cls), cls.name


def test_mutants():
    rp_src = pathlib.Path(RP.__file__).read_text()
    for tag, a, b in (
            ("a game counts from its tip", "plus(iso(tip), 60 * GAME_HOURS) <= t", "iso(tip) <= t"),
            ("the stores are not as of t", "            drop = self.day.asof.unknown(kind, src, t)\n", "            drop = frozenset()\n"),
            ("the View's history is not as of t",
             "        return [a for a in self.history.before(pid, date) if self.day.asof.final(a[3], a[0], self.day.clock)]",
             "        return self.history.before(pid, date)"),
            ("an unknown tip counts", "return bool(tip) and E._et_date(tip) == date", "return not tip or E._et_date(tip) == date"),
            ("fetched_at ignored", "            elif a > t:\n", "            elif False:\n"),
            ("no stored time counts", 'iso(at) if at else "9999"', 'iso(at) if at else ""')):
        assert rp_src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_replay_amut.py").write_text(rp_src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_replay_amut"), SR), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_replay_amut", None)
            T.isolate(SR, d)
    s_src = pathlib.Path(S.__file__).read_text()
    a = ('"SELECT 1 FROM days WHERE rule = ? AND fp = ? AND date = ? AND apparatus = ?", (r.name, fps[r.name], d, APPARATUS)')
    assert s_src.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_sxs_amut.py").write_text(s_src.replace(a, '"SELECT 1 FROM days WHERE rule = ? AND fp = ? AND date = ?", (r.name, fps[r.name], d)'))
    sys.path.insert(0, str(d))
    saved = S
    try:
        globals()["S"] = importlib.import_module("nba_sxs_amut")
        try:
            test_runner_redoes_days_run_before_amendment_8()
        except AssertionError:
            pass
        else:
            raise AssertionError("MUTANT (the runner ignores the apparatus) passed")
    finally:
        globals()["S"] = saved
        sys.path.remove(str(d))
        sys.modules.pop("nba_sxs_amut", None)
