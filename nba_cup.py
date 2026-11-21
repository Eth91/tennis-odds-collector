"""NBA Cup games for Pickz's NBA Cup filter: which game ids were Cup games, by NBA.com's own schedule labels.

NBA.com's schedule marks each Cup game (gameLabel "Emirates NBA Cup"; gameSubtype "in-season" for group play,
"in-season-knockout" for the knockout rounds) and names its group or round in gameSubLabel ("West Group B",
"Quarterfinal"). stats.nba.com serves a past season's schedule as well as this one's (scheduleleaguev2?Season=),
and answers the VM (probed 2026-11-02: 67 Cup games in 2025-26, 67 in 2026-27).

The group games, quarterfinals and semifinals are regular-season games, so they are in the box-score logs. The
championship is not (its stats don't count), so it never matches a log row.

Cached in nba_cup.json (the VM's own, gitignored). A season fetched after it ended is never fetched again; the
current one is refreshed once a day (its knockout games are placeholders until the teams are set). A failed fetch
keeps what is cached and is retried an hour later. With nothing cached, no game is a Cup game and the page shows
no Cup filter: a missing source hides the filter, it never shows a player with no Cup games.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "nba_cup.json"
SCHED = "https://stats.nba.com/stats/scheduleleaguev2?LeagueID=00&Season={}"
H = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com", "Accept": "application/json"}
REFRESH_H, RETRY_H = 24, 1


def parse(sched):
    """A scheduleleaguev2 payload -> {gid: "West Group B" | "Quarterfinal" | ...}, its Cup games only."""
    out = {}
    for d in sched["leagueSchedule"]["gameDates"]:
        for g in d["games"]:
            if (g.get("gameSubtype") or "").startswith("in-season") or "NBA Cup" in (g.get("gameLabel") or ""):
                out[g["gameId"]] = g.get("gameSubLabel") or "NBA Cup"
    return out


def _get(url):
    from curl_cffi import requests as cr
    r = cr.get(url, impersonate="chrome", timeout=30, headers=H)
    r.raise_for_status()
    return r.json()


def ended(season, at):
    """True once a season is over (by July; its Cup ended in December)."""
    return at.date() >= dt.date(int(season[:4]) + 1, 7, 1)


def games(seasons, now=None, get=None, cache=CACHE):
    """{gid: label} over the seasons, from the cache, fetching what is due first. Never raises: the page build
    must not fail over a filter."""
    now = now or dt.datetime.now(dt.timezone.utc)
    get = get or _get
    try:
        c = json.loads(Path(cache).read_text())
    except (OSError, ValueError):
        c = {}
    held = c.setdefault("seasons", {})
    failed = c.get("failed")
    wait = failed and now - dt.datetime.fromisoformat(failed) < dt.timedelta(hours=RETRY_H)
    changed = False
    for s in seasons:
        have = held.get(s)
        at = have and dt.datetime.fromisoformat(have["fetched"])
        if wait or (at and (ended(s, at) or now - at < dt.timedelta(hours=REFRESH_H))):
            continue
        try:
            got = parse(get(SCHED.format(s)))
            if not got:                              # a schedule with no Cup game in it is a changed format, not news
                raise ValueError("no Cup games in the schedule")
        except Exception as e:                       # noqa: BLE001  network, HTTP, JSON, shape
            print(f"nba_cup: {s} not fetched ({type(e).__name__}: {str(e)[:80]}); keeping the cache", file=sys.stderr)
            c["failed"], wait, changed = now.isoformat(), True, True
            continue
        held[s] = {"fetched": now.isoformat(), "games": got}
        c.pop("failed", None)
        changed = True
    if changed:
        tmp = Path(cache).with_name(f".{Path(cache).name}.tmp")
        try:
            tmp.write_text(json.dumps(c, separators=(",", ":")))
            os.replace(tmp, cache)
        except OSError as e:
            print(f"nba_cup: cache not written ({e})", file=sys.stderr)
    return {gid: lab for s in seasons for gid, lab in (held.get(s) or {}).get("games", {}).items()}


if __name__ == "__main__":
    import nba_research as RS
    s = RS.season_of(dt.date.today().isoformat())
    g = games((RS.prev_season(s), s))
    print(f"nba_cup: {len(g)} Cup games over {RS.prev_season(s)} and {s}")
