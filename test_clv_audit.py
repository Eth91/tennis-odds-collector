"""CLV_AUDIT_PREREG.md guards for clv_audit.py: the NBA close is the same book's last observation within 30 min of tip,
the same rung's no-vig wins over the conversion and an under flips it; the matched null keeps only not-yet-started
games; a tie in book inference goes to FanDuel; the snapshot close ignores in-play fetches and the 30-min window; the
NFL null leaves out the bet's own rung and price CLV is bet over close; golf drops a close taken before the bet; the
tennis close needs a run within 30 min; Holm is step-down; tiers cap Level C, low coverage and no-baseline strategies;
dedupe keeps the earliest. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import math
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import clv_audit as A
import nba_injury_step2a as S
import test_nba_injury_reaction as T1

U = dt.timezone.utc


def utc(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=U)


def nba_fixture(mod):
    l, _n, _m = T1.fixture()
    con = sqlite3.connect(l)
    con.executemany("INSERT INTO quotes VALUES (?, 'fd', 'G4', '2026-10-27T21:00:00Z', 7, 'P7', 'points', 12.5, ?, 1.87)",
                    [("2026-10-27T19:14:00", "over"), ("2026-10-27T19:14:00", "under")])
    con.commit()
    con.close()
    conv = {m: S.Conv(math.log(10), 0.0) for m in S.MARKETS}
    return mod.NBA(l, conv), conv


def check_nba(mod=A):
    nba, conv = nba_fixture(mod)
    c = conv["points"]
    p145 = A.nv(1.70, 2.15)
    ok = math.isclose(nba.clv("fd", "G3", 2, "points", "over", 14.5, 1.87)[0], p145 * 1.87 - 1, rel_tol=1e-9)
    ok &= math.isclose(nba.clv("fd", "G3", 2, "points", "under", 14.5, 2.0)[0], (1 - p145) * 2.0 - 1, rel_tol=1e-9)
    ok &= math.isclose(nba.clv("fd", "G3", 2, "points", "over", 13.5, 1.87)[0], c.p_at(15.5, 0.5, 13.5) * 1.87 - 1,
                       rel_tol=1e-9)
    ok &= math.isclose(nba.clv("dk", "G3", 2, "points", "over", 14.5, 1.87)[0], c.p_at(15.5, 0.5, 14.5) * 1.87 - 1,
                       rel_tol=1e-9)
    ok &= nba.clv("fd", "G4", 7, "points", "over", 12.5, 1.87) == (None, "no close")
    return bool(ok)


def check_null(mod=A):
    nba, _ = nba_fixture(mod)
    m, n = mod.nba_null(nba, "fd", "points", "over", T1.utc("19:16:00"), "2026-10-27", {})
    want = (A.nv(1.70, 2.15) * 1.87 - 1 + 2 * (0.5 * 1.87 - 1)) / 3
    ok = n == 3 and math.isclose(m, want, rel_tol=1e-9)
    m2, n2 = mod.nba_null(nba, "fd", "points", "over", T1.utc("19:35:00"), "2026-10-27", {})
    ok &= n2 == 2 and math.isclose(m2, 0.5 * 1.87 - 1, rel_tol=1e-9)
    ok &= mod.infer_book(nba, "G3", 2, "points", 14.5, 1.87, T1.utc("19:16:00")) == "fd"
    ok &= mod.infer_book(nba, "G3", 2, "points", 14.5, 1.87, T1.utc("19:25:00")) == "dk"
    return bool(ok)


def snap_fixture():
    d = pathlib.Path(tempfile.mkdtemp())
    con = sqlite3.connect(d / "s.sqlite")
    con.execute("CREATE TABLE fd_quotes (fetched_at, event_id, event_name, commence, mins_to_kick, market_type, "
                "market_name, market_id, runner, market, player, side, line, american, price, sgm)")
    rows = []

    def add(f, ev, com, mk, pl, line, o=None, u=None):
        for side, p in (("over", o), ("under", u)):
            if p is not None:
                rows.append((f"2026-11-01T{f}+00:00", ev, com, mk, pl, side, line, p))

    E1, E2, E3 = "2026-11-01T20:00:00.000Z", "2026-11-01T21:00:00.000Z", "2026-11-01T19:30:00.000Z"
    R = "player_rush_yds"
    add("18:00:00", "E1", E1, R, "John Doe", 50.5, 1.87, 1.87)
    add("19:00:00", "E1", E1, R, "John Doe", 50.5, 1.87, 1.87)
    add("19:45:00", "E1", E1, R, "John Doe", 52.5, 1.90, 1.84)
    add("20:10:00", "E1", E1, R, "John Doe", 60.5, 1.87, 1.87)                # in play: never the close
    for f in ("18:00:00", "19:00:00", "19:45:00", "20:10:00"):
        add(f, "E1", E1, R, "Jim Roe", 30.5, 1.87, 1.87)
    for f in ("18:00:00", "19:00:00", "19:45:00", "21:10:00"):                 # last pre-kick fetch 75 min out
        add(f, "E2", E2, R, "Bo Smith", 40.5, 1.87, 1.87)
    for f in ("18:00:00", "19:20:00"):
        add(f, "E3", E3, R, "Ann Poe", 20.5, 1.80, 1.95)
    ALT = "player_reception_yds_alternate"
    for f, a, b, c in (("18:00:00", 1.20, 1.60, 1.10), ("19:45:00", 1.25, 1.70, 1.05)):
        add(f, "E1", E1, ALT, "John Doe", 9.5, a)
        add(f, "E1", E1, ALT, "John Doe", 19.5, b)
        add(f, "E1", E1, ALT, "Jim Roe", 9.5, c)
    con.executemany("INSERT INTO fd_quotes (fetched_at, event_id, commence, market, player, side, line, price) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?)", rows)
    con.commit()
    con.close()
    return d / "s.sqlite"


def snap_events(mod, snap):
    return {"2026-11-01": [(e, snap.kick(e)) for e in ("E1", "E2", "E3")]}


def check_snap(mod=A):
    snap = mod.Snap(snap_fixture(), ("player_rush_yds", "player_reception_yds_alternate"),
                    cutoff=utc("2026-11-02T00:00:00"))
    ok = snap.close_t("E1", "player_rush_yds") == utc("2026-11-01T19:45:00")
    c, why, mv = mod.snap_clv(snap, "E1", "player_rush_yds", "john doe", "over", 52.5, 1.95)
    ok &= math.isclose(c, A.nv(1.90, 1.84) * 1.95 - 1, rel_tol=1e-9) and why is None
    c, why, mv = mod.snap_clv(snap, "E1", "player_rush_yds", "john doe", "under", 50.5, 1.87)
    ok &= c is None and why == "line not at the close (no conversion)" and mv == -2.0
    ok &= mod.snap_clv(snap, "E2", "player_rush_yds", "bo smith", "over", 40.5, 1.87)[:2] == (None, "no close")
    ev = snap_events(mod, snap)
    m, n = mod.snap_null(snap, ev, "player_rush_yds", "over", utc("2026-11-01T19:10:00"), "2026-11-01", {})
    want = ((0.5 * 1.87 - 1) + (A.nv(1.80, 1.95) * 1.80 - 1)) / 2              # Jim Roe (E1) and Ann Poe (E3)
    ok &= n == 2 and math.isclose(m, want, rel_tol=1e-9)
    m, n = mod.snap_null(snap, ev, "player_rush_yds", "over", utc("2026-11-01T19:40:00"), "2026-11-01", {})
    ok &= n == 1 and math.isclose(m, 0.5 * 1.87 - 1, rel_tol=1e-9)
    return bool(ok)


def check_nfl(mod=A):
    snap = mod.Snap(snap_fixture(), ("player_reception_yds_alternate",), cutoff=utc("2026-11-02T00:00:00"))
    b = mod.bet("nfl_v2", "V2:alt_tails", utc("2026-11-01T18:30:00"), utc("2026-11-01T20:00:00"), "E1", "john doe",
                "player_reception_yds_alternate", "over", 9.5, "fd", 1.22)
    mod.score_nfl([b], snap, {})
    want_null = ((1.60 / 1.70 - 1) + (1.10 / 1.05 - 1)) / 2
    ok = math.isclose(b["clv"], 1.22 / 1.25 - 1, rel_tol=1e-9) and b["null_n"] == 2
    ok &= math.isclose(b["null"], want_null, rel_tol=1e-9) and math.isclose(b["clv2"], 1.20 / 1.25 - 1, rel_tol=1e-9)
    return bool(ok)


def check_golf(mod=A):
    def g(flag, tee, cts, cod):
        b = mod.bet("golf", "E3-birdies", utc(flag), None, "Ev", "x over 3.5", "M", "back", None, "fd", 2.0)
        b["_row"], b["_opp"] = (tee, cts, cod, None, None), None
        return b
    bs = [g("2026-08-13T10:00:00", "2026-08-13T16:40:00", "2026-08-13T16:30:00", 1.8),
          g("2026-08-13T16:35:00", "2026-08-13T16:40:00", "2026-08-13T16:30:00", 1.8),
          g("2026-08-13T16:45:00", "2026-08-13T16:40:00", "2026-08-13T16:30:00", 1.8),
          g("2026-08-13T10:00:00", "2026-08-13T16:40:00", "2026-08-13T15:30:00", 1.8)]
    mod.score_golf(bs)
    ok = math.isclose(bs[0]["clv"], 2.0 / 1.8 - 1, rel_tol=1e-9)
    ok &= bs[1]["clv"] is None and bs[1]["why"] == "close before the bet" and bs[1]["eligible"]
    ok &= not bs[2]["eligible"] and bs[2]["why"] == "flagged after the start"
    ok &= bs[3]["clv"] is None and bs[3]["why"] == "no close"
    return bool(ok)


def check_tennis(mod=A):
    s = utc("2026-10-01T12:00:00")
    rows = [(utc("2026-10-01T10:00:00"), "e1", s, "A Player", 1.80), (utc("2026-10-01T10:00:00"), "e1", s, "B Player", 2.05),
            (utc("2026-10-01T11:40:00"), "e1", s, "A Player", 1.70), (utc("2026-10-01T11:40:00"), "e1", s, "B Player", 2.20)]
    runs = [utc("2026-10-01T10:00:00") + dt.timedelta(minutes=15 * i) for i in range(8)]       # 10:00 .. 11:45
    ml = mod.ML(rows, runs)
    q, why = ml.close("e1", "A Player", "B Player")
    ok = math.isclose(q, A.nv(1.70, 2.20), rel_tol=1e-9)
    ok &= math.isclose(ml.q_at("e1", "A Player", "B Player", utc("2026-10-01T10:30:00")), A.nv(1.80, 2.05), rel_tol=1e-9)
    ok &= ml.find("B Player", "a player", s + dt.timedelta(hours=1)) == "e1"
    ok &= ml.find("A Player", "B Player", s + dt.timedelta(hours=13)) is None
    early = mod.ML(rows, runs[:5])                                                              # last run 11:00
    ok &= early.close("e1", "A Player", "B Player") == (None, "no close")
    return bool(ok)


def check_stats(mod=A):
    ok = all(math.isclose(a, b) for a, b in zip(mod.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06]))
    base = {"n": 250, "dates": 12, "clv": (0.02, 0.005, 0.04, 0.01), "excess": (0.03, 0.01, 0.05, 0.001),
            "holm_p": 0.01, "coverage": 0.8, "level": "A"}
    ok &= mod.tier(base) == "Strong"
    ok &= mod.tier(dict(base, level="C")) == "Promising"
    ok &= mod.tier(dict(base, coverage=0.6)) == "Promising"
    ok &= mod.tier(dict(base, holm_p=0.2)) == "Promising"
    nob = {k: v for k, v in base.items() if k != "excess"}
    ok &= mod.tier(nob) == "Promising"
    ok &= mod.tier(dict(nob, clv=(0.02, -0.01, 0.04, 0.1))) == "No evidence"
    ok &= mod.tier(dict(base, clv=(-0.05, -0.08, -0.01, 1.0))) == "Loses to the close"
    ok &= mod.tier(dict(base, n=40)) == "Insufficient"
    m, lo, hi, p = mod.boot([1.0, 1.0, 3.0], ["a", "a", "b"])
    ok &= math.isclose(m, 5 / 3) and 1.0 <= lo <= hi <= 3.0 and p == 1 / A.BOOT
    t0 = utc("2026-10-01T10:00:00")
    b1 = mod.bet("golf", "s", t0 + dt.timedelta(hours=1), None, "g", "p", "m", "back", None, "fd", 2.0)
    b2 = mod.bet("golf", "s", t0, None, "g", "p", "m", "back", None, "fd", 3.0)
    kept, dup = mod.dedupe([b1, b2])
    ok &= dup == 1 and kept[0]["odds"] == 3.0
    return bool(ok)


def test_guards():
    assert check_nba() and check_null() and check_snap() and check_nfl() and check_golf() and check_tennis() \
        and check_stats()


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
            ("same rung ignored", "        if rung:\n            p = R.nv(*rung)", "        if False:\n            p = R.nv(*rung)",
             check_nba),
            ("under not flipped", 'return (p if side == "over" else 1 - p), None', "return p, None", check_nba),
            ("NBA close without the window",
             "self._close[k] = obs[-1] if obs and tip and R.mins(obs[-1], tip) <= CLOSE_MAX else None",
             "self._close[k] = obs[-1] if obs and tip else None", check_nba),
            ("null keeps started games", "gids = [g for g in nba.games_by_date.get(date, ()) if nba.b.tip[g] > t]",
             "gids = list(nba.games_by_date.get(date, ()))", check_null),
            ("DraftKings on a tie", "return hit[0] if hit else None", "return hit[-1] if hit else None", check_null),
            ("in-play fetch counted", 'if d["kick"] and f < d["kick"]]', 'if d["kick"]]', check_snap),
            ("snapshot close without the window",
             "return o[-1] if o and R.mins(o[-1], self.kick(ev)) <= CLOSE_MAX else None",
             "return o[-1] if o else None", check_snap),
            ("snapshot null keeps started games", "evs = [e for e, k in events.get(date, ()) if k > t]",
             "evs = [e for e, k in events.get(date, ())]", check_snap),
            ("NFL null keeps the bet's own rung",
             'others = [v for k, v in rungs.items() if k != (b["player"], b["line"])]',
             "others = list(rungs.values())", check_nfl),
            ("price CLV inverted", "return odds / oc - 1, None", "return oc / odds - 1, None", check_nfl),
            ("golf close before the bet allowed", 'elif cts < b["t"]:', "elif False:", check_golf),
            ("tennis close without the window", "if i < 0 or R.mins(self.runs[i], start) > CLOSE_MAX:", "if i < 0:",
             check_tennis),
            ("Bonferroni, not Holm", "run = max(run, min(1.0, (len(ps) - r) * ps[i]))",
             "run = max(run, min(1.0, len(ps) * ps[i]))", check_stats),
            ("Level C can be Strong", 's["level"] in ("A", "B")', "True", check_stats),
            ("coverage cap dropped", 'and s["coverage"] >= COVER_MIN)', ")", check_stats),
            ("no-baseline judged on the mean only", 'return "Promising" if c[0] > 0 and c[1] > 0 else "No evidence"',
             'return "Promising" if c[0] > 0 else "No evidence"', check_stats),
            ("dedupe keeps the latest", 'for b in sorted(bets, key=lambda x: x["t"]):',
             'for b in sorted(bets, key=lambda x: x["t"], reverse=True):', check_stats)):
        assert not mutant(A.__file__, "clv_audit_mut", a, b, check), tag


if __name__ == "__main__":
    test_guards()
    test_mutants()
    print("ok")
