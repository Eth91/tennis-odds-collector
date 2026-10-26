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
