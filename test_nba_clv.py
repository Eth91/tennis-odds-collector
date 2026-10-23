"""nba_clv: the closing line is rebuilt correctly from the change log, and the beat/at-close
arithmetic is right. Includes a MUTANT (pulled rungs treated as live) that must fail."""
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_clv as V
import nba_flags as F

TIP = "2026-01-10T00:00:00"


def build():
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    q = sqlite3.connect(d / "q.sqlite")
    q.executescript("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER,"
                    " player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    def quote(t, book, pid, line, side, odds):
        q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (t, book, "G", TIP, pid, f"p{pid}", "points", line, side, odds))
    def flag(pid, line, odds, actual):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, "
                   "odds, gid, gtime, pid, actual, news_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (f"f{pid}", "2026-01-09T20:00:00", "2026-01-09", "priced", "T", "X", f"p{pid}",
                    "points", line, odds, "G", TIP + "Z", pid, actual, "2026-01-09T19:45:00+00:00"))
    # 1: line moves 10.5 -> 11.5 by tip                       -> beat, move +1
    quote("2026-01-09T20:00:00", "fd", 1, 10.5, "over", 1.91); quote("2026-01-09T20:00:00", "fd", 1, 10.5, "under", 1.91)
    quote("2026-01-09T23:00:00", "fd", 1, 10.5, "over", None); quote("2026-01-09T23:00:00", "fd", 1, 10.5, "under", None)
    quote("2026-01-09T23:00:00", "fd", 1, 11.5, "over", 1.91); quote("2026-01-09T23:00:00", "fd", 1, 11.5, "under", 1.91)
    flag(1, 10.5, 1.91, 11)                                  # wins as flagged, LOSES over 11.5
    # 2: same line, over shortens 1.91 -> 1.80                -> beat
    quote("2026-01-09T20:00:00", "dk", 2, 20.5, "over", 1.91); quote("2026-01-09T20:00:00", "dk", 2, 20.5, "under", 1.91)
    quote("2026-01-09T23:30:00", "dk", 2, 20.5, "over", 1.80); quote("2026-01-09T23:30:00", "dk", 2, 20.5, "under", 2.02)
    flag(2, 20.5, 1.91, 25)
    # 3: same line, over lengthens 1.91 -> 2.05; a quote AFTER tip must be ignored -> not beat
    quote("2026-01-09T20:00:00", "fd", 3, 5.5, "over", 1.91); quote("2026-01-09T20:00:00", "fd", 3, 5.5, "under", 1.91)
    quote("2026-01-09T23:50:00", "fd", 3, 5.5, "over", 2.05); quote("2026-01-09T23:50:00", "fd", 3, 5.5, "under", 1.78)
    quote("2026-01-10T00:05:00", "fd", 3, 5.5, "over", 1.50)  # post-tip
    flag(3, 5.5, 1.91, 4)
    # 4 (AMENDMENT 4): the two yardsticks disagree. Flag time: FD 11.5, DK 10.5 (the flag took DK's
    # 10.5). By tip FD's over shortened 1.91 -> 1.80 (FD: beat), DK's lengthened 1.91 -> 1.95, and the
    # two-book close is DK's 10.5 @1.95 (nearer even money) (FD+DK: not beat). An FD move AFTER the
    # flag but before tip must not leak into the flag-time rung.
    for t, bk, ln, o, u in (("2026-01-09T19:59:00", "fd", 11.5, 1.91, 1.91), ("2026-01-09T19:59:00", "dk", 10.5, 1.91, 1.91),
                            ("2026-01-09T21:00:00", "fd", 11.5, 1.85, 1.97),
                            ("2026-01-09T23:40:00", "fd", 11.5, 1.80, 2.02), ("2026-01-09T23:40:00", "dk", 10.5, 1.95, 1.87)):
        quote(t, bk, 4, ln, "over", o); quote(t, bk, 4, ln, "under", u)
    flag(4, 10.5, 1.91, 11)
    # 5 (AMENDMENT 4): FanDuel posts only AFTER the flag -> no flag-time FD rung -> not in the primary
    quote("2026-01-09T19:59:00", "dk", 5, 7.5, "over", 1.91); quote("2026-01-09T19:59:00", "dk", 5, 7.5, "under", 1.91)
    quote("2026-01-09T22:00:00", "fd", 5, 7.5, "over", 1.91); quote("2026-01-09T22:00:00", "fd", 5, 7.5, "under", 1.91)
    flag(5, 7.5, 1.91, 9)
    sh.commit(); q.commit()
    V.SHADOW, V.LINES = d / "s.sqlite", d / "q.sqlite"
    return {r["pid"]: r for r in V.collect()}


