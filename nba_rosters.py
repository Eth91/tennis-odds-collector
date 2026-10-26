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
                        "status_text": g.get("gameStatusText") or "",   # "PPD" marks a postponement
                        "home": g["homeTeam"]["teamTricode"],
                        "away": g["awayTeam"]["teamTricode"],
                        # nicknames ("Knicks", "Trail Blazers", "76ers") are the only part of a
                        # team's name that FanDuel ("New York Knicks") and DraftKings ("NY Knicks")
                        # spell the same way; nba_lines matches book events on them
                        "home_nick": g["homeTeam"].get("teamName") or "",
                        "away_nick": g["awayTeam"].get("teamName") or ""})
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


INDEX = ("https://stats.nba.com/stats/playerindex?LeagueID=00&Season={season}"
         "&Historical=0&Active=1")
INDEX_CACHE = HERE / "nba_player_index.json"
INDEX_TTL_H, INDEX_STALE_OK_H = 6.0, 72.0
STATS_H = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com",
           "Accept": "application/json", "x-nba-stats-origin": "stats",
           "x-nba-stats-token": "true"}


def player_index(today_et):
    """({pid: (tricode, name, position)}, note) — the league's CURRENT active rosters.

    WHY. "Current team" from a player's most recent appearance is wrong for every summer
    move until that player plays: on 2026-10-22 it put DeRozan on SAC (he is on DEN),
    Bagley on DAL (DEN), Watson on DEN (CLE), and could not place any rookie. The index
    is authoritative and keyed by the same NBA person id as the game logs and box scores.
    stats.nba.com is Mac-only. Cached INDEX_TTL_H; on a failed refresh a cache younger than
    INDEX_STALE_OK_H is used and SAID so; older than that raises Blind.
    """
    from curl_cffi import requests as cr
    now = dt.datetime.now(dt.timezone.utc)
    try:
        c = json.loads(INDEX_CACHE.read_text())
        age_h = (now - dt.datetime.fromisoformat(c["fetched_at"])).total_seconds() / 3600
    except (OSError, ValueError, KeyError):
        c, age_h = None, None
    if c and age_h < INDEX_TTL_H:
        return {int(k): tuple(v) for k, v in c["players"].items()}, ""
    y = int(today_et[:4]) if int(today_et[5:7]) >= 8 else int(today_et[:4]) - 1
    season = f"{y}-{(y + 1) % 100:02d}"
    try:
        r = cr.get(INDEX.format(season=season), impersonate="chrome", timeout=60,
                   headers=STATS_H)
        if r.status_code != 200:
            raise Blind(f"playerindex: HTTP {r.status_code}")
        rs = r.json()["resultSets"][0]
        ix = {h: i for i, h in enumerate(rs["headers"])}
        players = {int(x[ix["PERSON_ID"]]): (x[ix["TEAM_ABBREVIATION"]],
                                             f"{x[ix['PLAYER_FIRST_NAME']]} "
                                             f"{x[ix['PLAYER_LAST_NAME']]}".strip(),
                                             x[ix["POSITION"]] or "")
                   for x in rs["rowSet"] if x[ix["TEAM_ABBREVIATION"]]}
        if len(players) < 300:                       # a real league has ~500; a stub is a bad read
            raise Blind(f"playerindex: only {len(players)} rostered players")
    except Blind:
        raise_ = not (c and age_h is not None and age_h < INDEX_STALE_OK_H)
        if raise_:
            raise
        return ({int(k): tuple(v) for k, v in c["players"].items()},
                f"player index refresh failed; using a {age_h:.0f}h-old cache")
    except Exception as e:
        if c and age_h is not None and age_h < INDEX_STALE_OK_H:
            return ({int(k): tuple(v) for k, v in c["players"].items()},
                    f"player index refresh failed ({type(e).__name__}); using a {age_h:.0f}h-old cache")
        raise Blind(f"playerindex: {type(e).__name__}") from e
    INDEX_CACHE.write_text(json.dumps({"fetched_at": now.isoformat(), "season": season,
                                       "players": {str(k): v for k, v in players.items()}}))
    return players, ""

def _stats(p, r, a, t3, fga, fta, f3a):
    return {"pts": p, "reb": r, "ast": a, "fg3m": t3, "fga": fga, "fta": fta, "fg3a": f3a,
            "pra": p + r + a, "pts_reb": p + r, "pts_ast": p + a, "reb_ast": r + a}


def state(today_et, boxes, index=None):
    """Everything the engine projects from, merged and ordered by date.

    apps:  {pid: [(date, min, stats, team), ...]} — last season's game logs inside the 400-day
           pool PLUS this season's box scores. `stats` carries pts, reb, ast, fg3m, fga, fta,
           fg3a and the combos (pra, pts_reb, pts_ast, reb_ast) — the WNBA pricing machinery
           needs the shot columns (its conviction gate reads the FGA split). `team` is the team
           the player appeared FOR, so callers can scope to a franchise as the backtests did.
           Reads logs_full (nba_logs_full.py), never the 5-column `logs`.
    team:  {pid: CURRENT tricode}. With `index` (player_index) the index is authoritative and a
           player absent from it has NO current team; without it, the team of the most recent
           appearance — wrong for every summer move until the player appears.
    name:  {pid: name}
    """
    cut = (dt.date.fromisoformat(today_et) - dt.timedelta(days=POOL_DAYS)).isoformat()
    apps, team, name, last = defaultdict(list), {}, {}, {}
    con = sqlite3.connect(f"file:{LOGS}?mode=ro", uri=True)
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='logs_full'").fetchone():
        con.close()
        raise Blind("nba_gamelogs.sqlite has no logs_full — run nba_logs_full.py --fetch")
    for date, tri, pid, nm, mn, p, r, a, t3, fga, fta, f3a in con.execute(
            "SELECT date, team, player_id, player, min, pts, reb, ast, fg3m, fga, fta, fg3a "
            "FROM logs_full WHERE date >= ? AND date < ? AND min > 0", (cut, today_et)):
        apps[pid].append((date, float(mn), _stats(p, r, a, t3, fga, fta, f3a), tri))
        name[pid] = nm
        if date >= last.get(pid, ""):
            last[pid], team[pid] = date, tri
    con.close()
    for gid, bx in boxes.items():
        if bx["date"] >= today_et:                          # strictly prior games only
            continue
        for q in bx["players"]:
            pid = q["pid"]
            apps[pid].append((bx["date"], q["min"], _stats(
                q["pts"], q["reb"], q["ast"], q["fg3m"], q["fga"], q["fta"], q["fg3a"]),
                q["team"]))
            name[pid] = q["name"]
            if bx["date"] >= last.get(pid, ""):
                last[pid], team[pid] = bx["date"], q["team"]
    for pid in apps:
        apps[pid].sort(key=lambda a: a[0])
    if index is not None:
        team = {pid: tri for pid, (tri, _, _) in index.items()}
        for pid, (_, nm, _) in index.items():
            name.setdefault(pid, nm)
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
