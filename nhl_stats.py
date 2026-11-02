#!/usr/bin/env python3
"""NHL game logs for Pickz: the NHL's per-game stats reports -> nhl_stats.sqlite (read by nhl_research).

One row per player per game, this season and last (regular season and playoffs), with everything a prop is graded on
and the usage behind it:
    logs        skaters: goals, assists, points, shots on goal, blocked shots, power-play points, hits, shot attempts,
                time on ice (all, even strength, power play, short-handed), shifts, faceoffs; goalies: saves, shots and
                goals against, a start. Each row carries its game's context: home, his team's final margin, days off
                before it (0 = the second of a back-to-back), his share of his team's shots and of its power-play time.
                Columns named as the NBA side's where they mean the same: "min" is time on ice in minutes, "starter" a
                goalie's start (None for a skater).
    players     name, team (his current roster, else his last game's), position (C L R D G), headshot, jersey
    names       everyone in the logs, gone or not
    team_games  per team per game: goals for and against, shots for and against, power-play chances and goals, time
                on the power play, hits, blocks, shot attempts
    meta        when it was built, the last game date, and which past seasons are complete

The reports (api.nhle.com/stats/rest, isGame=true) return a season's player-games in pages of 10,000 rows, read a page at
a time (the VM has 1 GB). A past season is read once and kept; this season is read again on every run (hourly).

    python3 nhl_stats.py              # this season and last
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

import nhl_common as C

HERE = Path(__file__).resolve().parent
DB = Path(os.environ.get("NHL_STATS_DB", HERE / "nhl_stats.sqlite"))
LOG_COLS = ("date", "gid", "team", "opp", "home", "starter", "min", "goals", "assists", "points", "shots", "blocks",
            "saves", "ppp", "margin", "rest", "pp_min", "sh_min", "ev_min", "shifts", "attempts", "missed", "blocked",
            "hits", "pim", "ppg", "shg", "pm", "fow", "fot", "gwg", "sa", "ga", "shot_share", "pp_share")
TEXT = {"date", "gid", "team", "opp"}
TEAM_COLS = ("season", "gid", "date", "team", "opp", "home", "gf", "ga", "sf", "sa", "pp_opp", "ppg", "pp_sec", "hits",
             "blocks", "attempts", "pim")
DDL = f"""
CREATE TABLE IF NOT EXISTS logs (season INTEGER, pid INTEGER, pos TEXT,
    {", ".join(c + (" TEXT" if c in TEXT else " REAL") for c in LOG_COLS)}, PRIMARY KEY (pid, gid));
CREATE INDEX IF NOT EXISTS logs_season ON logs (season, team);
CREATE TABLE IF NOT EXISTS players (pid INTEGER PRIMARY KEY, name TEXT, team TEXT, pos TEXT, headshot TEXT, jersey TEXT,
    shoots TEXT);
CREATE TABLE IF NOT EXISTS names (pid INTEGER PRIMARY KEY, name TEXT, pos TEXT);
CREATE TABLE IF NOT EXISTS team_games (season INTEGER, gid TEXT, date TEXT, team TEXT, opp TEXT, home INTEGER, gf REAL,
    ga REAL, sf REAL, sa REAL, pp_opp REAL, ppg REAL, pp_sec REAL, hits REAL, blocks REAL, attempts REAL, pim REAL,
    PRIMARY KEY (gid, team));
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""
WINDOW_DAYS = 15
REFETCH_DAYS = 3             # this season's last 3 days are read again on every run (the NHL corrects its stats)


def spans(first, last):
    """[(from, to)): WINDOW_DAYS at a time from the first date to past the last. A report answers at most 10,000 rows
    (and only with limit=-1); a fortnight of games is about 4,000. A window is read, written and dropped before the
    next (the VM has 1 GB)."""
    d, last, out = dt.date.fromisoformat(first), dt.date.fromisoformat(last), []
    while d <= last:
        out.append((d.isoformat(), (d + dt.timedelta(days=WINDOW_DAYS)).isoformat()))
        d += dt.timedelta(days=WINDOW_DAYS)
    return out


def report(path, cayenne, span, get=None):
    """An NHL stats report's per-game rows (api.nhle.com/stats/rest/en/{path}, isGame) in a date window."""
    cay = f'{cayenne} and gameDate>="{span[0]}" and gameDate<"{span[1]}"'
    return ((get or C.fetch)(f"{C.REST}/{path}?isAggregate=false&isGame=true&start=0&limit=-1&cayenneExp="
                             + urllib.parse.quote(cay)).get("data") or [])


def _min(sec):
    return None if sec is None else round(float(sec) / 60, 2)


