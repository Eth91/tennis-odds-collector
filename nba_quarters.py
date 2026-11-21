#!/usr/bin/env python3
"""Each player's minutes and box score by quarter, for the props page's quarter filter (1Q / 2Q / 3Q / 4Q):
docs/quarters/{pid}.json, from each final game's cdn.nba.com play-by-play (fetched once: a final game's play-by-play does
not change; kept in nba_quarters.sqlite). Last season and this one, as the page's game logs.

Who is on the court comes from nba_onoff.parse (the box score's starters open the game, each substitution moves one
player, a later period's five are the players who show up in it before a sub in of their own); each second on the court
and each stat goes to the period it happened in. A player's game is kept only where his periods add up to his box score
(nba_matchup): minutes within half a minute, points, rebounds, assists and threes exactly. One that doesn't is kept out
(checks.ok = 0, and why), and the page leaves that game out of a quarter's view.

File: {pid, cols: COLS, games: {gid: [[q1 x COLS], [q2 ...], [q3 ...], [q4 ...]]}}   min to a tenth; overtime is in no
      quarter. Written only when it changes.

    python3 nba_quarters.py --out /home/ubuntu/tennis-odds-collector/docs/quarters
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nba_onoff as O

DB = Path(__file__).resolve().parent / "nba_quarters.sqlite"
COLS = ("min", "pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta")      # the page's game-log columns that have a quarter
CHECK = ("pts", "reb", "ast", "fg3m")                                  # must add up to the box score exactly
MIN_TOL = 0.5                                                          # minutes: within half a minute of the box score
CHUNK = 40                                                             # feeds in memory at once, at most
GIVE_UP_DAYS = 3                                                       # a game this old with no full feed is let go
DDL = """CREATE TABLE IF NOT EXISTS games (gid TEXT PRIMARY KEY, season TEXT, date TEXT, ok INTEGER, why TEXT);
CREATE TABLE IF NOT EXISTS quarters (gid TEXT, pid INTEGER, team TEXT, period INTEGER, secs REAL, """ + \
    ", ".join(f"{k} INTEGER" for k in O.STATS) + """, PRIMARY KEY (gid, pid, period));
