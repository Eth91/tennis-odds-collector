"""nfl_lines: FanDuel / DraftKings NFL market parsing, event matching, identity scoped to the game's two rosters, the
board / change log / game lines cycle, and the DraftKings receiver's NFL dispatch. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import json
import pathlib
import sqlite3
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nba_dk_receive as K
import nfl_lines as L

NOW = dt.datetime(2026, 10, 29, 12, 0, tzinfo=dt.timezone.utc)


def fdm(name, runners, mtype="X"):
    return {"marketName": name, "marketType": mtype,
            "runners": [{"runnerName": n, "handicap": h, "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": a}}}
                        for n, h, a in runners]}


def sched():
    g = lambda gid, a, h, utc: {"gid": gid, "season": 2026, "week": 8, "away": a, "home": h, "utc": utc,
                                "home_score": None, "away_score": None, "date": utc[:10]}
    return [g("2026_08_CAR_GB", "CAR", "GB", "2026-10-30T00:15:00"),
            g("2026_08_BAL_BUF", "BAL", "BUF", "2026-11-01T17:00:00"),
            g("2026_08_LAC_LA", "LAC", "LAR", "2026-11-01T21:05:00"),
            dict(g("2026_07_CAR_GB", "CAR", "GB", "2026-10-20T00:15:00"), home_score=20.0, away_score=17.0)]


def roster():
    r = lambda name, team, pos="WR", fb="": {"name": name, "team": team, "pos": pos, "football_name": fb}
    return {1: r("Jordan Love", "GB", "QB"), 2: r("Josh Jacobs", "GB", "RB"), 3: r("Tetairoa McMillan", "CAR"),
            4: r("Josh Allen", "BUF", "QB"), 5: r("Josh Allen", "JAX", "LB"),        # same name, another team
            6: r("Chris Smith", "CAR"), 7: r("Chris Smith", "GB"),                    # ambiguous inside the game
            8: r("Andrew Ogletree", "BUF", "TE"), 9: r("DJ Moore", "BUF")}


# ── FanDuel ─────────────────────────────────────────────────────────────────────────────────────────────
def check_fd(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    x = mod.fd_extract
    want(x(fdm("Jordan Love - Passing Yds", [("Jordan Love Over", 260.5, -113), ("Jordan Love Under", 260.5, -113)]))
         == [("Jordan Love", "pass_yds", 260.5, "over", 1.885), ("Jordan Love", "pass_yds", 260.5, "under", 1.885)],
         "two-sided O/U at the posted line")
    want(x(fdm("Josh Jacobs - Alt Rushing Yds", [("Josh Jacobs 25+ Yards", 0, -1800), ("Josh Jacobs 40+ Yards", 0, -360)]))
         == [("Josh Jacobs", "rush_yds", 24.5, "over", round(1 + 100 / 1800, 4)), ("Josh Jacobs", "rush_yds", 39.5, "over", round(1 + 100 / 360, 4))],
         "an alt ladder: N+ is an over at N - 0.5")
    want([r[1:4] for r in x(fdm("Jordan Love - Alt Passing TDs", [("Jordan Love 2+ Passing Touchdowns", 0, -154)]))]
         == [("pass_tds", 1.5, "over")], "alt passing TDs")
    want([r[1:4] for r in x(fdm("Tetairoa McMillan - Alt Receptions", [("Tetairoa McMillan 3+ Receptions", 0, -1600)]))]
         == [("rec", 2.5, "over")], "alt receptions")
    want([r[1:3] for r in x(fdm("Chuba Hubbard - Rushing + Receiving Yds", [("Chuba Hubbard Over", 84.5, -113)]))]
         == [("rush_rec_yds", 84.5)], "rushing + receiving is its own market, not rushing yards")
    want([r[1] for r in x(fdm("Savion Williams - Total Receptions", [("Savion Williams Over", 2.5, -110)]))] == ["rec"],
         "total receptions")
    want([r[:4] for r in x(fdm("Any Time Touchdown Scorer", [("Josh Jacobs", 0, -150), ("Chuba Hubbard", 0, -115)]))]
         == [("Josh Jacobs", "anytime_td", 0.5, "over"), ("Chuba Hubbard", "anytime_td", 0.5, "over")], "anytime TD = over 0.5")
    want([r[2] for r in x(fdm("To Score 2+ Touchdowns", [("Josh Jacobs", 0, 420)]))] == [1.5], "2+ TDs = over 1.5")
    want([r[2] for r in x(fdm("To Score 3+ Touchdowns", [("Josh Jacobs", 0, 2200)]))] == [2.5], "3+ TDs = over 2.5")
    want([r[1:4] for r in x(fdm("Player To Record a 20+ Yard Reception", [("Christian Watson", 0, -350)]))]
         == [("long_rec", 19.5, "over")], "a 20+ yard reception = longest reception over 19.5")
    want([r[1:4] for r in x(fdm("Player To Record A Sack", [("Lukas Van Ness", 0, -102)]))] == [("sacks", 0.5, "over")],
         "to record a sack = sacks over 0.5")
    for nm, rn in (("Christian Watson - 1st Qtr Receiving Yds", "Christian Watson Over"),
                   ("Jordan Love - 2nd Half Passing Yds", "Jordan Love Over"),
                   ("Josh Jacobs Drive 1 Rushing Yds GB Packers", "Josh Jacobs 5+ Rushing Yards"),
                   ("Either Player - Anytime Touchdown Scorer", "Josh Jacobs or Chuba Hubbard"),
                   ("Anytime 1st Half TD Scorer", "Josh Jacobs"), ("Last Touchdown Scorer", "Josh Jacobs"),
                   ("Most Receiving Yards", "Tetairoa McMillan"), ("Game Specials - Rushing", "Chuba Hubbard to record 5+"),
                   ("Defensive Player Any Time Touchdown Scorer", "Xavier McKinney"),
                   ("GB Packers Total Points", "Over")):
        want(x(fdm(nm, [(rn, 12.5, -110)])) == [], f"not a full-game prop: {nm}")
    return ok


def test_fd():
    assert check_fd(L)


def test_fd_game_lines():
    page = {"attachments": {"events": {"1": {"name": "Carolina Panthers @ Green Bay Packers"}}, "markets": {
        "a": dict(fdm("Spread", [("Carolina Panthers", 3.5, -106), ("Green Bay Packers", -3.5, -114)]),
                  marketType="MATCH_HANDICAP_(2-WAY)", eventId=1, marketStatus="OPEN"),
        "b": dict(fdm("Total Points", [("Over", 47.5, -102), ("Under", 47.5, -120)]),
                  marketType="TOTAL_POINTS_(OVER/UNDER)", eventId=1, marketStatus="OPEN"),
        "c": dict(fdm("1st Half Spread", [("Carolina Panthers", 2.5, 100)]), marketType="FIRST_HALF_HANDICAP",
                  eventId=1, marketStatus="OPEN")}}}
    con = sqlite3.connect(":memory:")
    con.executescript(L.DDL)
    up = [g for g in sched() if g["home_score"] is None]
    assert L.store_game_lines(con, page, up, "t1") == 4
    got = {(m, s): ln for m, s, ln in con.execute("SELECT market, side, line FROM game_lines")}
    assert got == {("spread", "away"): 3.5, ("spread", "home"): -3.5, ("total", "over"): 47.5, ("total", "under"): 47.5}
    assert L.store_game_lines(con, page, up, "t2") == 0, "unchanged lines are not written again"


# ── DraftKings ──────────────────────────────────────────────────────────────────────────────────────────
def dksel(mid, label, dec, player, points=None):
    return {"marketId": mid, "label": label, "points": points, "displayOdds": {"decimal": str(dec)},
            "participants": [{"type": "Player", "name": player}]}


def check_dk(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    ev = {10: "CAR Panthers @ GB Packers"}
    ou = {"_name": "pass yards o/u", "markets": [{"id": "m1", "eventId": 10, "name": "Jordan Love Passing Yards O/U"},
                                               {"id": "m2", "eventId": 99, "name": "Started QB Passing Yards O/U"}],
          "selections": [dksel("m1", "Over", 1.88, "Jordan Love", 256.5), dksel("m1", "Under", 1.9, "Jordan Love", 256.5),
                         dksel("m2", "Over", 1.9, "Started QB", 200.5)]}
    want(mod.dk_rows(ou, ev) == [(ev[10], "Jordan Love", "pass_yds", 256.5, "over", 1.88),
                                 (ev[10], "Jordan Love", "pass_yds", 256.5, "under", 1.9)],
         "O/U rungs; a started game's market is skipped")
    ms = {"_name": "pass yards", "markets": [{"id": "m1", "eventId": 10, "name": "Jordan Love Passing Yards"}],
          "selections": [dksel("m1", "150+", 1.17, "Jordan Love"), dksel("m1", "300+", 3.4, "Jordan Love")]}
    want([r[3:5] for r in mod.dk_rows(ms, ev)] == [(149.5, "over"), (299.5, "over")], "a milestone N+ is an over at N - 0.5")
    td = {"_name": "td scorer", "markets": [{"id": "a", "eventId": 10, "name": "Anytime TD Scorer"},
                                          {"id": "f", "eventId": 10, "name": "First TD Scorer"},
                                          {"id": "t", "eventId": 10, "name": "2+ TDs"}],
          "selections": [dksel("a", "Josh Jacobs", 1.66, "Josh Jacobs"), dksel("f", "Josh Jacobs", 5.5, "Josh Jacobs"),
                         dksel("t", "Josh Jacobs", 4.7, "Josh Jacobs")]}
    want(sorted(r[2:5] for r in mod.dk_rows(td, ev)) == [("anytime_td", 0.5, "over"), ("anytime_td", 1.5, "over")],
         "anytime TD 0.5, 2+ TDs 1.5, first TD scorer left out")
    want(mod.dk_stat("Pass Yards - 1Q O/U") is None and mod.dk_stat("Rec Yards - 1H") is None, "period subcategories map to nothing")
    want(mod.dk_stat("Rush + Rec Yards O/U") == "rush_rec_yds" and mod.dk_stat("Longest Reception") == "long_rec",
         "combo and longest subcategories")
    return ok


def test_dk():
    assert check_dk(L)


# ── matching, identity, the cycle ───────────────────────────────────────────────────────────────────────
def test_match_event():
    up = [g for g in sched() if g["home_score"] is None]
    assert L.match_event("Carolina Panthers @ Green Bay Packers", up)["gid"] == "2026_08_CAR_GB"
    assert L.match_event("CAR Panthers @ GB Packers", up)["gid"] == "2026_08_CAR_GB"
    assert L.match_event("Los Angeles Chargers @ Los Angeles Rams", up)["gid"] == "2026_08_LAC_LA"
    assert L.match_event("Green Bay Packers @ Carolina Panthers", up) is None, "home and away are not interchangeable"
    assert L.match_event("Packers vs Panthers", up) is None


def run_cycle(db, fd_rows, dk=None, now=NOW, sched_=None):
    fetch = {"fd": lambda: (fd_rows, ""), "dk": dk or (lambda: ([], ""))}
    return L.cycle(("fd", "dk") if dk else ("fd",), now=now, sched=sched_ or sched(), roster=roster(), fetchers=fetch, db=db)


def test_cycle():
    db = pathlib.Path(tempfile.mkdtemp()) / "l.sqlite"
    E, B = "Carolina Panthers @ Green Bay Packers", "Baltimore Ravens @ Buffalo Bills"
    rows = [(E, "Jordan Love", "pass_yds", 260.5, "over", 1.885), (E, "Jordan Love", "pass_yds", 260.5, "under", 1.885),
            (E, "Josh Jacobs", "rush_yds", 58.5, "over", 1.88), (E, "Josh Jacobs", "rush_yds", 58.5, "over", 1.90),
            (E, "Chris Smith", "rec", 2.5, "over", 2.0),            # ambiguous inside CAR @ GB: never guessed
            (E, "Green Bay Defense", "anytime_td", 0.5, "over", 9.0),  # a team, not a player
            (B, "Josh Allen", "pass_yds", 247.5, "over", 1.885),    # Josh Allen (JAX) is not in this game
            (B, "Drew Ogletree", "rec", 1.5, "over", 1.8), (B, "D.J. Moore", "rec_yds", 40.5, "under", 1.9),
            ("Chicago Bears @ Seattle Seahawks", "X", "rec", 1.5, "over", 1.9),   # no such game: unmatched
            (E, "Jordan Love", "points", 20.5, "over", 1.9)]       # not an NFL stat key
    assert run_cycle(db, rows) == []
    con = sqlite3.connect(db)
    b = {(r[0], r[1], r[2], r[3]): r[4:] for r in con.execute("SELECT player, stat, line, side, pid, gid, odds FROM board")}
    assert b[("Jordan Love", "pass_yds", 260.5, "over")][:2] == (1, "2026_08_CAR_GB")
    assert b[("Josh Jacobs", "rush_yds", 58.5, "over")][2] == 1.90, "one price per rung: the better one"
    assert b[("Chris Smith", "rec", 2.5, "over")][0] is None, "an ambiguous name stays unresolved"
    assert b[("Josh Allen", "pass_yds", 247.5, "over")][0] == 4, "resolved within the game's two teams only"
    assert b[("Drew Ogletree", "rec", 1.5, "over")][0] == 8, "a short first name resolves to the roster's long form"
    assert b[("D.J. Moore", "rec_yds", 40.5, "under")][0] == 9
    assert not any(k[0] == "Green Bay Defense" for k in b) and not any(k[1] == "points" for k in b)
    assert len(b) == 7
    cyc = con.execute("SELECT status, rows, events, matched_events, unresolved FROM cycles").fetchone()
    assert cyc == ("ok", 7, 3, 2, 1), cyc
    assert con.execute("SELECT COUNT(*) FROM quotes").fetchone()[0] == 7
    # second cycle: one price moves, one rung is pulled -> 1 change + 1 NULL row; the rest are not logged again
    rows2 = [r for r in rows if r[1] != "D.J. Moore"]
    rows2 = [(r[0], r[1], r[2], r[3], r[4], 1.95) if r[1] == "Jordan Love" and r[4] == "over" else r for r in rows2]
    assert run_cycle(db, rows2, now=NOW + dt.timedelta(minutes=5)) == []
    q = con.execute("SELECT player, odds FROM quotes WHERE seen_at > ? ORDER BY player",
                    ((NOW + dt.timedelta(minutes=1)).replace(tzinfo=None).isoformat(),)).fetchall()
    assert q == [("D.J. Moore", None), ("Jordan Love", 1.95)], q
    # a failed fetch leaves the board as it was and is returned as failed
    n0 = con.execute("SELECT COUNT(*) FROM board").fetchone()[0]
    assert L.cycle(("fd",), now=NOW + dt.timedelta(minutes=10), sched=sched(), roster=roster(),
                   fetchers={"fd": lambda: (_ for _ in ()).throw(RuntimeError("down"))}, db=db) == ["fd"]
    assert con.execute("SELECT COUNT(*) FROM board").fetchone()[0] == n0
    # after kickoff the game's props no longer match: nothing is written for a game under way
    late = NOW.replace(day=30, hour=1)
    run_cycle(db, rows2, now=late)
    assert not con.execute("SELECT COUNT(*) FROM board WHERE gid='2026_08_CAR_GB'").fetchone()[0]


def test_snapshot_stale_and_dk():
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / "nfl_dk_snapshot.json"
    at = (NOW - dt.timedelta(minutes=20)).replace(tzinfo=None, microsecond=0).isoformat()
    p.write_text(json.dumps({"book": "dk", "league": "nfl", "fetched_at": at, "rows": [], "detail": ""}))
    try:
        L.fetch_dk_snapshot(p, now=NOW.replace(tzinfo=None))
        assert False, "a 20-minute-old snapshot must be stale"
    except L.Stale:
        pass
    p.write_text(json.dumps({"book": "dk", "fetched_at": at, "rows": [], "detail": ""}))
    try:
        L.fetch_dk_snapshot(p, now=NOW.replace(tzinfo=None) - dt.timedelta(minutes=19))
        assert False, "an NBA snapshot is never read as NFL"
    except L.Stale:
        pass
    at = (NOW - dt.timedelta(minutes=2)).replace(tzinfo=None, microsecond=0).isoformat()
    row = ["CAR Panthers @ GB Packers", "Jordan Love", "pass_yds", 256.5, "over", 1.88]
    p.write_text(json.dumps({"book": "dk", "league": "nfl", "fetched_at": at, "rows": [row], "detail": ""}))
    db = d / "l.sqlite"
    run_cycle(db, [], dk=lambda: L.fetch_dk_snapshot(p, now=NOW.replace(tzinfo=None)))
    con = sqlite3.connect(db)
    assert con.execute("SELECT collected_at, pid FROM board WHERE book='dk'").fetchall() == [(at, 1)], \
        "the snapshot's own fetch time dates the board"


# ── the receiver's NFL dispatch ─────────────────────────────────────────────────────────────────────────
RNOW = dt.datetime(2026, 10, 29, 12, 0, 0)


def rsnap(league=None, at=RNOW - dt.timedelta(seconds=30)):
    s = {"book": "dk", "fetched_at": at.isoformat(), "detail": "",
         "rows": [["CAR Panthers @ GB Packers", "Jordan Love", "pass_yds", 256.5, "over", 1.88]]}
    if league is not None:
        s["league"] = league
    return json.dumps(s).encode()


def check_recv(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    d = pathlib.Path(tempfile.mkdtemp())
    nba, nfl = d / "dk_snapshot.json", d / "nfl_dk_snapshot.json"
    code, msg = mod.receive(rsnap("nfl"), RNOW, nba, nfl)
    want(code == 0 and nfl.exists() and not nba.exists() and json.loads(nfl.read_text())["league"] == "nfl",
         "an NFL snapshot goes to its own file, never the NBA one")
    code, msg = mod.receive(rsnap(), RNOW, nba, nfl)
    want(code == 0 and nba.exists() and "league" not in json.loads(nba.read_text()),
         "an NBA snapshot (no league) is written as before, with no league key")
    code, _ = mod.receive(rsnap("nfl", RNOW - dt.timedelta(seconds=60)), RNOW, nba, nfl)
    want(json.loads(nfl.read_text())["fetched_at"] == (RNOW - dt.timedelta(seconds=30)).isoformat(),
         "an older NFL snapshot never replaces a newer one")
    before = (nba.read_text(), nfl.read_text())
    code, msg = mod.receive(rsnap("mlb"), RNOW, nba, nfl)
    want(code == 2 and (nba.read_text(), nfl.read_text()) == before, "an unknown league is refused")
    return ok


def test_receiver_nfl():
    assert check_recv(K)


def _mutant(src_path, modname, a, b):
    src = pathlib.Path(src_path).read_text()
    assert src.count(a) == 1, a
    d = pathlib.Path(tempfile.mkdtemp())
    (d / f"{modname}.py").write_text(src.replace(a, b))
    sys.path.insert(0, str(d))
    try:
        return importlib.import_module(modname)
    finally:
        sys.path.remove(str(d))


def test_mutants():
    cases = (
        (L.__file__, "nfl_lines_m1", "if NOT_FULL_GAME.search(low) or", "if", check_fd, "period rejection"),
        (L.__file__, "nfl_lines_m2", 'rows.append((player, stat, int(mm.group(1)) - 0.5, "over", o))',
         'rows.append((player, stat, float(mm.group(1)), "over", o))', check_fd, "FanDuel N+ -> N - 0.5"),
        (L.__file__, "nfl_lines_m3", 'side, pts = "over", float(raw[:-1]) - 0.5', 'side, pts = "over", float(raw[:-1])',
         check_dk, "DraftKings N+ -> N - 0.5"),
        (L.__file__, "nfl_lines_m4", 'if eid not in events:', 'if False:', check_dk, "DraftKings started-game filter"),
        (K.__file__, "nba_dk_receive_m1", 'out, tag = out_nfl, "nfl "', 'out, tag = out, "nfl "', check_recv, "receiver dispatch"),
        (K.__file__, "nba_dk_receive_m2", 'if snap.get("league") not in LEAGUES:', 'if False:', check_recv, "league check"),
    )
    for path, name, a, b, check, label in cases:
        mut = _mutant(path, name, a, b)
        print(f"MUTANT ({label}) — must fail:")
        try:
            survived = check(mut)
        except Exception as e:                       # a crash is a caught mutant too
            print(f"   (crashed: {type(e).__name__})")
            survived = False
        assert not survived, f"mutant survived: {label}"
