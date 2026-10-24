"""nba_lines.cycle(only_gids=...) (amendment 12): FanDuel is fetched and written for the requested
games only. Their changes and pulled rungs are logged; every other game's board rows and quotes are
untouched; the cycle row says 'game'. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_lines as L

G1 = {"status": 1, "utc": "2099-01-01T00:00:00Z", "gid": "G1", "home": "BOS", "away": "NYK",
      "home_nick": "Celtics", "away_nick": "Knicks", "date_et": "2098-12-31"}
G2 = {"status": 1, "utc": "2099-01-01T01:00:00Z", "gid": "G2", "home": "ORL", "away": "MIA",
      "home_nick": "Magic", "away_nick": "Heat", "date_et": "2098-12-31"}
E1, E2 = "New York Knicks @ Boston Celtics", "Miami Heat @ Orlando Magic"


def rows(e1_over, e1_has_reb=True, e2_over=1.91):
    r = [(E1, "Jalen Brunson", "points", 25.5, "over", e1_over), (E1, "Jalen Brunson", "points", 25.5, "under", 1.91),
         (E2, "Bam Adebayo", "points", 18.5, "over", e2_over), (E2, "Bam Adebayo", "points", 18.5, "under", 1.91)]
    if e1_has_reb:
        r += [(E1, "Jalen Brunson", "rebounds", 3.5, "over", 1.91), (E1, "Jalen Brunson", "rebounds", 3.5, "under", 1.91)]
    return r


def setup(mod):
    d = pathlib.Path(tempfile.mkdtemp())
    mod.DB = d / "l.sqlite"
    saved = {k: getattr(mod.R, k) for k in ("schedule", "season_boxes", "player_index", "state")}
    mod.R.schedule = lambda: [G1, G2]
    mod.R.season_boxes = lambda sched: ({}, None)
    mod.R.player_index = lambda day: ({}, "")
    mod.R.state = lambda day, boxes, index=None: ({}, {}, {})

    class Resolver:
        def __init__(self, *a):
            pass

        def __call__(self, player, home, away):
            return 1 if "Brunson" in player else 2
    mod.Resolver = Resolver
    state = {"rows": rows(1.91), "seen_filters": []}

    def fake_fd(event_filter=None):
        state["seen_filters"].append(event_filter)
        return [r for r in state["rows"] if event_filter is None or event_filter(r[0])], ""
    mod.fetch_fd = fake_fd
    mod.BOOKS["fd"] = fake_fd
    return d, state, saved


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    d, state, saved = setup(mod)
    try:
        mod.cycle(("fd",))                                         # full board first
        state["rows"] = rows(1.80, e1_has_reb=False, e2_over=2.10)  # G1 moved + pulled reb; G2 moved too
        mod.cycle(("fd",), only_gids={"G1"})
        c = sqlite3.connect(mod.DB)
        want(c.execute("SELECT odds FROM board WHERE player='Jalen Brunson' AND stat='points' AND side='over'"
                       ).fetchone() == (1.80,), "G1's price move lands on the board")
        want(c.execute("SELECT COUNT(*) FROM quotes WHERE gid='G1' AND stat='rebounds' AND odds IS NULL").fetchone()[0] == 2,
             "G1's vanished rebounds rung is logged as pulled")
        want(c.execute("SELECT odds FROM board WHERE player='Bam Adebayo' AND side='over'").fetchone() == (1.91,)
             and c.execute("SELECT COUNT(*) FROM quotes WHERE gid='G2'").fetchone()[0] == 2,
             "G2 untouched: its board row and change log are exactly as the full refresh left them")
        want(c.execute("SELECT COUNT(*) FROM board WHERE gid='G2'").fetchone()[0] == 2, "G2's rows are not deleted")
        want(c.execute("SELECT status FROM cycles ORDER BY rowid DESC LIMIT 1").fetchone()[0] == "game",
             "the per-game refresh is logged as 'game', never as a full refresh")
        f = state["seen_filters"][-1]
        want(f is not None and f(E1) and not f(E2), "only the requested game's event is fetched")
    finally:
        for k, v in saved.items():
            setattr(mod.R, k, v)
    return ok


def test_partial():
    assert check(importlib.reload(L))
    importlib.reload(L)


def test_mutants():
    src = pathlib.Path(L.__file__).read_text()
    for name, a, b in (
            ("delete every game", 'con.execute(f"DELETE FROM board WHERE book=? AND gid IN ({qmarks})", (book, *sorted(scope)))',
             'con.execute("DELETE FROM board WHERE book=?", (book,))'),
            ("pulled across all games", '"SELECT player, stat, line, side, odds, gid, tip_utc, pid FROM board WHERE book=? "\n                f"AND gid IN ({qmarks})", (book, *sorted(scope)))}',
             '"SELECT player, stat, line, side, odds, gid, tip_utc, pid FROM board WHERE book=?", (book,))}'),
            ("logged as a full refresh", '(bts, book, "game" if scope else status, len(board), len(events),',
             '(bts, book, status, len(board), len(events),')):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_lines_mutp.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({name}) — must fail:")
            assert not check(importlib.import_module("nba_lines_mutp")), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_lines_mutp", None)


if __name__ == "__main__":
    test_partial()
    test_mutants()
    print("test_nba_lines_partial: OK")
