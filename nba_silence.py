"""The silence check (NBA_SPEED_PREREG.md amendment 21) — one definition, used by nba_news_watch.news_outs
and nba_board. No dependencies beyond the standard library, so the board can load it by path.

A news absence for player P (team T, game date D, first seen t) is SILENCED when the first official
report that is published ON D (ET, by its mark), at least GRACE_MIN after t, and lists at least one
player of T for D has no row for P. 2026-10-24: RotoBaller's "Jalen Green doubtful" (21:37Z) was wrong
and every report from 21:45Z listed PHX without him. Silenced at 22:45Z, 3 h 15 min before tip.
The grace exists because the engine's edge is news BEFORE the report: real news reached the report a
median 28 min later (38 items; none silenced at any grace from 15 to 120 min).
"""
from __future__ import annotations

import datetime as dt

GRACE_MIN = 60


def _t(s):
    t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def silenced(con, pid, team, game_date, first, grace_min=GRACE_MIN):
    """The published_at of the report that silences this news absence, or None. `con` is the news store
    (reports + snapshots)."""
    if not (pid and team and game_date and first):
        return None
    t0 = _t(first) + dt.timedelta(minutes=grace_min)
    for mark, pub in con.execute("SELECT mark, published_at FROM reports WHERE substr(mark, 1, 10) = ? "
                                 "ORDER BY published_at", (game_date,)):
        if _t(pub) < t0:
            continue
        if not con.execute("SELECT 1 FROM snapshots WHERE mark=? AND game_date=? AND team=? AND pid IS NOT NULL "
                           "LIMIT 1", (mark, game_date, team)).fetchone():
            continue                                   # the team is not on this report yet
        listed = con.execute("SELECT 1 FROM snapshots WHERE mark=? AND game_date=? AND pid=? LIMIT 1",
                             (mark, game_date, pid)).fetchone()
        return None if listed else pub
    return None
