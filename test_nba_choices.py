"""Amendment 14: a choice ("plays only one of A / B") -> pending -> resolved by the official report or
the live box score; PLAYED in A => inferred Out for B (news item + trigger). MUTANTS."""
import datetime as dt
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_injury_report as I
import nba_news_watch as NW
import nba_watch as W

THU = dt.datetime(2026, 10, 22, 22, 0, tzinfo=NW.ET)
EMBIID = ("Joel Embiid said he won't play in both legs of Sixers' back-to-back set on Saturday and Sunday. "
          "\"I'm playing in one of them.\"")
SCHED = [{"gid": "GA", "date_et": "2026-10-24", "utc": "2026-10-24T23:30:00Z", "status": 1, "home": "PHI", "away": "MIL"},
         {"gid": "GB", "date_et": "2026-10-25", "utc": "2026-10-25T23:00:00Z", "status": 1, "home": "PHI", "away": "DET"}]


def test_choice_dates():
    team = {"2026-10-24", "2026-10-25", "2026-10-27"}
    assert NW.choice_dates(EMBIID, THU, team) == ["2026-10-24", "2026-10-25"]
    assert NW.choice_dates("He won't play both games of the back-to-back.", THU, team) == ["2026-10-24", "2026-10-25"]
    assert NW.choice_dates("won't play in both, Saturday only", THU, {"2026-10-24"}) is None


def test_register():
    con = sqlite3.connect(":memory:")
    NW._migrate(con)
    index = {203954: ("PHI", "Joel Embiid", "C"), 1: ("PHI", "Joel Smith", "G")}
    reg = NW.register_choice(con, {"item_id": "x1", "headline": "", "body": EMBIID, "provenance": "x:underdog"},
                             index, {"PHI": {"2026-10-24", "2026-10-25"}}, THU, THU)
    assert reg == (203954, "Joel Embiid", "PHI", ["2026-10-24", "2026-10-25"])
    assert con.execute("SELECT state FROM choices").fetchone() == ("pending",)


def setup(con):
    con.executescript(I.DDL)
    NW._migrate(con)
    con.execute("INSERT INTO choices VALUES (203954,'Joel Embiid','PHI','2026-10-24','2026-10-25','x1',"
                "'x:underdog','t','pending',NULL,NULL)")
    con.commit()


def run(mod, now, box=None, report=None):
    con = sqlite3.connect(":memory:")
    setup(con)
    if report:                                    # (game_date, status) on an official report
        gd, st = report
        con.execute("INSERT INTO reports (mark, published_at) VALUES ('m1', '2026-10-24T18:00:00+00:00')")
        con.execute("INSERT INTO snapshots (mark, published_at, game_date, matchup, team, pid, player, status, reason) "
                    "VALUES ('m1','2026-10-24T18:00:00+00:00',?,'','PHI',203954,'Joel Embiid',?,'')", (gd, st))
    fired = []
    mod._now = lambda: now
    mod.resolve_choices(con, SCHED, [], fire=lambda c, label, at, fresh, log: fired.append((label, fresh)),
                        box_get=lambda gid: box)
    state = con.execute("SELECT state FROM choices").fetchone()[0]
    inferred = con.execute("SELECT game_date, status FROM news_items WHERE source='inferred'").fetchall()
    return state, fired, inferred


def box(played=None, status="ACTIVE", game_status=2):
    players = [] if played is None else [{"personId": 203954, "played": played, "status": status}]
    return {"gameStatus": game_status, "homeTeam": {"teamTricode": "PHI", "players": players},
            "awayTeam": {"teamTricode": "MIL", "players": []}}


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    live = dt.datetime(2026, 10, 24, 23, 40, tzinfo=dt.timezone.utc)
    st, fired, inf = run(mod, live, box(played="1"))
    want(st == "inferred_out_b" and fired == [("news:inferred", [(203954, "Joel Embiid", "PHI", "2026-10-25")])]
         and inf == [("2026-10-25", "out")], "PLAYED game A -> inferred Out for B: news item for B + trigger for B")
    st, fired, _ = run(mod, live, box(played="0", status="INACTIVE"))
    want(st == "plays_b" and not fired, "INACTIVE in A -> he plays B, nothing fired")
    st, fired, _ = run(mod, dt.datetime(2026, 10, 24, 20, 0, tzinfo=dt.timezone.utc), box(played="1"))
    want(st == "pending" and not fired, "hours before A's tip: still pending, box not read")
    st, fired, _ = run(mod, live, box(played="1"), report=("2026-10-24", "Out"))
    want(st == "plays_b" and not fired, "report lists him Out for A -> plays B")
    st, fired, _ = run(mod, live, box(played="1"), report=("2026-10-25", "Out"))
    want(st == "out_b_report" and not fired, "report already lists him Out for B -> nothing to infer")
    st, fired, _ = run(mod, live, box(played="0", game_status=3))
    want(st == "plays_b" and not fired, "A final without him playing -> plays B")
    return ok


def test_resolve():
    assert check(W)


def test_mutants():
    src = pathlib.Path(W.__file__).read_text()
    for name, a, b in (
            ("fires for A instead of B", 'fire(con, "news:inferred", now.isoformat(), [(pid, name, tri, b)], log)',
             'fire(con, "news:inferred", now.isoformat(), [(pid, name, tri, a)], log)'),
            ("played check off", 'if p and p.get("played") == "1":', 'if p:'),
            ("report on A ignored", 'done("plays_b", f"official report lists him Out for {a}")\n            continue',
             'pass')):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_watch_mut14.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({name}) — must fail:")
            try:
                survived = check(importlib.import_module("nba_watch_mut14"))
            except Exception as e:
                print(f"   (crashed: {type(e).__name__})")
                survived = False
            assert not survived, name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_watch_mut14", None)


if __name__ == "__main__":
    test_choice_dates()
    test_register()
    test_resolve()
    test_mutants()
    print("test_nba_choices: OK")
