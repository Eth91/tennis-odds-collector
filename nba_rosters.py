"""NBA current-season state: who plays for whom NOW, and every appearance to project from.

WHY THIS EXISTS. nba_wowy.sqlite encodes the rosters of April 2026. Its pair lookup was
team-scoped, so every summer move broke it: on 2026-10-22, 12 of the 13 OUT players in
the news window matched zero pairs (Coby White's pairs are filed under CHI; he plays for
CHA). The cold-start tier needs the CURRENT rotation too. This module supplies both from
this season's cdn.nba.com box scores, joined to nba_gamelogs.sqlite on the NBA person id
— an exact id join, never a name join (reference_name_key_collapse: `a|brown`).

⚠️ MAC-ONLY. cdn.nba.com 403s plain HTTP clients everywhere and 403s the Oracle VM even
with browser impersonation (probed 2026-10-22). It answers curl_cffi impersonate="chrome"
from a residential IP. Same topology as stats.nba.com and DraftKings.

Final box scores never change, so each is fetched once and cached in
nba_season_boxes.json (gitignored). A game whose box fails to fetch is simply not cached
and is retried next run; it is never recorded as a game with no players.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE / "nba_gamelogs.sqlite"
CACHE = HERE / "nba_season_boxes.json"
SCHEDULE = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
BOX = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{}.json"
H = {"Referer": "https://www.nba.com/", "Accept": "application/json"}
POOL_DAYS = 400


class Blind(RuntimeError):
    """A source we cannot read. Raised, never swallowed into an empty result."""


def _get(url):
    from curl_cffi import requests as cr
    try:
        r = cr.get(url, impersonate="chrome", timeout=30, headers=H)
    except Exception as e:                                  # network, TLS, timeout
        raise Blind(f"{url.rsplit('/', 1)[-1]}: {type(e).__name__}") from e
    if r.status_code != 200:
        raise Blind(f"{url.rsplit('/', 1)[-1]}: HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise Blind(f"{url.rsplit('/', 1)[-1]}: not JSON") from e


def _minutes(iso):
    """'PT33M15.00S' -> 33.25"""
    m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", iso or "")
    if not m:
        return 0.0
    return float(m.group(1) or 0) + float(m.group(2) or 0) / 60.0


def schedule():
    """Regular-season games: [{gid, date_et, utc, status, home, away}]. Raises Blind."""
    s = _get(SCHEDULE)["leagueSchedule"]
    out = []
    for d in s["gameDates"]:
        for g in d["games"]:
            if not g["gameId"].startswith("002"):           # regular season only
                continue
            out.append({"gid": g["gameId"], "date_et": g["gameDateEst"][:10],
                        "utc": g["gameDateTimeUTC"], "status": g.get("gameStatus"),
                        "home": g["homeTeam"]["teamTricode"],
                        "away": g["awayTeam"]["teamTricode"]})
    return out


def season_boxes(sched):
    """{gid: {date, players: [...]}} for every FINAL game, fetching only uncached ones.
    Returns (boxes, n_failed). A failed fetch is retried next run, never cached empty."""
    try:
        boxes = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        boxes = {}
    failed = 0
    for g in sched:
        if g["status"] != 3 or g["gid"] in boxes:
            continue
        try:
            b = _get(BOX.format(g["gid"]))["game"]
        except Blind:
            failed += 1
            continue
        players = []
        for side in ("homeTeam", "awayTeam"):
            tri = b[side]["teamTricode"]
            for p in b[side]["players"]:
                s = p.get("statistics") or {}
                mn = _minutes(s.get("minutes"))
                if str(p.get("played")) != "1" or mn <= 0:
                    continue
                players.append({"pid": int(p["personId"]), "name": p["name"], "team": tri,
                                "pos": p.get("position") or "", "min": round(mn, 2),
                                "pts": s.get("points", 0), "reb": s.get("reboundsTotal", 0),
                                "ast": s.get("assists", 0),
                                "fg3m": s.get("threePointersMade", 0),
                                "fga": s.get("fieldGoalsAttempted", 0),
                                "fta": s.get("freeThrowsAttempted", 0),
                                "fg3a": s.get("threePointersAttempted", 0)})
        if not players:                                     # a final box with nobody in it
            failed += 1                                     # is a bad read, not a fact
            continue
        boxes[g["gid"]] = {"date": g["date_et"], "players": players}
    CACHE.write_text(json.dumps(boxes))
    return boxes, failed


def state(today_et, boxes):
    """Everything the engine projects from, merged and ordered by date.

    apps:  {pid: [(date, min, {pts, reb, ast, fg3m, pra}, team), ...]} — last season's game
           logs inside the 400-day pool PLUS this season's box scores. `team` is the team the
           player appeared FOR, so callers can scope to a franchise as the backtest did.
    team:  {pid: tricode of the player's most recent appearance} — CURRENT team.
    name:  {pid: name}
    """
    cut = (dt.date.fromisoformat(today_et) - dt.timedelta(days=POOL_DAYS)).isoformat()
    apps, team, name, last = defaultdict(list), {}, {}, {}
    con = sqlite3.connect(f"file:{LOGS}?mode=ro", uri=True)
    for date, tri, pid, nm, mn, p, r, a, t3 in con.execute(
            "SELECT date, team, player_id, player, min, pts, reb, ast, fg3m FROM logs "
            "WHERE date >= ? AND date < ? AND min > 0", (cut, today_et)):
        apps[pid].append((date, float(mn), {"pts": p, "reb": r, "ast": a, "fg3m": t3,
                                            "pra": p + r + a}, tri))
        name[pid] = nm
        if date >= last.get(pid, ""):
            last[pid], team[pid] = date, tri
    con.close()
    for gid, bx in boxes.items():
        if bx["date"] >= today_et:                          # strictly prior games only
            continue
        for q in bx["players"]:
            pid = q["pid"]
            apps[pid].append((bx["date"], q["min"], {
                "pts": q["pts"], "reb": q["reb"], "ast": q["ast"], "fg3m": q["fg3m"],
                "pra": q["pts"] + q["reb"] + q["ast"]}, q["team"]))
            name[pid] = q["name"]
            if bx["date"] >= last.get(pid, ""):
                last[pid], team[pid] = bx["date"], q["team"]
    for pid in apps:
        apps[pid].sort(key=lambda a: a[0])
    return apps, team, name


if __name__ == "__main__":
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).date().isoformat()
    sch = schedule()
    bx, nf = season_boxes(sch)
    apps, team, name = state(today, bx)
    cur = [p for p in apps if any(a[0] >= "2026-10-01" for a in apps[p])]
    print(f"schedule: {len(sch)} games, {sum(g['status'] == 3 for g in sch)} final | "
          f"boxes cached: {len(bx)} ({nf} failed this run) | players with apps: {len(apps)} | "
          f"appeared this season: {len(cur)} | teams: {len({team[p] for p in cur})}")
