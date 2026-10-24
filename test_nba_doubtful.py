"""Amendment 15: Doubtful is an absence. Classifier, news Outs, the report watcher's fresh Outs, the
board's take-back and the clv `doubtful` cell. MUTANTS in test_mutants()."""
import contextlib
import datetime as dt
import importlib
import io
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_board as B
import nba_clv as V
import nba_flags as F
import nba_injury_report as I
import nba_news_watch as NW
import nba_watch as W

CLASSES = [("", "Draymond Green (back) listed doubtful Saturday.", "doubtful"),
           ("Doubtful for Friday", "", "doubtful"),
           ("", "Embiid upgraded from doubtful to questionable for Saturday.", "other"),
           ("", "Embiid is no longer doubtful for Saturday.", "other"),
           ("", "Green is doubtful, a game-time decision Saturday.", "other"),
           ("", "Embiid is doubtful for one of the two games this weekend.", "other"),
           ("", "Curry ruled out Saturday; Green doubtful.", "out"),
           ("Questionable for Friday", "", "other")]


def news_db():
    con = sqlite3.connect(":memory:")
    con.executescript(I.DDL)
    NW._migrate(con)
    return con


def item(con, iid, at, status, pid=7):
    con.execute("INSERT INTO news_items (source, item_id, detected_at, player, pid, team, game_date, status, "
                "headline, body, provenance) VALUES ('x',?,?,'P',?,'NYK','2026-10-23',?,'','','x')",
                (iid, at, pid, status))


def report(con, mark, pid, status, gd="2026-10-23"):
    con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)", (mark, mark, gd, "", "NYK", pid, "P", status, ""))


def check_news(nw):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    want(all(nw.status_of(h, b) == w for h, b, w in CLASSES), "classifier: doubtful, its hedges, out + doubtful")
    c = news_db(); item(c, "1", "2026-10-22T19:00:00+00:00", "doubtful")
    report(c, "2026-10-22T19:15:00+00:00", 7, "Doubtful")
    want(nw.news_outs("2026-10-23", con=c).get(7, (0,) * 5)[4] == "Doubtful",
         "news doubtful, later report Doubtful: kept, status Doubtful")
    c = news_db(); item(c, "1", "2026-10-22T19:00:00+00:00", "doubtful")
    report(c, "2026-10-22T19:15:00+00:00", 7, "Questionable")
    want(7 not in nw.news_outs("2026-10-23", con=c), "news doubtful, later report Questionable: contradicted")
    c = news_db(); item(c, "1", "2026-10-22T19:00:00+00:00", "out")
    report(c, "2026-10-22T19:15:00+00:00", 7, "Doubtful")
    want(nw.news_outs("2026-10-23", con=c).get(7, (0,) * 5)[4] == "Out",
         "news out, later report Doubtful: NOT a contradiction, status Out")
    c = news_db(); item(c, "1", "2026-10-22T19:00:00+00:00", "doubtful"); item(c, "2", "2026-10-22T19:05:00+00:00", "out")
    r = nw.news_outs("2026-10-23", con=c).get(7)
    want(r and r[2] == "2026-10-22T19:00:00+00:00" and r[4] == "Out", "doubtful then out: earliest time, status Out")
    return ok


def check_fresh(w):
    c = news_db()
    for pid, st in ((1, "Questionable"), (2, "Doubtful"), (4, "Out")):
        report(c, "m1", pid, st)
    for pid, st in ((1, "Doubtful"), (2, "Out"), (3, "Doubtful"), (4, "Out")):
        report(c, "m2", pid, st)
    got = sorted(f[0] for f in w.fresh_outs(c, "m2"))
    print(f"   {'ok ' if got == [1, 3] else 'BAD'} fresh at m2: Questionable->Doubtful and new Doubtful; "
          f"not Doubtful->Out, not Out->Out (got {got})")
    return got == [1, 3]


def check_cell(v):
    def row(xs):
        return {"tier": "wowy", "gid": "G", "horizon": 0, "confirmed": None, "x_status": xs,
                "fd_flag": (10.5, 1.91), "fd_close": (11.5, 1.91), "fd_beat": True, "fd_move": 1.0}
    v.VOIDED = 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        v.scoreboard([row(None), row("Out"), row("Doubtful")])
    lines = {ln.split()[0] + " " + ln.split()[1]: int(ln.split()[2]) for ln in buf.getvalue().splitlines()
             if ln.startswith("wowy/")}
    ok = lines.get("wowy/h0 FD") == 2 and lines.get("wowy/doubtful FD") == 1
    print(f"   {'ok ' if ok else 'BAD'} clv: the Doubtful flag in its own cell, out of h0 ({lines})")
    return ok


