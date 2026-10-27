#!/usr/bin/env python3
"""Every player's page, prop or not: docs/player/{pid}.json — his game logs for this season and last in the props
page's LOG_COLS (nba_research.game_logs, the same rows a prop's page charts) — and docs/player/index.json, the list
the page searches: [pid, name, team, position] for everyone on a roster now (the player index) who has a game.

    python3 nba_players.py --out /home/ubuntu/tennis-odds-collector/docs/player
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

import nba_research as R


def _write(path, doc):
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")))
    os.replace(tmp, path)


def build(mcon, out, idx, season, trk=None):
    """Write one file per player with games, and the index. Returns the number of players written."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pids = [int(k) for k in idx]
    logs = R.game_logs(mcon, pids, (R.prev_season(season), season), trk)
    rows = []
    for pid in pids:
        lg = logs.get(pid)
        if not lg:
            continue
        team, name, pos = idx[str(pid)][:3]
        _write(out / f"{pid}.json", {"pid": pid, "name": name, "team": team, "pos": pos or "", "logs": lg})
        rows.append([pid, name, team, pos or ""])
    _write(out / "index.json", {"season": season, "log_cols": list(R.LOG_COLS),
                                "players": sorted(rows, key=lambda r: r[1])})
    return len(rows)


def main():
    import nba_matchup as MU
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/player)")
    a = ap.parse_args()
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    idx = json.loads(R.INDEX.read_text()).get("players", {})
    season = R.season_of(dt.datetime.now(R.ET).date().isoformat())
    n = build(mcon, a.out, idx, season, R._ro(R.TRACKING))
    print(f"nba_players: {n} players -> {a.out}")


if __name__ == "__main__":
    main()
