"""NBA_SPEED_PREREG.md amendment 34: last night's box scores as soon as NBA.com posts them.

Cron runs this every 15 minutes. It stores this season's newly final games (`nba_matchup.fetch`: only games marked
final) without a play-type snapshot, which stays with the daily `nba_matchup.py --current`. The props page's own
jobs (box scores, matchup page, player pages, every 20 minutes under their own locks) pick the new finals up.

    python3 nba_finals.py
"""
from __future__ import annotations

import datetime as dt

import nba_matchup as MU


def run(con=None, schedule=None, get=None):
    """Store new finals. Returns (stored, not final or failed)."""
    if schedule is None:
        import nba_rosters as R
        schedule = R.schedule
    return MU.fetch([g["gid"] for g in schedule() if g["status"] == 3], con, get=get)


if __name__ == "__main__":
    print(f"nba_finals {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M}Z: stored %d, not final or failed %d" % run())
