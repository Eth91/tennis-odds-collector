#!/usr/bin/env python3
"""What the NHL side of Pickz shares: the 32 teams, the schedule, the rosters and player identity.

TEAMS. One code per team, the NHL's own (TBL, LAK, NJD, SJS, UTA). Every source is mapped onto these codes where it is
read: the NHL's APIs (its codes, or its team ids), ESPN (TB, LA, NJ, SJ, UTAH) and the books' event names ("Edmonton
Oilers @ New York Rangers"; DraftKings "EDM Oilers @ NY Rangers"), by nickname.

PLAYERS. The NHL's player id (8478402) is the identity everywhere: the stores, the page, the box scores.

GAMES. The NHL's game id as a string ("2026020214"), so the page keys it the way it keys the NBA's and the NFL's.

SOURCES (free, no key): api-web.nhle.com (rosters, scores, box scores, play by play), api.nhle.com/stats/rest (the
season's schedule, per-game reports, shift charts) and the NHL's HTML time-on-ice reports where the shift chart is
empty. Fetched through a cache under nhl_cache/, so a run reads each file at most every max_age seconds.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from nfl_common import Resolver, fold, nosfx       # noqa: F401  (player identity is the same problem in every league)

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("NHL_CACHE", HERE / "nhl_cache"))
WEB = "https://api-web.nhle.com/v1"
REST = "https://api.nhle.com/stats/rest/en"
ET, MT = ZoneInfo("America/New_York"), ZoneInfo("America/Denver")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# code: (full name, nickname, NHL team id, primary color)
TEAMS = {
    "ANA": ("Anaheim Ducks", "Ducks", 24, "#F47A38"), "BOS": ("Boston Bruins", "Bruins", 6, "#FFB81C"),
    "BUF": ("Buffalo Sabres", "Sabres", 7, "#003087"), "CAR": ("Carolina Hurricanes", "Hurricanes", 12, "#CE1126"),
    "CBJ": ("Columbus Blue Jackets", "Blue Jackets", 29, "#002654"), "CGY": ("Calgary Flames", "Flames", 20, "#D2001C"),
    "CHI": ("Chicago Blackhawks", "Blackhawks", 16, "#CF0A2C"), "COL": ("Colorado Avalanche", "Avalanche", 21, "#6F263D"),
    "DAL": ("Dallas Stars", "Stars", 25, "#006847"), "DET": ("Detroit Red Wings", "Red Wings", 17, "#CE1126"),
    "EDM": ("Edmonton Oilers", "Oilers", 22, "#FF4C00"), "FLA": ("Florida Panthers", "Panthers", 13, "#C8102E"),
    "LAK": ("Los Angeles Kings", "Kings", 26, "#111111"), "MIN": ("Minnesota Wild", "Wild", 30, "#154734"),
    "MTL": ("Montreal Canadiens", "Canadiens", 8, "#AF1E2D"), "NJD": ("New Jersey Devils", "Devils", 1, "#CE1126"),
    "NSH": ("Nashville Predators", "Predators", 18, "#FFB81C"), "NYI": ("New York Islanders", "Islanders", 2, "#00539B"),
    "NYR": ("New York Rangers", "Rangers", 3, "#0038A8"), "OTT": ("Ottawa Senators", "Senators", 9, "#C52032"),
    "PHI": ("Philadelphia Flyers", "Flyers", 4, "#F74902"), "PIT": ("Pittsburgh Penguins", "Penguins", 5, "#FCB514"),
    "SEA": ("Seattle Kraken", "Kraken", 55, "#355464"), "SJS": ("San Jose Sharks", "Sharks", 28, "#006D75"),
    "STL": ("St. Louis Blues", "Blues", 19, "#002F87"), "TBL": ("Tampa Bay Lightning", "Lightning", 14, "#002868"),
    "TOR": ("Toronto Maple Leafs", "Maple Leafs", 10, "#00205B"), "UTA": ("Utah Mammoth", "Mammoth", 68, "#6CACE4"),
    "VAN": ("Vancouver Canucks", "Canucks", 23, "#00205B"), "VGK": ("Vegas Golden Knights", "Golden Knights", 54, "#B4975A"),
    "WPG": ("Winnipeg Jets", "Jets", 52, "#041E42"), "WSH": ("Washington Capitals", "Capitals", 15, "#C8102E"),
}
ALIAS = {"TB": "TBL", "LA": "LAK", "NJ": "NJD", "SJ": "SJS", "UTAH": "UTA", "WAS": "WSH", "MON": "MTL", "VEG": "VGK",
         "CLB": "CBJ", "CLS": "CBJ", "CAL": "CGY", "NAS": "NSH", "WIN": "WPG", "ARI": "UTA", "PHX": "UTA"}
BY_ID = {v[2]: k for k, v in TEAMS.items()} | {59: "UTA"}          # 59: Utah Hockey Club (2024-25), now the Mammoth
BY_NICK = {v[1].split()[-1].lower(): k for k, v in TEAMS.items()}  # "leafs", "jackets", "wings", "knights": all unique
POS_GROUP = {"C": "C", "L": "W", "R": "W", "LW": "W", "RW": "W", "W": "W", "D": "D", "G": "G"}


def team(code):
    """Any source's team code -> ours (None for an unknown or empty one)."""
    c = (code or "").strip().upper()
    c = ALIAS.get(c, c)
    return c if c in TEAMS else None


