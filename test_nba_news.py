"""nba_news_watch: classifier, day parsing, add-only/contradiction. A MUTANT that ignores a later
official contradiction must fail."""
import datetime as dt
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_news_watch as N

THU = dt.datetime(2026, 10, 22, 16, 30, tzinfo=N.ET)


def test_classifier():
    cases = [("Ruled out for Friday", "", "out"), ("Won't suit up Friday", "", "out"),
             ("Doubtful for Friday", "", "other"), ("Remains out for Friday", "", "out"),
             ("Missing second straight game", "Martin (thumb) won't play Friday.", "out"),
             ("Won't play Friday", "He'll look to return Saturday.", "out"),
             ("Questionable for Friday", "", "other"), ("Iffy for Friday", "", "other"),
             ("Likely to play Friday", "", "other"), ("Quiet in season debut", "9 points.", "other")]
    for h, b, want in cases:
        assert N.status_of(h, b) == want, (h, b)


def test_day_parse_headline_first():
    assert N.game_date_of("Ruled out for Friday", "after missing Wednesday's game", THU) == "2026-10-23"
    assert N.game_date_of("Out tonight", "", THU) == "2026-10-22"
    assert N.game_date_of("Big night", "won't play Saturday", THU) == "2026-10-24"
    assert N.game_date_of("Big night", "no day here", THU) is None


def _db(official_status, official_after_news):
    d = pathlib.Path(tempfile.mkdtemp()) / "n.sqlite"
    con = sqlite3.connect(d)
    con.executescript(N.I.DDL)
    N._migrate(con)
    con.execute("INSERT INTO news_items (source, item_id, detected_at, player, pid, team, game_date, "
                "status, headline, body, provenance) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("rotowire", "1", "2026-10-22T19:00:00+00:00", "P", 7, "NYK", "2026-10-23", "out",
                 "Ruled out for Friday", "", "x"))
    pub = "2026-10-22T19:15:04+00:00" if official_after_news else "2026-10-22T18:45:04+00:00"
    con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                ("m", pub, "2026-10-23", "NYK@BOS", "NYK", 7, "P", official_status, ""))
    con.commit()
    return con


def check(fn):
    later_q = 7 in fn("2026-10-23", con=_db("Questionable", official_after_news=True))
    earlier_q = 7 in fn("2026-10-23", con=_db("Questionable", official_after_news=False))
    later_out = 7 in fn("2026-10-23", con=_db("Out", official_after_news=True))
    return (not later_q) and earlier_q and later_out


def test_add_only_and_contradiction():
    assert check(N.news_outs)


def test_mutant_ignoring_contradiction_fails():
    def mutant(game_date, con):
        return {p: (n, t, f, s) for p, n, t, f, s in con.execute(
            "SELECT pid, player, team, MIN(detected_at), source FROM news_items WHERE game_date=? "
            "AND status='out' AND pid IS NOT NULL GROUP BY pid", (game_date,))}
    assert not check(mutant)


if __name__ == "__main__":
    test_classifier(); test_day_parse_headline_first(); test_add_only_and_contradiction()
    test_mutant_ignoring_contradiction_fails()
    print("test_nba_news: OK")


def test_first_poll_of_a_source_seeds_and_never_triggers():
    d = pathlib.Path(tempfile.mkdtemp()) / "n.sqlite"
    con = sqlite3.connect(d)
    con.executescript(N.I.DDL)
    item = {"item_id": "1", "player": "Jalen Brunson", "team_name": "New York Knicks",
            "headline": "Ruled out for Friday", "body": "", "provenance": "x"}
    saved = N.SOURCES
    N.SOURCES = {"fake": lambda: [item]}
    try:
        outs1, _ = N.poll(now=dt.datetime(2026, 10, 22, 20, 0, tzinfo=dt.timezone.utc), con=con)
        item2 = dict(item, item_id="2")
        N.SOURCES = {"fake": lambda: [item, item2]}
        outs2, _ = N.poll(now=dt.datetime(2026, 10, 22, 20, 1, tzinfo=dt.timezone.utc), con=con)
    finally:
        N.SOURCES = saved
    assert outs1 == []                                    # the backlog never fires
    assert len(outs2) == 1                                # a genuinely new item does
    assert con.execute("select seeded from news_items where item_id='1'").fetchone()[0] == 1