CREATE TABLE IF NOT EXISTS checks (gid TEXT, pid INTEGER, ok INTEGER, why TEXT, PRIMARY KEY (gid, pid));
CREATE INDEX IF NOT EXISTS quarters_pid ON quarters (pid);
"""


def connect(path):
    con = sqlite3.connect(path)
    con.executescript(DDL)
    return con


def split(actions, box):
    """A game's play-by-play and its box score [(pid, team, starter, min, pts, reb, ast, fg3m)] ->
    ({(pid, period): [seconds, stat x nba_onoff.STATS]}, {pid: (ok, why)}). Raises nba_onoff.Unreadable."""
    periods = {}
    O.parse(actions, {r[0]: r[1] for r in box}, [r[0] for r in box if r[2]], periods)
    checks = {}
    for pid, _, _, mn, *st in box:
        mine = [v for (p, _), v in periods.items() if p == pid]
        secs = sum(v[0] for v in mine)
        got = {k: sum(v[1 + O.S[k]] for v in mine) for k in CHECK}
        if not mine and not mn:
            continue                                                  # did not play
        off = [f"min {secs / 60:.1f} v {mn or 0:.1f}"] if abs(secs / 60 - (mn or 0)) > MIN_TOL else []
        off += [f"{k} {got[k]} v {int(b or 0)}" for k, b in zip(CHECK, st) if got[k] != int(b or 0)]
        checks[pid] = (0 if off else 1, ", ".join(off) or None)
    return periods, checks


def store(con, gid, season, date, team_of, periods, checks, ok, why=None):
    con.execute("DELETE FROM quarters WHERE gid = ?", (gid,))
    con.execute("DELETE FROM checks WHERE gid = ?", (gid,))
    con.executemany(f"INSERT INTO quarters VALUES (?,?,?,?,?,{','.join('?' * len(O.STATS))})",
                    [(gid, pid, team_of.get(pid), per, round(v[0], 1), *v[1:]) for (pid, per), v in sorted(periods.items())])
    con.executemany("INSERT INTO checks VALUES (?,?,?,?)", [(gid, pid, k, w) for pid, (k, w) in checks.items()])
    con.execute("INSERT OR REPLACE INTO games VALUES (?,?,?,?,?)", (gid, season, date, ok, why))


def fetch(con, mcon, seasons, get=None, workers=4, today=None):
    """Store every final game of the seasons (nba_matchup's) not stored yet. A feed not to its end yet is tried again
    next run, unless the game is GIVE_UP_DAYS old (then kept as ok = 0, no feed). One the five cannot be read from is
    kept as ok = 0, not tried again. Returns (stored, not yet, no good)."""
    today = today or dt.date.today().isoformat()
    cut = (dt.date.fromisoformat(today) - dt.timedelta(days=GIVE_UP_DAYS)).isoformat()
    have = {g for (g,) in con.execute("SELECT gid FROM games")}
    marks = ",".join("?" * len(seasons))
    todo = [r for r in mcon.execute(f"SELECT gid, season, date FROM games WHERE season IN ({marks}) AND home_pts IS NOT NULL "
                                    "ORDER BY date", list(seasons)) if r[0] not in have]
    if get is None:
        import nba_rosters as R
        get = lambda gid: R._get(O.URL.format(gid))["game"]["actions"]

    def one(r):
        try:
            return get(r[0])
        except Exception:                                                     # noqa: BLE001
            return None
    stored = waiting = bad = 0
    with ThreadPoolExecutor(workers) as ex:
        for i in range(0, len(todo), CHUNK):
            part = todo[i:i + CHUNK]
            for (gid, season, date), acts in zip(part, ex.map(one, part)):
                box = mcon.execute("SELECT pid, team, starter, min, pts, reb, ast, fg3m FROM player_games WHERE gid = ?",
                                   (gid,)).fetchall()
                team_of = {r[0]: r[1] for r in box}
                if not acts or not O.complete(acts, date, today):
                    if date >= cut:
                        waiting += 1                                          # no feed yet, or not to its end yet
                        continue
                    store(con, gid, season, date, team_of, {}, {}, 0, "no full feed")
                    stored, bad = stored + 1, bad + 1
                    continue
                try:
                    periods, checks = split(acts, box)
                    store(con, gid, season, date, team_of, periods, checks, 1)
                except O.Unreadable as e:
                    store(con, gid, season, date, team_of, {}, {}, 0, str(e))
                    bad += 1
                stored += 1
            con.commit()
    return stored, waiting, bad


def build(con, seasons):
    """{pid: his file (see the module doc)}: his games in the seasons that add up to the box score."""
    marks = ",".join("?" * len(seasons))
    good = {(g, p) for g, p in con.execute(
        f"SELECT c.gid, c.pid FROM checks c JOIN games g ON g.gid = c.gid WHERE g.ok = 1 AND c.ok = 1 AND g.season IN ({marks})",
        list(seasons))}
    out = {}
    for gid, pid, per, secs, *st in con.execute(
            f"SELECT q.gid, q.pid, q.period, q.secs, {', '.join('q.' + k for k in O.STATS)} FROM quarters q "
            f"JOIN games g ON g.gid = q.gid WHERE g.season IN ({marks}) AND q.period <= 4 ORDER BY g.date, q.gid",
            list(seasons)):
        if (gid, pid) not in good:
            continue
        g = out.setdefault(pid, {}).setdefault(gid, [[0.0] + [0] * (len(COLS) - 1) for _ in range(4)])
        vals = dict(zip(O.STATS, st))
        g[per - 1] = [round(secs / 60, 1)] + [vals[k] for k in COLS[1:]]
    for (gid, pid) in good:                                    # on the court only in overtime: four empty quarters
        out.setdefault(pid, {}).setdefault(gid, [[0.0] + [0] * (len(COLS) - 1) for _ in range(4)])
    return {pid: {"pid": pid, "cols": list(COLS), "games": games} for pid, games in out.items()}


def write(out, docs):
    """Writes each file that changed; returns how many."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for pid, doc in docs.items():
        path, body = out / f"{pid}.json", json.dumps(doc, separators=(",", ":"), sort_keys=True)
        try:
            if path.read_text() == body:
                continue
        except OSError:
            pass
        tmp = out / f".{pid}.json.tmp"
        tmp.write_text(body)
        os.replace(tmp, path)
        n += 1
    return n


def main():
    import nba_matchup as MU
    import nba_research as R
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/quarters)")
    a = ap.parse_args()
    con = connect(DB)
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    today = dt.datetime.now(R.ET).date().isoformat()
    this = R.season_of(today)
    last = f"{int(this[:4]) - 1}-{this[2:4]}"
    seasons = (last, this)
    stored, waiting, bad = fetch(con, mcon, seasons, today=today)
    docs = build(con, seasons)
    n = write(a.out, docs)
    off = con.execute("SELECT COUNT(*), SUM(ok = 0) FROM checks").fetchone()
    print(f"nba_quarters: {stored} games stored ({bad} no good), {waiting} not yet · {', '.join(seasons)} · "
          f"{len(docs)} players, {n} files written · player-games off the box score {off[1] or 0} of {off[0]} -> {a.out}")


if __name__ == "__main__":
    main()
