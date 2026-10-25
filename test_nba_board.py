"""nba_board: one row per opportunity (earliest flag, tiers merged across stat spellings), voided
flags hidden, retractions moved to the OFF strip (never dropped), FanDuel now vs at tip, the
SHADOW label always present. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_board as B
import nba_flags as F

NOW = dt.datetime(2026, 1, 9, 22, 0, tzinfo=dt.timezone.utc)          # 5 PM ET, Jan 9
TIP_LATE, TIP_EARLY = "2026-01-10T03:00:00Z", "2026-01-09T21:00:00Z"   # one upcoming, one started


def build(mod):
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")

    def flag(fid, at, tier, b, pid, stat, line, odds, gtime, x="X1", x_pid=101, void=None, gid="G1",
             matchup="AAA @ BBB", result=None, actual=None):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, "
                   "gtime, matchup, pid, x_pid, void_reason, result, actual, horizon) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                   (fid, at, "2026-01-09", tier, "BBB", x, b, stat, line, odds, gid, gtime, matchup, pid,
                    x_pid, void, result, actual))
    flag("a1", "2026-01-09T18:00:00", "wowy", "Ann", 1, "pts", 10.5, 1.91, TIP_LATE)
    flag("a2", "2026-01-09T19:00:00", "priced", "Ann", 1, "points", 11.5, 1.95, TIP_LATE)   # same opp, later
    flag("b1", "2026-01-09T18:00:00", "wowy", "Bob", 2, "reb", 5.5, 1.80, TIP_LATE)        # Bob ruled OUT
    flag("c1", "2026-01-09T18:00:00", "wowy", "Cal", 3, "pts", 7.5, 1.85, TIP_LATE, x="X2", x_pid=102)  # X2 back
    flag("d1", "2026-01-09T18:00:00", "wowy", "Dee", 4, "pts", 9.5, 1.85, TIP_LATE, void="amend3: test")
    flag("e1", "2026-01-09T18:00:00", "wowy", "Eve", 5, "pra", 20.5, 2.10, TIP_LATE)       # Eve questionable
    flag("f1", "2026-01-09T15:00:00", "wowy", "Fay", 6, "pts", 12.5, 1.90, TIP_EARLY, gid="G2",
         matchup="CCC @ DDD")                                                               # started: FD at tip
    sh.commit()
    n = sqlite3.connect(d / "n.sqlite")
    n.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT,"
              " pid INTEGER, player TEXT, status TEXT, reason TEXT)")
    for mark, pid, stt in (("2026-01-09T16:00", 2, "Probable"),      # an OLDER report: Bob probable
                           ("2026-01-09T16:30", 2, "Out"), ("2026-01-09T16:30", 102, "Available"),
                           ("2026-01-09T16:30", 5, "Questionable"), ("2026-01-09T16:30", 101, "Out")):
        n.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                  (mark, mark, "2026-01-09", "", "", pid, "", stt, ""))
    n.commit()
    q = sqlite3.connect(d / "q.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT,"
              " stat TEXT, line REAL, side TEXT, odds REAL)")
    for t, bk, gid, pid, stat, ln, o in (("2026-01-09T18:00:00", "fd", "G1", 1, "points", 10.5, 1.91),
                                          ("2026-01-09T21:30:00", "fd", "G1", 1, "points", 10.5, None),   # pulled
                                          ("2026-01-09T21:30:00", "fd", "G1", 1, "points", 11.5, 1.87),
                                          ("2026-01-09T21:30:00", "dk", "G1", 1, "points", 12.5, 1.90),
                                          ("2026-01-09T15:00:00", "fd", "G2", 6, "points", 12.5, 1.90),
                                          ("2026-01-09T20:50:00", "fd", "G2", 6, "points", 12.5, None),   # pulled
                                          ("2026-01-09T20:50:00", "fd", "G2", 6, "points", 13.5, 1.85),
                                          ("2026-01-09T21:40:00", "fd", "G2", 6, "points", 15.5, 1.85)):   # post-tip
        for side, oo in (("over", o), ("under", 1.91 if o else None)):
            q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", (t, bk, gid, "", pid, "", stat, ln, side, oo))
    q.commit()
    mod.SHADOW, mod.NEWS, mod.LINES = d / "s.sqlite", d / "n.sqlite", d / "q.sqlite"
    return mod.board(NOW)


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    b = build(mod)
    rows = {r["b"]: r for s in b["slates"] for g in s["games"] for r in g["rows"]}
    off = {r["b"]: r for r in b["retracted"]}
    want(b["slates"] and b["slates"][0]["label"] == "TONIGHT", "tonight's slate first")
    a = rows.get("Ann")
    want(a and a["line"] == 10.5 and a["tiers"] == ["priced", "wowy"],
         "one row per opportunity: the EARLIEST flag, tiers merged across pts/points")
    want(a and a["fd"] == {"line": 11.5, "odds": 1.87}, "FD NOW = FanDuel's current main line (not DraftKings')")
    want("Bob" in off and "Bob" not in rows and off["Bob"]["why"] == "Bob OUT",
         "player ruled Out on the NEWEST report -> OFF strip, not dropped")
    want("Cal" in off and off["Cal"]["why"] == "X2 AVAILABLE", "absent star back (Available) -> OFF strip")
    want("Dee" not in rows and "Dee" not in off, "a voided flag is not shown")
    want(rows.get("Eve", {}).get("b_status") == "Questionable", "a questionable player stays, marked")
    f = rows.get("Fay")
    want(f and f["state"] == "live" and f["fd"] == {"line": 13.5, "odds": 1.85},
         "started game: FD at TIP, a post-tip quote ignored")
    h = mod.html(b)
    want("SHADOW · NOT BETS" in h and "OFF" in h and "Bob" in h, "html: shadow label, OFF strip rendered")
    want(sum(1 for s in b["slates"] for g in s["games"] for _ in g["rows"]) == 3, "exactly 3 live rows")
    return ok


def test_board():
    assert check(B)


def check_veto(mod):
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    for fid, b, pid in (("v", "VJ Edgecombe", 7), ("k", "Kelly Oubre Jr.", 8)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, gtime, "
                   "matchup, pid, x_pid, horizon) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                   (fid, "2026-01-09T18:00:00", "2026-01-09", "wowy", "PHI", "Joel Embiid", b, "pts", 12.5, 1.83,
                    "G1", TIP_LATE, "MIL @ PHI", pid, 203954))
    sh.commit()
    n = sqlite3.connect(d / "n.sqlite")
    n.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT,"
              " pid INTEGER, player TEXT, status TEXT, reason TEXT)")
    n.commit()
    sqlite3.connect(d / "q.sqlite").execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, "
                                            "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    mod.SHADOW, mod.NEWS, mod.LINES = d / "s.sqlite", d / "n.sqlite", d / "q.sqlite"
    assert mod.veto("2026-01-09", 7, "Embiid not out (a choice, not a ruling)") == "VJ Edgecombe"
    b = mod.board(NOW)
    shown = [r["b"] for s in b["slates"] for g in s["games"] for r in g["rows"]]
    off = {r["b"]: r["why"] for r in b["retracted"]}
    return shown == ["Kelly Oubre Jr."] and "VETOED" in off.get("VJ Edgecombe", "")


def test_veto_moves_play_to_off_strip():
    assert check_veto(B)


def test_pinged_off_card_strip():
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    for fid, b, pid, stat, card in (("a", "Gui Santos", 1, "pts", 1), ("b", "Gui Santos", 1, "pra", 0),
                                    ("c", "Dillon Brooks", 2, "pts", 0), ("d", "Not Pinged", 3, "reb", 0)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, gtime, "
                   "matchup, pid, x_pid, horizon, card) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                   (fid, "2026-01-09T18:00:00", "2026-01-09", "wowy", "GSW", "X", b, stat, 20.5, 1.87, "G1",
                    TIP_LATE, "GSW @ PHX", pid, 9, card))
    import nba_ping as P
    sh.execute(P.PINGS_DDL)
    for k in ("play|2026-01-09|1|points", "play|2026-01-09|1|pra", "play|2026-01-09|2|points"):
        sh.execute("INSERT INTO pings (key, kind, sent_at, ok) VALUES (?, 'play', '2026-01-09T18:00:00', 1)", (k,))
    sh.commit()
    n = sqlite3.connect(d / "n.sqlite")
    n.execute("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT,"
              " pid INTEGER, player TEXT, status TEXT, reason TEXT)")
    n.commit()
    sqlite3.connect(d / "q.sqlite").execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, "
                                            "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    B.SHADOW, B.NEWS, B.LINES = d / "s.sqlite", d / "n.sqlite", d / "q.sqlite"
    b = B.board(NOW)
    off = {(r["b"], r["stat"]): r["why"] for r in b["offcard"]}
    assert off == {("Gui Santos", "PRA"): "1 PER PLAYER", ("Dillon Brooks", "PTS"): "TEAM SLOT"}, off
    assert not b["retracted"]                       # never a retraction, so never a VOID ping
    shown = [r["b"] for s in b["slates"] for g in s["games"] for r in g["rows"]]
    assert shown == ["Gui Santos"] and "PINGED · OFF CARD" in B.html(b)


def test_veto_mutant_fails():
    src = pathlib.Path(B.__file__).read_text()
    a = '        if (gd, f["pid"]) in vetoed:\n'
    assert src.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_board_mutv.py").write_text(src.replace(a, '        if False:\n'))
    (d / "nba_clv.py").write_text((pathlib.Path(B.__file__).parent / "nba_clv.py").read_text())
    sys.path.insert(0, str(d))
    try:
        assert not check_veto(importlib.import_module("nba_board_mutv"))
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("nba_board_mutv", None)


def test_mutants():
    src = pathlib.Path(B.__file__).read_text()
    for name, a, b in (
            ("retraction off", "if not started and st.get(f[\"pid\"]) in B_OFF:", "if False:"),
            ("latest flag wins", "if k not in opp:", "if True:"),
            ("voids shown", "WHERE void_reason IS NULL AND COALESCE(card, 1) = 1", "WHERE 1 AND COALESCE(card, 1) = 1"),
            ("no stat canonicalisation", "STAT.get(f[\"stat\"], f[\"stat\"]))\n", "f[\"stat\"])\n"),
            ("oldest report", "SELECT MAX(mark) FROM snapshots", "SELECT MIN(mark) FROM snapshots"),
            ("star-back ignored", "and st.get(f[\"x_pid\"]) in X_BACK", "and False"),
            ("FD now from every book", "books=(\"fd\",))", "books=None)")):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_board_mut.py").write_text(src.replace(a, b).replace(
            'HERE = Path(__file__).resolve().parent', f'HERE = Path({str(pathlib.Path(B.__file__).parent)!r})'))
        sys.path.insert(0, str(d))
        try:
            mut = importlib.import_module("nba_board_mut")
            print(f"MUTANT ({name}) — must fail:")
            try:
                survived = check(mut)
            except Exception as e:
                print(f"   (crashed: {type(e).__name__})")
                survived = False
            assert not survived, name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_board_mut", None)


if __name__ == "__main__":
    test_board()
    test_mutants()
    print("test_nba_board: OK")
