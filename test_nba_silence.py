"""Amendment 21: the silence check, on the real 2026-10-24 case (RotoBaller's "Jalen Green doubtful", every
later report listing PHX without him). Grace, game-day reports only, team must be listed, inferred
exempt, the board takes the flag back. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_board as B
import nba_flags as F
import nba_injury_report as I
import nba_news_watch as NW
import nba_silence as S

GD, SEEN = "2026-10-24", "2026-10-24T21:37:38.389809+00:00"
GREEN, IGHO, BOOKER = 1630224, 1631367, 1626164


def news_db(path=":memory:"):
    con = sqlite3.connect(path)
    con.executescript(I.DDL)
    NW._migrate(con)

    def report(mark, pub, rows, gd=GD):
        con.execute("INSERT INTO reports (mark, published_at) VALUES (?, ?)", (mark, pub))
        for team, pid, st in rows:
            con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)", (mark, pub, gd, "", team, pid, "", st, ""))
    report("2026-10-23T17:00", "2026-10-23T21:00:04+00:00", [("PHX", IGHO, "Out")], gd="2026-10-24")   # day before
    report("2026-10-24T17:45", "2026-10-24T21:45:04+00:00", [("PHX", IGHO, "Out")])   # inside the 60-min grace
    report("2026-10-24T18:30", "2026-10-24T22:40:04+00:00", [("GSW", 203110, "Doubtful")])   # past the grace, PHX not listed
    report("2026-10-24T18:45", "2026-10-24T22:45:04+00:00", [("PHX", IGHO, "Out"), ("GSW", 203110, "Doubtful"),
                                                             ("PHI", 1631104, "Questionable")])   # PHI listed, not him
    for iid, pid, team, src, status in (("rb", GREEN, "PHX", "x", "doubtful"), ("ok", BOOKER, "PHX", "x", "out"),
                                        ("inf", 1642845, "PHI", "inferred", "out")):
        con.execute("INSERT INTO news_items (source, item_id, detected_at, player, pid, team, game_date, status, "
                    "headline, body, provenance) VALUES (?,?,?,?,?,?,?,?,'','','x')",
                    (src, iid, SEEN, "P", pid, team, GD, status))
    # next-day case: the 10/24 18:45 report also lists PHX for 10/25, without Green. Not game day for 10/25.
    con.execute("INSERT INTO snapshots VALUES ('2026-10-24T18:45','2026-10-24T22:45:04+00:00','2026-10-25','','PHX',?,"
                "'','Out','')", (IGHO,))
    # Booker: real news, on the report by the first eligible one
    con.execute("INSERT INTO snapshots VALUES ('2026-10-24T18:45','2026-10-24T22:45:04+00:00',?,'','PHX',?,'','Out','')",
                (GD, BOOKER))
    con.commit()
    return con


def check(sil, nw=NW):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    con = news_db()
    want(sil.silenced(con, GREEN, "PHX", GD, SEEN) == "2026-10-24T22:45:04+00:00",
         "Jalen Green silenced by the 18:45 ET report: past the grace, game day, PHX listed, he is not")
    want(sil.silenced(con, BOOKER, "PHX", GD, SEEN) is None, "real news: on the first eligible report -> not silenced")
    want(sil.silenced(con, GREEN, "PHX", GD, SEEN, grace_min=600) is None, "no eligible report yet -> not silenced")
    want(sil.silenced(con, GREEN, "PHX", "2026-10-25", SEEN) is None,
         "next-day game: a report from the day before lists PHX for 10/25 without him -> still not silenced")
    outs = nw.news_outs(GD, con=con) if nw else {}
    if nw:
        want(GREEN not in outs and BOOKER in outs and 1642845 in outs,
             "news_outs drops the silenced item, keeps real news, exempts the inferred one")
    return ok


def test_silence():
    import nba_silence
    assert check(nba_silence)


def test_board_takes_it_back():
    d = pathlib.Path(tempfile.mkdtemp())
    news_db(d / "n.sqlite").close()
    sh = F._shadow(d / "s.sqlite")
    for fid, b, pid, src, x, xpid, team in (("g", "Collin Gillespie", 1, "news:x", "Jalen Green", GREEN, "PHX"),
                                            ("e", "VJ Edgecombe", 2, "news:inferred", "Joel Embiid", 1642845, "PHI"),
                                            ("r", "Report Play", 3, "report", "Oso Ighodaro", IGHO, "PHX")):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, gtime, "
                   "matchup, pid, x_pid, horizon, trigger_src, news_at, card) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,1)",
                   (fid, "2026-10-24T22:11:52", GD, "wowy", team, x, b, "pts", 8.5, 1.8, "G" + team,
                    "2026-10-25T02:00:00Z", "GSW @ " + team, pid, xpid, src, SEEN))
    sh.commit()
    sqlite3.connect(d / "q.sqlite").execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, "
                                            "pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL)")
    B.SHADOW, B.NEWS, B.LINES = d / "s.sqlite", d / "n.sqlite", d / "q.sqlite"
    b = B.board(dt.datetime(2026, 10, 24, 23, 0, tzinfo=dt.timezone.utc))
    off = {r["b"]: r["why"] for r in b["retracted"]}
    assert off == {"Collin Gillespie": "Jalen Green NOT ON REPORT"}, off       # inferred and report flags stay


def test_mutants():
    src = pathlib.Path(S.__file__).read_text()
    for tag, a, b in (
            ("no grace", "        if _t(pub) < t0:\n            continue\n", ""),
            ("any day's report", "WHERE substr(mark, 1, 10) = ? ", "WHERE ? IS NOT NULL "),
            ("team need not be listed", "            continue                                   # the team is not on this report yet\n",
             "            pass\n")):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_silence_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_silence_mut"), nw=None), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_silence_mut", None)
    nsrc = pathlib.Path(NW.__file__).read_text()
    a = 'if src != "inferred" and SIL.silenced(con, pid, team, game_date, first):'
    assert nsrc.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_news_watch_mut21.py").write_text(nsrc.replace(a, 'if SIL.silenced(con, pid, team, game_date, first):'))
    sys.path.insert(0, str(d))
    try:
        print("MUTANT (inferred not exempt) — must fail:")
        assert not check(S, nw=importlib.import_module("nba_news_watch_mut21"))
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("nba_news_watch_mut21", None)


if __name__ == "__main__":
    test_silence(); test_board_takes_it_back(); test_mutants()
    print("test_nba_silence: OK")