def team_of_name(name):
    """A book's or ESPN's team name ("New York Rangers", "NY Rangers", "Rangers") -> our code, by its nickname."""
    w = fold(name).split()
    return BY_NICK.get(w[-1]) if w else None


def season_of(date):
    """The NHL season a date falls in, named for its first year (October to June: 2026-11-01 -> 2026)."""
    d = dt.date.fromisoformat(str(date)[:10])
    return d.year if d.month >= 8 else d.year - 1


def season_id(season):
    """2026 -> "20262027", the NHL's name for it."""
    return f"{int(season)}{int(season) + 1}"


# ── fetching, cached ──────────────────────────────────────────────────────────────────────────────────────────
def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:                                                    # pragma: no cover
        return ssl.create_default_context()


def fetch(url, timeout=60, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/html"})
    with urllib.request.urlopen(req, context=_ctx(), timeout=timeout) as r:
        b = r.read()
    return b if raw else json.loads(b)


def cached(name, url, max_age, raw=False, get=None):
    """The JSON (or bytes) at url, kept under nhl_cache/name and fetched again when older than max_age seconds. A failed
    fetch falls back to the cached copy, however old; with none it raises."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / name
    if f.exists() and time.time() - f.stat().st_mtime < max_age:
        b = f.read_bytes()
        return b if raw else json.loads(b)
    try:
        got = get(url) if get else fetch(url, raw=True)
        b = got if isinstance(got, bytes) else json.dumps(got).encode()
    except Exception:
        if f.exists():
            b = f.read_bytes()
            return b if raw else json.loads(b)
        raise
    tmp = f.with_name(f.name + ".part")
    tmp.write_bytes(b)
    os.replace(tmp, f)
    return b if raw else json.loads(b)


def rest_rows(path, cayenne, name, max_age, extra="", get=None, page=10000):
    """Every row of an NHL stats REST report (api.nhle.com/stats/rest/en/{path}) for a cayenne filter, paged."""
    out, start = [], 0
    while True:
        url = (f"{REST}/{path}?start={start}&limit={page}{extra}&cayenneExp=" + urllib.parse.quote(cayenne))
        j = cached(f"{name}_{start}.json", url, max_age, get=get)
        rows = j.get("data") or []
        out += rows
        if len(rows) < page or start + page >= (j.get("total") or 0):
            return out
        start += page


# ── the schedule ──────────────────────────────────────────────────────────────────────────────────────────────
STATE = {1: "pregame", 2: "pregame", 3: "live", 4: "live", 5: "final", 6: "final", 7: "final", 8: "postponed", 9: "postponed"}


def to_utc(eastern):
    """The NHL's easternStartTime ("2026-11-01T19:00:00", US Eastern) -> naive UTC ISO."""
    t = dt.datetime.fromisoformat(eastern).replace(tzinfo=ET)
    return t.astimezone(dt.timezone.utc).replace(tzinfo=None).isoformat()


def schedule(season, max_age=3 * 3600, get=None):
    """Every regular-season and playoff game of a season: [{gid, season, type ("R" / "P"), date (ET), utc, away, home,
    away_score, home_score (None until final), state}]. Playoff games never played (if necessary) are left out."""
    out = []
    for gt, kind in ((2, "R"), (3, "P")):
        rows = rest_rows("game", f"season={season_id(season)} and gameType={gt}", f"games_{season}_{gt}", max_age, get=get)
        for g in rows:
            h, a = BY_ID.get(g.get("homeTeamId")), BY_ID.get(g.get("visitingTeamId"))
            if not h or not a or not g.get("easternStartTime"):
                continue
            state = STATE.get(g.get("gameStateId"), "pregame")
            if g.get("gameScheduleStateId") not in (None, 1):
                state = "postponed"
            if kind == "P" and state != "final" and dt.date.fromisoformat(g["easternStartTime"][:10]) < dt.date.today():
                continue
            fin = state == "final"
            out.append({"gid": str(g["id"]), "season": int(season), "type": kind, "date": g["easternStartTime"][:10],
                        "utc": to_utc(g["easternStartTime"]), "away": a, "home": h, "state": state,
                        "away_score": g.get("visitingScore") if fin else None,
                        "home_score": g.get("homeScore") if fin else None, "period": g.get("period")})
    out.sort(key=lambda g: (g["utc"], g["gid"]))
    return out


# ── rosters and identity ──────────────────────────────────────────────────────────────────────────────────────
def roster(t, max_age=6 * 3600, get=None):
    """[{pid, name, team, pos (C / L / R / D / G), jersey, headshot, shoots}] on a team's current roster."""
    j = cached(f"roster_{t}.json", f"{WEB}/roster/{t}/current", max_age, get=get)
    out = []
    for grp in ("forwards", "defensemen", "goalies"):
        for p in j.get(grp) or []:
            nm = f"{(p.get('firstName') or {}).get('default', '')} {(p.get('lastName') or {}).get('default', '')}".strip()
            out.append({"pid": int(p["id"]), "name": nm, "team": t, "pos": p.get("positionCode") or "",
                        "jersey": p.get("sweaterNumber"), "headshot": p.get("headshot"), "shoots": p.get("shootsCatches")})
    return out


def rosters(season=None, max_age=6 * 3600, get=None):
    """{pid: {"name", "team", "pos", "jersey", "headshot", "shoots"}} over the 32 current rosters (a team that fails to
    load is left out, logged)."""
    out = {}
    for t in TEAMS:
        try:
            for p in roster(t, max_age, get):
                out[p.pop("pid")] = p
        except Exception as e:                                               # noqa: BLE001
            print(f"nhl_common: no roster for {t}: {type(e).__name__}")
    return out


SEARCH = "https://search.d3.nhle.com/api/v1/search/player?culture=en-us&limit=8&q="
SEARCH_MAX_AGE = 86400


class Resolver(Resolver):
    """nfl_common's Resolver (the two teams' rosters, a name unique there or nothing), then for a name still unknown the
    NHL's player search: a call-up the roster lists do not show yet. Accepted only when exactly one player of that name
    is on one of the game's two teams there. Searches are cached a day (nhl_cache/search.json)."""

    def __init__(self, roster, search=True, get=None):
        super().__init__(roster)
        self.search, self.get, self.memo = search, get, None

    def _found(self, name):
        if self.memo is None:
            try:
                self.memo = json.loads((CACHE / "search.json").read_text())
            except (OSError, ValueError):
                self.memo = {}
        k = nosfx(fold(name))
        hit = self.memo.get(k)
        if hit is None or time.time() - hit[0] > SEARCH_MAX_AGE:
            try:
                rows = (self.get or fetch)(SEARCH + urllib.parse.quote(name))
            except Exception:                                                # noqa: BLE001
                return []
            hit = [time.time(), [[int(r["playerId"]), team(r.get("teamAbbrev") or r.get("lastTeamAbbrev"))]
                                 for r in rows or [] if nosfx(fold(r.get("name"))) == k and r.get("playerId")]]
            self.memo[k] = hit
            try:
                CACHE.mkdir(parents=True, exist_ok=True)
                tmp = CACHE / "search.json.part"
                tmp.write_text(json.dumps(self.memo))
                os.replace(tmp, CACHE / "search.json")
            except OSError:
                pass
        return hit[1]

    def resolve(self, name, teams):
        pid = super().resolve(name, teams)
        if pid is not None or not self.search:
            return pid
        hits = {p for p, t in self._found(name) if t in teams}
        return hits.pop() if len(hits) == 1 else None


def searched():
    """{pid: team} from the player-search cache: the call-ups Resolver found that no roster lists yet."""
    try:
        memo = json.loads((CACHE / "search.json").read_text())
    except (OSError, ValueError):
        return {}
    return {p: t for _, hits in memo.values() for p, t in hits if t}


headshot = lambda season, t, pid: f"https://assets.nhle.com/mugs/nhl/{season_id(season)}/{t}/{pid}.png"


def game_state(gid_state):
    """The NHL's gameState string (FUT PRE LIVE CRIT FINAL OFF PPD) -> pregame / live / final / postponed."""
    return {"FUT": "pregame", "PRE": "pregame", "LIVE": "live", "CRIT": "live", "FINAL": "final", "OFF": "final",
            "PPD": "postponed", "SUSP": "postponed"}.get((gid_state or "").upper(), "pregame")