def test_doubtful_news():
    assert check_news(NW)


def test_fresh_outs():
    assert check_fresh(W)


def test_clv_cell():
    assert check_cell(V)


def test_board_takeback():
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    for fid, b, pid, xpid in (("q", "Ann", 1, 201), ("o", "Bob", 2, 202)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, gtime, "
                   "matchup, pid, x_pid, horizon, x_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'Doubtful')",
                   (fid, "2026-01-09T18:00:00", "2026-01-09", "wowy", "BBB", "X", b, "pts", 10.5, 1.91, "G1",
                    "2026-01-10T03:00:00Z", "AAA @ BBB", pid, xpid))
    sh.commit()
    n = sqlite3.connect(d / "n.sqlite")
    n.executescript(I.DDL)
    for pid, st in ((201, "Questionable"), (202, "Doubtful")):
        n.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                  ("2026-01-09T16:30", "2026-01-09T16:30", "2026-01-09", "", "", pid, "", st, ""))
    n.commit()
    q = sqlite3.connect(d / "q.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT,"
              " stat TEXT, line REAL, side TEXT, odds REAL)")
    q.commit()
    B.SHADOW, B.NEWS, B.LINES = d / "s.sqlite", d / "n.sqlite", d / "q.sqlite"
    out = B.board(dt.datetime(2026, 1, 9, 22, 0, tzinfo=dt.timezone.utc))
    off = {r["b"] for r in out["retracted"]}
    assert off == {"Ann"}, off            # X Doubtful -> Questionable: taken back; still Doubtful: stays


def test_absent_matches_board_and_clv():
    assert I.ABSENT == B.B_OFF and set(I.ABSENT).isdisjoint(B.X_BACK)
    assert I.ABSENT_SQL == "status IN ('Out', 'Doubtful')"


def _mutant(mod, tag, a, b, check):
    src = pathlib.Path(mod.__file__).read_text()
    assert src.count(a) == 1, tag
    d = pathlib.Path(tempfile.mkdtemp())
    name = f"{pathlib.Path(mod.__file__).stem}_mut15"
    (d / f"{name}.py").write_text(src.replace(a, b))
    sys.path.insert(0, str(d))
    try:
        print(f"MUTANT ({tag}) — must fail:")
        try:
            survived = check(importlib.import_module(name))
        except Exception as e:                       # noqa: BLE001
            print(f"   (crashed: {type(e).__name__})")
            survived = False
        assert not survived, tag
    finally:
        sys.path.remove(str(d))
        sys.modules.pop(name, None)


def test_mutants():
    _mutant(NW, "doubtful ignored", "        if DOUBTFUL_RE.search(t):\n", "        if False:\n", check_news)
    _mutant(NW, "doubtful hedges ignored",
            'return "other" if hedged else "doubtful"', 'return "doubtful"', check_news)
    _mutant(NW, "a later Doubtful contradicts a news Out", "AND NOT {I.ABSENT_SQL} AND", "AND status!='Out' AND",
            check_news)
    _mutant(W, "fresh Outs read Out only", 'f"{I.ABSENT_SQL} AND pid IS NOT NULL"',
            '"status=\'Out\' AND pid IS NOT NULL"', check_fresh)
    _mutant(W, "Doubtful -> Out fires twice",
            'f"SELECT pid FROM snapshots WHERE mark=? AND game_date=? AND {I.ABSENT_SQL}",',
            '"SELECT pid FROM snapshots WHERE mark=? AND game_date=? AND status=\'Out\'",', check_fresh)
    _mutant(V, "no doubtful cell", '                else "doubtful" if r.get("x_status") == "Doubtful"\n', "",
            check_cell)


if __name__ == "__main__":
    test_doubtful_news(); test_fresh_outs(); test_clv_cell(); test_board_takeback()
    test_absent_matches_board_and_clv(); test_mutants()
    print("test_nba_doubtful: OK")
