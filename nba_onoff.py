#!/usr/bin/env python3
"""On/off court splits for the props page's WOWY tab: docs/onoff/{TEAM}.json, from each final game's cdn.nba.com
play-by-play (fetched once: a final game's play-by-play does not change; kept in nba_onoff.sqlite).

Who is on the court: the box score's starters (nba_matchup) open the game; each substitution moves one player in or
out. A later period's five are not in the feed: they are the players who show up in it (a shot, a foul, a sub out)
before any sub in of theirs, and where that finds fewer than five (a quiet period), the five who ended the last one.
Every player's minutes rebuilt this way match the box score's to a second in 1989 of 1990 games' player-games
(2026-27 to 2026-11-01; the one off by 2 minutes is a substitution missing from the feed).

File: {season, team, built_at, games, stats, gp: {pid: games on the court}, lineups: [[pids x5], seconds, team points,
       opponent points, [[stat x len(stats)] for each of the five, in the same order]]}
  a lineup  every five the team put on the court this season, its time and the box score of each of the five while
            it was on, summed over its games. The page sums a player's lineups with and without a teammate in them.

    python3 nba_onoff.py --out /home/ubuntu/tennis-odds-collector/docs/onoff
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DB = Path(__file__).resolve().parent / "nba_onoff.sqlite"
URL = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{}.json"
STATS = ("pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "tov", "stl", "blk", "oreb")
S = {k: i for i, k in enumerate(STATS)}
DDL = """CREATE TABLE IF NOT EXISTS games (gid TEXT PRIMARY KEY, season TEXT, date TEXT, ok INTEGER);
CREATE TABLE IF NOT EXISTS lineups (gid TEXT, team TEXT, lineup TEXT, secs REAL, pf INTEGER, pa INTEGER);
CREATE TABLE IF NOT EXISTS pstats (gid TEXT, team TEXT, lineup TEXT, pid INTEGER, """ + ", ".join(f"{k} INTEGER" for k in STATS) + """);
CREATE INDEX IF NOT EXISTS lineups_gid ON lineups (gid);
CREATE INDEX IF NOT EXISTS pstats_gid ON pstats (gid);
"""


class Unreadable(Exception):
    """A play-by-play the five on the court cannot be read from (a period without five a side)."""


def clock(period, iso):
    """(seconds into the game, the period's start, its end) for a period and its clock ('PT06M37.00S': time left)."""
    m = re.match(r"PT(\d+)M([\d.]+)S", iso or "")
    left = int(m.group(1)) * 60 + float(m.group(2)) if m else 0.0
    start, length = ((period - 1) * 720, 720) if period <= 4 else (2880 + (period - 5) * 300, 300)
    return start + length - left, start, start + length


def period_fives(actions, team_of, starters):
    """{(period, team): five pids} — period 1 from the box score's starters, a later one from who shows up in it before
    a sub in of his own (else the five who ended the period before). Raises Unreadable."""
    periods = sorted({a["period"] for a in actions if a.get("actionType") == "period" and a.get("subType") == "start"})
    teams = sorted(set(team_of.values()))
    out = {(1, t): [p for p in starters if team_of[p] == t] for t in teams}
    ended = {}
    for per in periods:
        acts = [a for a in actions if a["period"] == per]
        for t in teams:
            if per > 1:
                entered, five = set(), []
                for a in acts:
                    if a.get("actionType") == "substitution":
                        pid = a.get("personId")
                        if team_of.get(pid) != t:
                            continue
                        if a.get("subType") == "in":
                            entered.add(pid)
                        elif pid not in entered and pid not in five:
                            five.append(pid)
                        continue
                    if a.get("actionType") == "foul" and "technical" in (a.get("subType") or "").lower():
                        continue                                 # a technical can be called on the bench
                    for pid in a.get("personIdsFilter") or []:
                        if team_of.get(pid) == t and pid not in entered and pid not in five:
                            five.append(pid)
                five += [p for p in ended.get(t, []) if p not in five and p not in entered][:5 - len(five)]
                out[(per, t)] = five
            if len(out[(per, t)]) != 5:
                raise Unreadable(f"period {per} {t}: {len(out[(per, t)])} on the court")
            on = set(out[(per, t)])
            for a in acts:
                if a.get("actionType") == "substitution" and team_of.get(a.get("personId")) == t:
                    (on.add if a.get("subType") == "in" else on.discard)(a["personId"])
            ended[t] = sorted(on)
    return out


def parse(actions, team_of, starters):
    """A game's play-by-play -> {(team, five pids sorted): [seconds, team points, opponent points, {pid: [stat x STATS]}]}
    and {pid: seconds on the court}. team_of: {pid: team} of everyone in the box score; starters: the box score's
    starters. Raises Unreadable."""
    acts = sorted((a for a in actions if a.get("period") and a.get("actionType") != "game"),
                  key=lambda a: (a["period"], clock(a["period"], a.get("clock"))[0], a.get("orderNumber") or 0))
    if not any(a.get("actionType") == "period" and a.get("subType") == "start" for a in acts):
        raise Unreadable("no periods")
    teams = sorted(set(team_of.values()))
    if len(teams) != 2:
        raise Unreadable(f"{len(teams)} teams in the box score")
    fives = period_fives(acts, team_of, starters)
    other = {teams[0]: teams[-1], teams[-1]: teams[0]}
    out, secs = {}, {}
    on, cur, last, end = {}, None, 0.0, 0.0

    def unit(t):
        return out.setdefault((t, tuple(sorted(on[t]))), [0.0, 0, 0, {}])

    def tick(to):
        for t in teams:
            unit(t)[0] += to - last
            for p in on[t]:
                secs[p] = secs.get(p, 0.0) + to - last

    def add(pid, k, n=1):
        t = team_of.get(pid)
        if t:
            u = unit(t)
            u[3].setdefault(pid, [0] * len(STATS))[S[k]] += n

    for a in acts:
        per = a["period"]
        now, start, stop = clock(per, a.get("clock"))
        if per != cur:
            if cur is not None:
                tick(end)
            if any((per, t) not in fives for t in teams):
                raise Unreadable(f"period {per} has plays but no start")
            on = {t: set(fives[(per, t)]) for t in teams}
            cur, last, end = per, start, stop
        tick(now)
        last = now
        kind, pid = a.get("actionType"), a.get("personId")
        if kind == "substitution":
            t = team_of.get(pid)
            if t:
                (on[t].add if a.get("subType") == "in" else on[t].discard)(pid)
        elif kind in ("2pt", "3pt", "freethrow") and team_of.get(pid):
            made, pts = a.get("shotResult") == "Made", {"2pt": 2, "3pt": 3, "freethrow": 1}[kind]
            add(pid, "fta" if kind == "freethrow" else "fga")
            if kind == "3pt":
                add(pid, "fg3a")
            if made:
                add(pid, "pts", pts)
                if kind == "3pt":
                    add(pid, "fg3m")
                if a.get("assistPersonId"):
                    add(a["assistPersonId"], "ast")
                t = team_of[pid]
                unit(t)[1] += pts
                unit(other[t])[2] += pts
        elif kind == "rebound" and team_of.get(pid):
            add(pid, "reb")
            if a.get("subType") == "offensive":
                add(pid, "oreb")
        elif kind in ("turnover", "steal", "block") and team_of.get(pid):
            add(pid, {"turnover": "tov", "steal": "stl", "block": "blk"}[kind])
    if cur is not None:
        tick(end)
    return {k: v for k, v in out.items() if v[0] > 0 or v[1] or v[2] or v[3]}, secs


def connect(path):
    con = sqlite3.connect(path)
    con.executescript(DDL)
    return con


def store(con, gid, season, date, units):
    con.execute("DELETE FROM lineups WHERE gid = ?", (gid,))
    con.execute("DELETE FROM pstats WHERE gid = ?", (gid,))
    for (team, five), (s, pf, pa, ps) in units.items():
        key = ",".join(map(str, five))
        con.execute("INSERT INTO lineups VALUES (?,?,?,?,?,?)", (gid, team, key, round(s, 1), pf, pa))
        con.executemany(f"INSERT INTO pstats VALUES (?,?,?,?,{','.join('?' * len(STATS))})",
                        [(gid, team, key, pid, *v) for pid, v in ps.items()])
    con.execute("INSERT OR REPLACE INTO games VALUES (?,?,?,?)", (gid, season, date, 1 if units else 0))


def complete(actions, date, today):
    """The feed is to its end: its game end, or, from the day after (some feeds never get one), its last period's end."""
    if any(a.get("actionType") == "game" and a.get("subType") == "end" for a in actions):
        return True
    ends = [a["period"] for a in actions if a.get("actionType") == "period" and a.get("subType") == "end"]
    return date < today and bool(ends) and max(ends) >= 4 and max(ends) == max(a.get("period") or 0 for a in actions)


def fetch(con, mcon, season, get=None, workers=4, today=None):
    """Store the lineups of every final game of the season (nba_matchup's games) not stored yet. A feed not to its end
    yet is tried again next run; one the five cannot be read from is kept as unreadable (ok = 0), not tried again.
    today: the date (ET) a game must be before to go without its game end. Returns (stored, not yet, unreadable)."""
    today = today or dt.date.today().isoformat()
    have = {g for (g,) in con.execute("SELECT gid FROM games")}
    todo = [r for r in mcon.execute("SELECT gid, date FROM games WHERE season = ? AND home_pts IS NOT NULL ORDER BY date",
                                    (season,)) if r[0] not in have]
    if get is None:
        import nba_rosters as R
        get = lambda gid: R._get(URL.format(gid))["game"]["actions"]

    def one(r):
        try:
            return get(r[0])
        except Exception:                                                     # noqa: BLE001
            return None
    stored = waiting = bad = 0
    with ThreadPoolExecutor(workers) as ex:
        for (gid, date), acts in zip(todo, ex.map(one, todo)):
            if not acts or not complete(acts, date, today):
                waiting += 1                                                  # no feed yet, or not to its end yet
                continue
            box = mcon.execute("SELECT pid, team, starter FROM player_games WHERE gid = ?", (gid,)).fetchall()
            try:
                units, _ = parse(acts, {pid: t for pid, t, _ in box}, [pid for pid, _, s in box if s])
            except Unreadable:
                units, bad = {}, bad + 1
            store(con, gid, season, date, units)
            stored += 1
            if stored % 50 == 0:
                con.commit()
    con.commit()
    return stored, waiting, bad


def build(con, season):
    """{team: its file (see the module doc)} for the season."""
    games = {g for (g,) in con.execute("SELECT gid FROM games WHERE season = ? AND ok = 1", (season,))}
    marks = ",".join("?" * len(games)) or "NULL"
    units, n, gp = {}, {}, {}
    for gid, team, key, s, pf, pa in con.execute(f"SELECT gid, team, lineup, secs, pf, pa FROM lineups WHERE gid IN ({marks})",
                                                 list(games)):
        u = units.setdefault((team, key), [0.0, 0, 0, {}])
        u[0] += s
        u[1] += pf
        u[2] += pa
        n.setdefault(team, set()).add(gid)
        for p in key.split(","):
            gp.setdefault((team, int(p)), set()).add(gid)
    for team, key, pid, *v in con.execute(f"SELECT team, lineup, pid, {', '.join(STATS)} FROM pstats WHERE gid IN ({marks})",
                                          list(games)):
        tot = units[(team, key)][3].setdefault(pid, [0] * len(STATS))
        for i, x in enumerate(v):
            tot[i] += x or 0
    built = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    out = {}
    for (team, key), (s, pf, pa, ps) in sorted(units.items(), key=lambda kv: -kv[1][0]):
        five = [int(p) for p in key.split(",")]
        if len(five) != 5:
            continue
        doc = out.setdefault(team, {"season": season, "team": team, "built_at": built, "games": len(n[team]),
                                    "stats": list(STATS), "gp": {str(p): len(g) for (t, p), g in gp.items() if t == team},
                                    "lineups": []})
        doc["lineups"].append([five, round(s), pf, pa, [ps.get(p, [0] * len(STATS)) for p in five]])
    return out


def write(out, docs):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for team, doc in docs.items():
        tmp = out / f".{team}.json.tmp"
        tmp.write_text(json.dumps(doc, separators=(",", ":")))
        os.replace(tmp, out / f"{team}.json")


def main():
    import nba_matchup as MU
    import nba_research as R
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/onoff)")
    a = ap.parse_args()
    con = connect(DB)
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    season = R.season_of(dt.datetime.now(R.ET).date().isoformat())
    stored, waiting, bad = fetch(con, mcon, season, today=dt.datetime.now(R.ET).date().isoformat())
    docs = build(con, season)
    write(a.out, docs)
    print(f"nba_onoff: {stored} games stored ({bad} unreadable), {waiting} not yet · {season} · {len(docs)} teams -> {a.out}")


if __name__ == "__main__":
    main()