def window_rows(season, sched, span, get=None):
    """(player rows {(gid, pid): {col: value, "pos", "name"}}, team rows {(gid, team): {col: value}}) for a season's
    games in a date window, from its reports. Only games of the schedule that are final count."""
    games = {g["gid"]: g for g in sched if g["state"] == "final" and span[0] <= g["date"] < span[1]}
    P, T = {}, {}
    if not games:
        return P, T
    for gt in (2, 3):
        cay = f"seasonId={C.season_id(season)} and gameTypeId={gt}"
        pages = lambda path, cay_, get_: [report(path, cay_, span, get_)]
        # skaters: the box score
        for page in pages("skater/summary", cay, get):
            for r in page:
                gid = str(r["gameId"])
                if gid not in games:
                    continue
                P[(gid, int(r["playerId"]))] = {
                    "team": C.team(r.get("teamAbbrev")), "opp": C.team(r.get("opponentTeamAbbrev")),
                    "home": 1 if r.get("homeRoad") == "H" else 0, "pos": r.get("positionCode") or "",
                    "name": r.get("skaterFullName") or "", "min": _min(r.get("timeOnIcePerGame")),
                    "goals": r.get("goals"), "assists": r.get("assists"), "points": r.get("points"),
                    "shots": r.get("shots"), "ppp": r.get("ppPoints"), "ppg": r.get("ppGoals"), "shg": r.get("shGoals"),
                    "pm": r.get("plusMinus"), "pim": r.get("penaltyMinutes"), "gwg": r.get("gameWinningGoals")}
        for kind, cols in (("realtime", {"blocks": "blockedShots", "hits": "hits", "attempts": "totalShotAttempts",
                                         "missed": "missedShots", "blocked": "shotAttemptsBlocked"}),
                           ("timeonice", {"pp_min": "ppTimeOnIce", "sh_min": "shTimeOnIce", "ev_min": "evTimeOnIce",
                                          "shifts": "shifts"}),
                           ("faceoffwins", {"fow": "totalFaceoffWins", "fot": "totalFaceoffs"})):
            for page in pages(f"skater/{kind}", cay, get):
                for r in page:
                    e = P.get((str(r["gameId"]), int(r["playerId"])))
                    if e is None:
                        continue
                    for c, k in cols.items():
                        v = r.get(k)
                        e[c] = _min(v) if c.endswith("_min") else v
        # goalies
        for page in pages("goalie/summary", cay, get):
            for r in page:
                gid = str(r["gameId"])
                if gid not in games:
                    continue
                P[(gid, int(r["playerId"]))] = {
                    "team": C.team(r.get("teamAbbrev")), "opp": C.team(r.get("opponentTeamAbbrev")),
                    "home": 1 if r.get("homeRoad") == "H" else 0, "pos": "G", "name": r.get("goalieFullName") or "",
                    "min": _min(r.get("timeOnIce")), "starter": 1 if r.get("gamesStarted") else 0, "saves": r.get("saves"),
                    "sa": r.get("shotsAgainst"), "ga": r.get("goalsAgainst"), "goals": r.get("goals"),
                    "assists": r.get("assists"), "points": r.get("points"), "pim": r.get("penaltyMinutes")}
        # teams
        for kind, cols in (("summary", {"gf": "goalsFor", "ga": "goalsAgainst", "sf": "shotsForPerGame",
                                        "sa": "shotsAgainstPerGame"}),
                           ("powerplay", {"pp_opp": "ppOpportunities", "ppg": "powerPlayGoalsFor", "pp_sec": "ppTimeOnIcePerGame"}),
                           ("realtime", {"hits": "hits", "blocks": "blockedShots", "attempts": "totalShotAttempts"}),
                           ("penalties", {"pim": "penaltyMinutes"})):
            for page in pages(f"team/{kind}", cay, get):
                for r in page:
                    gid = str(r["gameId"])
                    t = C.BY_ID.get(r.get("teamId"))
                    if gid not in games or not t:
                        continue
                    e = T.setdefault((gid, t), {"season": int(season), "gid": gid, "date": games[gid]["date"], "team": t,
                                                "opp": C.team(r.get("opponentTeamAbbrev")),
                                                "home": 1 if r.get("homeRoad") == "H" else 0})
                    for c, k in cols.items():
                        e[c] = r.get(k)
    return P, T


def rest_days(sched):
    """{(gid, team): days off before the game} (None for a team's first game of the season)."""
    by = defaultdict(list)
    for g in sched:
        if g["state"] == "postponed":
            continue
        for t in (g["home"], g["away"]):
            by[t].append((g["date"], g["gid"]))
    out = {}
    for t, gl in by.items():
        gl.sort()
        for i, (d, gid) in enumerate(gl):
            out[(gid, t)] = (dt.date.fromisoformat(d) - dt.date.fromisoformat(gl[i - 1][0])).days - 1 if i else None
    return out