def check(rows):
    ok = True
    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    r1, r2, r3 = rows[1], rows[2], rows[3]
    want(r1["close"][0] == 11.5 and r1["beat"] and r1["move"] == 1.0, "line moved up: close 11.5, beat, move +1")
    want(r1["u_flag"] > 0 and r1["u_close"] == -1.0, "actual 11: wins over 10.5 as flagged, loses over 11.5 at close")
    want(r2["close"][:2] == (20.5, 1.80) and r2["beat"], "same line, price shortened: beat")
    want(r3["close"][:2] == (5.5, 2.05) and not r3["beat"], "price lengthened: not beat; post-tip quote ignored")
    want(abs(r1["latency_min"] - 15.0) < 1e-6, "latency = flag time - news time = 15 min")
    r4 = rows[4]
    want(r4["fd_flag"] == (11.5, 1.91, 1) and r4["fd_close"] == (11.5, 1.80, 1),
         "amend4: FD-only rung at flag time (11.5 @1.91, not DK's 10.5; later FD move excluded) and at tip")
    want(r4["fd_beat"] and r4["fd_move"] == 0.0 and r4["close"][:2] == (10.5, 1.95) and not r4["beat"],
         "amend4: FD yardstick beat (price shortened) while the two-book yardstick did not")
    want(r4["fd_u_flag"] == -1.0 and abs(r4["u_flag"] - 0.91) < 1e-9,
         "amend4: actual 11 loses FD's 11.5, wins the flagged 10.5")
    want(r1["fd_flag"][0] == 10.5 and r1["fd_close"][0] == 11.5 and r1["fd_beat"] and r1["fd_move"] == 1.0,
         "amend4: FD line moved 10.5 -> 11.5: beat, move +1")
    want(r2.get("fd_flag") is None and V.view(r2, "FD")["close"] is None,
         "amend4: a DK-only flag has no FD yardstick (not counted in the primary)")
    r5 = rows[5]
    want(r5["fd_flag"] is None and r5["fd_close"] is not None and V.view(r5, "FD")["close"] is None,
         "amend4: FD posted only after the flag -> no FD yardstick")
    return ok


def test_real():
    assert check(build())


def test_mutant_pulled_rungs_as_live():
    orig = V.close_of
    def mutant(qcon, gid, pid, stat, tip, books=None):       # forget that NULL means pulled
        rows = [(b, l, s, o) for b, l, s, o in qcon.execute(
            "SELECT book, line, side, odds FROM quotes WHERE gid=? AND pid=? AND stat=? AND "
            "seen_at <= ? AND odds IS NOT NULL ORDER BY seen_at", (gid, pid, stat, tip))
            if not books or b in books]
        st = {}
        for b, l, s, o in rows:
            st[(b, round(l, 1), s)] = o
        best = None
        for (b, l, s), o in st.items():
            if s == "over" and (b, l, "under") in st and (best is None or abs(o - 1.9091) < abs(best[1] - 1.9091)):
                best = (l, o, 1)
        return best
    V.close_of = mutant
    try:
        assert not check(build())
    finally:
        V.close_of = orig


def test_mutant_fd_yardstick_reads_every_book():
    orig = V.PRIMARY_BOOKS
    V.PRIMARY_BOOKS = None                                     # forget amendment 4's book filter
    try:
        assert not check(build())
    finally:
        V.PRIMARY_BOOKS = orig


if __name__ == "__main__":
    print("REAL:"); test_real()
    print("MUTANT (FD yardstick reads every book) — must fail:"); test_mutant_fd_yardstick_reads_every_book()
    print("MUTANT (pulled rungs treated as live) — must fail:"); test_mutant_pulled_rungs_as_live()
    print("test_nba_clv: OK")


def test_one_opportunity_per_game_earliest_flag_wins():
    """A day-before flag (h1) and a game-day re-flag at a moved line are ONE opportunity."""
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    q = sqlite3.connect(d / "q.sqlite")
    q.executescript("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER,"
                    " player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    for side in ("over", "under"):
        q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)",
                  ("2026-01-09T12:00:00", "fd", "G", TIP, 9, "p9", "points", 11.5, side, 1.91))
    for fid, at, line, h in (("early", "2026-01-08T21:00:00", 10.5, 1), ("late", "2026-01-09T18:00:00", 11.5, 0)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, "
                   "gid, gtime, pid, horizon) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (fid, at, "2026-01-09", "priced", "T", "X", "p9", "points", line, 1.91, "G", TIP + "Z", 9, h))
    sh.commit(); q.commit()
    V.SHADOW, V.LINES = d / "s.sqlite", d / "q.sqlite"
    rows = V.collect()
    assert len(rows) == 1 and rows[0]["flag_id"] == "early" and rows[0]["horizon"] == 1
    assert rows[0]["beat"] and rows[0]["move"] == 1.0          # flagged 10.5 a day early, closed 11.5


def test_news_trigger_confirmed_vs_unconfirmed():
    """Amendment 2: a news-originated flag counts only if the official report lists the absent
    player Out for that game before tip; otherwise it is an unconfirmed audit row."""
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    q = sqlite3.connect(d / "q.sqlite")
    q.executescript("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER,"
                    " player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    nw = sqlite3.connect(d / "n.sqlite")
    nw.executescript("CREATE TABLE snapshots (mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT,"
                     " team TEXT, pid INTEGER, player TEXT, status TEXT, reason TEXT)")
    for pid in (21, 22):
        for side in ("over", "under"):
            q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)",
                      ("2026-01-09T12:00:00", "fd", "G", TIP, pid, "p", "points", 9.5, side, 1.91))
    # X=101's Out confirmed by the 18:00 report (before tip); X=102 never ruled Out
    nw.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
               ("m", "2026-01-09T18:00:04+00:00", "2026-01-09", "A@B", "T", 101, "x1", "Out", ""))
    nw.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
               ("m", "2026-01-09T18:00:04+00:00", "2026-01-09", "A@B", "T", 102, "x2", "Questionable", ""))
    for fid, b, x in (("c", 21, 101), ("u", 22, 102)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, "
                   "gid, gtime, pid, horizon, x_pid, trigger_src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (fid, "2026-01-09T17:30:00", "2026-01-09", "priced", "T", "X", f"p{b}", "points",
                    9.5, 1.91, "G", TIP + "Z", b, 0, x, "news:rotowire"))
    sh.commit(); q.commit(); nw.commit()
    V.SHADOW, V.LINES, V.NEWS = d / "s.sqlite", d / "q.sqlite", d / "n.sqlite"
    rows = {r["flag_id"]: r for r in V.collect()}
    assert rows["c"]["confirmed"] is True and rows["u"]["confirmed"] is False
