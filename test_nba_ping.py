"""nba_ping: the user's push format, one ping per play across tiers and re-flags, none once the game
has started, a failed send retried, and VOID only for a play that was pinged. MUTANTS."""
import datetime as dt
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_ping as P

NOW = dt.datetime(2026, 10, 24, 18, 0, tzinfo=dt.timezone.utc)
TIP = "2026-10-25T00:00:00Z"


def flag(**k):
    f = {"game_date": "2026-10-24", "pid": 7, "b": "Max Christie", "team": "DAL", "stat": "points",
         "line": 11.5, "odds": 1.8197, "tier": "priced", "gtime": TIP, "flag_id": "x"}
    f.update(k)
    return f


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    want(mod.play_body(flag()) == "🚨 DAL Max Christie PTS o11.5 -122 priced shadow", "the user's push format")
    sh = sqlite3.connect(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
    calls = []
    good = lambda body, pri: calls.append((body, pri)) or True
    mod.ping_plays(sh, [flag(), flag(tier="wowy", stat="pts", line=12.5, flag_id="y")], now=NOW, sender=good)
    want(len(calls) == 1 and calls[0][1] == "high", "two tiers / a re-flag of one play = ONE ping")
    mod.ping_plays(sh, [flag(line=12.5, flag_id="z")], now=NOW, sender=good)
    want(len(calls) == 1, "the same play later (moved line) does not ping again")
    mod.ping_plays(sh, [flag(pid=8, b="P.J. Washington", stat="reb_ast", gtime="2026-10-24T17:00:00Z")],
                   now=NOW, sender=good)
    want(len(calls) == 1, "a play whose game has started never pings")
    bad = lambda body, pri: False
    mod.ping_plays(sh, [flag(pid=9, b="A B", stat="rebounds")], now=NOW, sender=bad)
    mod.ping_plays(sh, [flag(pid=9, b="A B", stat="rebounds")], now=NOW, sender=good)
    want(len(calls) == 2 and "A B REB" in calls[-1][0], "a failed send is retried on the next pass")
    ret = [dict(flag(), stat="PTS", raw_stat="points", why="Max Christie OUT"),
           dict(flag(pid=99, b="Never Pinged"), stat="PTS", raw_stat="points", why="Never Pinged OUT")]
    mod.ping_voids(sh, ret, now=NOW, sender=good)
    want(len(calls) == 3 and calls[-1] == ("⚠ VOID DAL Max Christie PTS o11.5 Max Christie OUT", "urgent"),
         "VOID: urgent, once, only for a play that was pinged")
    mod.ping_voids(sh, ret, now=NOW, sender=good)
    want(len(calls) == 3, "a VOID is sent once")
    return ok


def test_ping():
    assert check(P)


def test_seed_stops_old_plays_pinging():
    sh = sqlite3.connect(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
    sh.execute("CREATE TABLE flags (game_date TEXT, pid INTEGER, b TEXT, stat TEXT, gtime TEXT, void_reason TEXT)")
    sh.execute("INSERT INTO flags VALUES ('2026-10-24', 7, 'Max Christie', 'points', ?, NULL)", (TIP,))
    assert P.seed(sh, NOW) == 1 and P.seed(sh, NOW) == 0
    calls = []
    P.ping_plays(sh, [flag(line=12.5)], now=NOW, sender=lambda b, p: calls.append(b) or True)
    assert calls == []                      # an old play re-flagged at a moved line stays quiet


def test_no_topic_is_quiet(monkeypatch=None):
    import os
    saved = os.environ.pop("NTFY_TOPIC", None)
    try:
        assert P.send("x") is False
    finally:
        if saved is not None:
            os.environ["NTFY_TOPIC"] = saved


def test_mutants():
    src = pathlib.Path(P.__file__).read_text()
    for name, a, b in (
            ("dedupe by flag id", 'return f"play|{f[\'game_date\']}|{f.get(\'pid\') or f[\'b\']}|{CANON.get(stat, stat)}"',
             'return f"play|{f.get(\'flag_id\')}"'),
            ("started games ping", "    for f in flags:\n        if _started(f.get(\"gtime\"), now):\n            continue\n",
             "    for f in flags:\n"),
            ("void without a ping", "if not pinged or (done and done[0]):", "if done and done[0]:"),
            ("failure counts as sent", "if row and row[0]:", "if row:")):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_ping_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({name}) — must fail:")
            assert not check(importlib.import_module("nba_ping_mut")), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_ping_mut", None)


if __name__ == "__main__":
    test_ping()
    test_no_topic_is_quiet()
    test_mutants()
    print("test_nba_ping: OK")