def log_rows(season, P, T, sched):
    """The logs table's rows for a season: each player-game in LOG_COLS order, with the game's context and his shares."""
    games = {g["gid"]: g for g in sched}
    rest = rest_days(sched)
    team_sog = defaultdict(float)
    for (gid, _pid), e in P.items():
        if e.get("pos") != "G" and e.get("shots") is not None:
            team_sog[(gid, e["team"])] += e["shots"]
    out = []
    for (gid, pid), e in P.items():
        g, t = games.get(gid), e.get("team")
        if not g or t not in (g["home"], g["away"]):
            continue
        mine, theirs = (g["home_score"], g["away_score"]) if t == g["home"] else (g["away_score"], g["home_score"])
        e = dict(e, date=g["date"], gid=gid, margin=(mine - theirs) if mine is not None and theirs is not None else None,
                 rest=rest.get((gid, t)))
        tsog, tpp = team_sog.get((gid, t)), (T.get((gid, t)) or {}).get("pp_sec")
        if e.get("pos") != "G":
            e["shot_share"] = round(100 * e["shots"] / tsog, 1) if tsog and e.get("shots") is not None else None
            e["pp_share"] = (round(min(100.0, 100 * e["pp_min"] * 60 / tpp), 1) if tpp and e.get("pp_min") is not None
                             else 0.0 if tpp == 0 and e.get("pp_min") is not None else None)
        out.append((int(season), pid, e.get("pos") or "", *[e.get(c) for c in LOG_COLS]))
    return out


def build(seasons=None, db=DB, now=None, get=None, sched=None, roster=None):
    """Refresh the store: this season always, a past season only until it is marked complete."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cur = C.season_of(now.astimezone(C.ET).date())
    seasons = seasons or (cur - 1, cur)
    con = sqlite3.connect(db, timeout=60)
    con.executescript(DDL)
    meta = {k: v for k, v in con.execute("SELECT k, v FROM meta")}
    done = set(json.loads(meta.get("complete") or "[]"))
    t0, notes = time.time(), []
    for s in seasons:
        if s in done and s != cur:
            notes.append(f"{s}: kept")
            continue
        sc = sched.get(s) if isinstance(sched, dict) else C.schedule(s, max_age=1800, get=get)
        # a season with games stored is read again from REFETCH_DAYS before its last stored game, the rest kept
        have = con.execute("SELECT MAX(date) FROM logs WHERE season=?", (s,)).fetchone()[0]
        since = (dt.date.fromisoformat(have) - dt.timedelta(days=REFETCH_DAYS)).isoformat() if have else None
        fin = [g["date"] for g in sc if g["state"] == "final" and (since is None or g["date"] >= since)]
        if s != cur and all(g["state"] in ("final", "postponed") for g in sc) and have:
            done.add(s)
        if not fin:
            notes.append(f"{s}: nothing new" if have else f"{s}: no games")
            continue
        cut, n, nt = since or "0000", 0, 0
        con.execute("DELETE FROM logs WHERE season=? AND date>=?", (s, cut))
        con.execute("DELETE FROM team_games WHERE season=? AND date>=?", (s, cut))
        for span in spans(min(fin), max(fin)):
            P, T = window_rows(s, sc, span, get)
            rows = log_rows(s, P, T, sc)
            con.executemany(f"INSERT OR REPLACE INTO logs VALUES ({','.join('?' * (3 + len(LOG_COLS)))})", rows)
            con.executemany(f"INSERT OR REPLACE INTO team_games VALUES ({','.join('?' * len(TEAM_COLS))})",
                            [tuple(e.get(c) for c in TEAM_COLS) for e in T.values()])
            con.executemany("INSERT OR REPLACE INTO names VALUES (?,?,?)",
                            {(pid, e.get("name"), e.get("pos")) for (_g, pid), e in P.items() if e.get("name")})
            n, nt = n + len(rows), nt + len(T)
            del P, T, rows
        notes.append(f"{s}: {n:,} player-games, {nt:,} team-games" + (f" from {since}" if since else ""))
    # players: the current rosters, and for anyone in the logs not on one, his last game's team
    ros = roster if roster is not None else C.rosters()
    last = {}
    for pid, pos, team, nm in con.execute("SELECT l.pid, l.pos, l.team, n.name FROM logs l LEFT JOIN names n ON n.pid = l.pid "
                                          "ORDER BY l.date"):
        last[pid] = (team, pos, nm)
    con.execute("DELETE FROM players")
    rows = []
    for pid in set(ros) | set(last):
        r = ros.get(pid)
        if r:
            rows.append((pid, r["name"], r["team"], r["pos"], r.get("headshot"), str(r.get("jersey") or "") or None, r.get("shoots")))
        else:
            t, pos, nm = last[pid]
            rows.append((pid, nm, t, pos, C.headshot(cur, t, pid), None, None))
    con.executemany("INSERT OR REPLACE INTO players VALUES (?,?,?,?,?,?,?)", rows)
    through = con.execute("SELECT MAX(date) FROM logs").fetchone()[0]
    stamp = now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)",
                    [("meta", json.dumps({"built_at": stamp, "through": through})), ("complete", json.dumps(sorted(done)))])
    con.commit()
    con.close()
    print(f"[{stamp}] nhl_stats -> {Path(db).name}: " + "; ".join(notes) + f"; players {len(rows):,}; through {through}; "
          f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="*")
    a = ap.parse_args()
    build(tuple(a.seasons) if a.seasons else None)
