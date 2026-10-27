"""nba_lineups_poll.py: snapshots only on change (plus an hourly heartbeat); the ET date is DST-correct."""
def test_lineup_poll_stores_only_changes():
    import sqlite3, tempfile, pathlib, datetime as dt
    import nba_lineups_poll as L

    class R:
        def __init__(self, j):
            self.status_code, self._j = 200, j

        def json(self):
            return self._j
    con = sqlite3.connect(pathlib.Path(tempfile.mkdtemp()) / "l.sqlite")
    con.execute(L.DDL)
    t = dt.datetime(2026, 10, 26, 22, 0, tzinfo=dt.timezone.utc)
    j1, j2 = {"games": [{"gameId": "G", "x": 1}]}, {"games": [{"gameId": "G", "x": 2}]}
    assert L.poll_once(con, lambda u: R(j1), t) == "stored"
    assert L.poll_once(con, lambda u: R(j1), t + dt.timedelta(minutes=5)) == "same"
    assert L.poll_once(con, lambda u: R(j2), t + dt.timedelta(minutes=10)) == "stored"
    assert L.poll_once(con, lambda u: R(j2), t + dt.timedelta(minutes=80)) == "stored"      # hourly heartbeat
    assert L.et_date(dt.datetime(2026, 10, 27, 2, 0, tzinfo=dt.timezone.utc)) == "2026-10-26"
    assert L.et_date(dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.timezone.utc)) == "2026-11-02"   # EST: UTC-5
    assert L.et_date(dt.datetime(2027, 3, 8, 3, 30, tzinfo=dt.timezone.utc)) == "2027-03-07"


def test_lineups_report_uses_cutoff_and_started_state():
    import json, sqlite3, tempfile, pathlib, zlib
    import nba_lineups_report as RP
    d = pathlib.Path(tempfile.mkdtemp())
    con = sqlite3.connect(d / "l.sqlite")
    con.execute("CREATE TABLE snaps (fetched_at TEXT, date_et TEXT, sha TEXT, body BLOB)")

    def snap(at, starters, status, gs):
        players = [{"personId": p, "position": "G" if p in starters else "", "lineupStatus": status} for p in range(1, 9)]
        g = {"gameId": "G", "gameStatus": gs, "homeTeam": {"teamAbbreviation": "AAA", "players": players},
             "awayTeam": {"teamAbbreviation": "BBB", "players": []}}
        con.execute("INSERT INTO snaps VALUES (?,?,?,?)", (at, "2026-10-26", "x", zlib.compress(json.dumps({"games": [g]}).encode())))
    snap("2026-10-26T22:20:00+00:00", {1, 2, 3, 4, 5}, "Expected", 1)       # at tip − 40
    snap("2026-10-26T22:45:00+00:00", {1, 2, 3, 4, 6}, "Confirmed", 1)      # changed after the cutoff
    snap("2026-10-26T23:10:00+00:00", {1, 2, 3, 4, 6}, "Confirmed", 2)      # game on
    con.commit()
    q = sqlite3.connect(d / "q.sqlite")
    q.execute("CREATE TABLE quotes (gid TEXT, tip_utc TEXT)")
    q.execute("INSERT INTO quotes VALUES ('G', '2026-10-26T23:00:00Z')")
    q.commit()
    summ, rows = RP.report(d / "l.sqlite", d / "q.sqlite")
    r = next(x for x in rows if x["team"] == "AAA")
    assert r["status_at_cutoff"] == "Expected" and r["starters_right_at_cutoff"] == 4 and r["confirmed_min_before_tip"] == 15
