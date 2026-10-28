"""NBA_SPEED_PREREG.md amendment 34: last night's box scores as soon as NBA.com posts them.

Cron runs this every 15 minutes. It stores this season's newly final games (`nba_matchup.fetch`: only games marked
final) without a play-type snapshot, which stays with the daily `nba_matchup.py --current`. Only when it stored a
new final does it rebuild the props page's box scores, matchup page and player pages, with the same commands as
their daily runs.

    python3 nba_finals.py
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import nba_matchup as MU

HERE = Path(__file__).resolve().parent
DOCS = Path("/home/ubuntu/tennis-odds-collector/docs")
LOGS = Path("/home/ubuntu/nba-logs")
PAGES = (("boxscore", ["nba_boxscore.py", "--out", str(DOCS / "box")]),             # in their daily order:
         ("vs", ["nba_vs.py", "--box", str(DOCS / "box"), "--out", str(DOCS / "vs")]),  # vs reads the box files
         ("players", ["nba_players.py", "--out", str(DOCS / "player")]))


def build(name, args):
    """One page builder, nice'd, appending to its daily log. Returns its exit code."""
    with open(LOGS / f"{name}.log", "a") as log:
        return subprocess.run(["nice", sys.executable, *args], cwd=HERE, stdout=log, stderr=subprocess.STDOUT).returncode


def run(con=None, schedule=None, get=None, builder=build):
    """Store new finals, then rebuild the pages if any. Returns (stored, not final or failed, [(page, exit code)])."""
    if schedule is None:
        import nba_rosters as R
        schedule = R.schedule
    stored, missed = MU.fetch([g["gid"] for g in schedule() if g["status"] == 3], con, get=get)
    return stored, missed, [(name, builder(name, args)) for name, args in PAGES] if stored else []


if __name__ == "__main__":
    stored, missed, built = run()
    print(f"nba_finals {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M}Z: stored {stored}, not final or failed {missed}"
          + ("".join(f" · {n} {'ok' if rc == 0 else f'exit {rc}'}" for n, rc in built)))
    sys.exit(1 if any(rc for _n, rc in built) else 0)
