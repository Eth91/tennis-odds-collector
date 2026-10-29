#!/usr/bin/env python3
"""What the NFL side of Pickz shares: the 32 teams, the schedule, the weekly rosters and player identity.

TEAMS. One code per team, nflverse's except the Rams (nflverse "LA" is "LAR" here, as every book and ESPN print it).
Every source is mapped onto these codes where it is read: nflverse (LA), ESPN (WSH, LAR), the books' event names
("Carolina Panthers @ Green Bay Packers"; DraftKings "CAR Panthers @ GB Packers").

PLAYERS. nflverse's GSIS id ("00-0039732") is the identity; the page and the stores carry it as an integer, its digits
after "00-" (39732), because the NBA side's code keys players by int. pid_of / gsis_of convert.

SOURCES (free, no key): nflverse-data GitHub releases (schedule, weekly rosters, weekly stats, snap counts, play by play,
injuries), refreshed by nflverse through the season; fetched with a cache under nfl_cache/ so a run reads each file at
most every CACHE_S seconds.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import os
import re
import ssl
import time
import unicodedata
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("NFL_CACHE", HERE / "nfl_cache"))
REL = "https://github.com/nflverse/nflverse-data/releases/download"
ET, MT = ZoneInfo("America/New_York"), ZoneInfo("America/Denver")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# code: (city / full name, nickname, ESPN code, ESPN id, primary color)
TEAMS = {
    "ARI": ("Arizona Cardinals", "Cardinals", "ARI", 22, "#97233F"), "ATL": ("Atlanta Falcons", "Falcons", "ATL", 1, "#A71930"),
    "BAL": ("Baltimore Ravens", "Ravens", "BAL", 33, "#241773"), "BUF": ("Buffalo Bills", "Bills", "BUF", 2, "#00338D"),
    "CAR": ("Carolina Panthers", "Panthers", "CAR", 29, "#0085CA"), "CHI": ("Chicago Bears", "Bears", "CHI", 3, "#0B162A"),
    "CIN": ("Cincinnati Bengals", "Bengals", "CIN", 4, "#FB4F14"), "CLE": ("Cleveland Browns", "Browns", "CLE", 5, "#311D00"),
    "DAL": ("Dallas Cowboys", "Cowboys", "DAL", 6, "#003594"), "DEN": ("Denver Broncos", "Broncos", "DEN", 7, "#FB4F14"),
    "DET": ("Detroit Lions", "Lions", "DET", 8, "#0076B6"), "GB": ("Green Bay Packers", "Packers", "GB", 9, "#203731"),
    "HOU": ("Houston Texans", "Texans", "HOU", 34, "#03202F"), "IND": ("Indianapolis Colts", "Colts", "IND", 11, "#002C5F"),
    "JAX": ("Jacksonville Jaguars", "Jaguars", "JAX", 30, "#006778"), "KC": ("Kansas City Chiefs", "Chiefs", "KC", 12, "#E31837"),
    "LV": ("Las Vegas Raiders", "Raiders", "LV", 13, "#000000"), "LAC": ("Los Angeles Chargers", "Chargers", "LAC", 24, "#0080C6"),
    "LAR": ("Los Angeles Rams", "Rams", "LAR", 14, "#003594"), "MIA": ("Miami Dolphins", "Dolphins", "MIA", 15, "#008E97"),
    "MIN": ("Minnesota Vikings", "Vikings", "MIN", 16, "#4F2683"), "NE": ("New England Patriots", "Patriots", "NE", 17, "#002244"),
    "NO": ("New Orleans Saints", "Saints", "NO", 18, "#D3BC8D"), "NYG": ("New York Giants", "Giants", "NYG", 19, "#0B2265"),
    "NYJ": ("New York Jets", "Jets", "NYJ", 20, "#125740"), "PHI": ("Philadelphia Eagles", "Eagles", "PHI", 21, "#004C54"),
    "PIT": ("Pittsburgh Steelers", "Steelers", "PIT", 23, "#FFB612"), "SF": ("San Francisco 49ers", "49ers", "SF", 25, "#AA0000"),
    "SEA": ("Seattle Seahawks", "Seahawks", "SEA", 26, "#002244"), "TB": ("Tampa Bay Buccaneers", "Buccaneers", "TB", 27, "#D50A0A"),
    "TEN": ("Tennessee Titans", "Titans", "TEN", 10, "#4B92DB"), "WAS": ("Washington Commanders", "Commanders", "WSH", 28, "#5A1414"),
}
ALIAS = {"LA": "LAR", "WSH": "WAS", "STL": "LAR", "SD": "LAC", "OAK": "LV", "JAC": "JAX"}
BY_NICK = {v[1].lower(): k for k, v in TEAMS.items()}
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def team(code):
    """Any source's team code -> ours (None for an unknown or empty one)."""
    c = (code or "").strip().upper()
    c = ALIAS.get(c, c)
    return c if c in TEAMS else None


def team_of_name(name):
    """A book's team name ("Green Bay Packers", "GB Packers", "Packers") -> our code, by its nickname."""
    w = fold(name).split()
    return BY_NICK.get(w[-1]) if w else None


def fold(s):
    n = unicodedata.normalize("NFKD", s or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[.'\u2019]", "", n.lower())                  # "D.J." = "DJ", "Ja'Kobi" = "Jakobi"
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", n).split())


def nosfx(f):
    return " ".join(t for t in f.split() if t not in SUFFIX)


def pid_of(gsis):
    """"00-0039732" -> 39732 (None for anything else)."""
    m = re.fullmatch(r"\d\d-(\d{7})", (gsis or "").strip())
    return int(m.group(1)) if m else None


def gsis_of(pid):
    return f"00-{int(pid):07d}"


# ── nflverse files, cached ────────────────────────────────────────────────────────────────────────────────
def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:                                                    # pragma: no cover
        return ssl.create_default_context()


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, context=_ctx(), timeout=timeout).read()


CACHE_S = 3 * 3600


def cached(path, max_age=CACHE_S):
    """The local copy of an nflverse release file ("schedules/games.csv"), downloaded again (streamed to disk, never
    held whole in memory: the VM has 1 GB) when older than max_age seconds. A failed download falls back to the cached
    copy, however old; with none it raises."""
    import shutil
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / path.replace("/", "__")
    if f.exists() and time.time() - f.stat().st_mtime < max_age:
        return f
    tmp = f.with_name(f.name + ".part")
    try:
        req = urllib.request.Request(f"{REL}/{path}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, context=_ctx(), timeout=180) as r, open(tmp, "wb") as out:
            shutil.copyfileobj(r, out, 1 << 20)
    except Exception:
        if f.exists():
            return f
        raise
    os.replace(tmp, f)
    return f


def release(path, max_age=CACHE_S):
    """The bytes of an nflverse release file (see cached)."""
    return cached(path, max_age).read_bytes()


def iter_rows(path, max_age=CACHE_S):
    """An nflverse csv (or csv.gz) streamed as dicts, a row at a time."""
    f = cached(path, max_age)
    with (gzip.open(f, "rt", encoding="utf-8-sig", newline="") if path.endswith(".gz")
          else open(f, encoding="utf-8-sig", newline="")) as fh:
        yield from csv.DictReader(fh)


def rows(path, max_age=CACHE_S):
    """An nflverse csv (or csv.gz) as a list of dicts."""
    return list(iter_rows(path, max_age))


def season_of(date):
    """The NFL season a date falls in: September to February is one season, named for its first year."""
    d = dt.date.fromisoformat(str(date)[:10])
    return d.year if d.month >= 3 else d.year - 1


# ── the schedule ──────────────────────────────────────────────────────────────────────────────────────────
def kickoff_utc(gameday, gametime):
    """nflverse's gameday + gametime (US Eastern) -> naive UTC ISO."""
    t = dt.datetime.fromisoformat(f"{gameday}T{gametime or '13:00'}").replace(tzinfo=ET)
    return t.astimezone(dt.timezone.utc).replace(tzinfo=None).isoformat()


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def schedule(season=None, max_age=CACHE_S):
    """Every game of a season (all seasons if None): [{gid, season, week, type, date (ET), utc, away, home, away_score,
    home_score, spread (nflverse spread_line: the home team's margin the line expects, + = home favored), total, roof,
    surface, temp, wind, away_rest, home_rest, div, stadium, espn}]."""
    out = []
    for r in iter_rows("schedules/games.csv", max_age):
        if season is not None and str(r["season"]) != str(season):
            continue
        h, a = team(r["home_team"]), team(r["away_team"])
        if not h or not a:
            continue
        out.append({"gid": r["game_id"], "season": int(r["season"]), "week": int(r["week"]), "type": r["game_type"],
                    "date": r["gameday"], "utc": kickoff_utc(r["gameday"], r["gametime"]), "away": a, "home": h,
                    "away_score": _f(r["away_score"]), "home_score": _f(r["home_score"]),
                    "spread": _f(r["spread_line"]), "total": _f(r["total_line"]), "roof": r["roof"] or None,
                    "surface": r["surface"] or None, "temp": _f(r["temp"]), "wind": _f(r["wind"]),
                    "away_rest": _f(r["away_rest"]), "home_rest": _f(r["home_rest"]), "div": r["div_game"] == "1",
                    "stadium": r["stadium"] or None, "espn": r["espn"] or None, "location": r["location"]})
    return out


def current_week(sched, now=None):
    """(season, week) of the slate on now: the earliest week with a game not yet final, counted final 4 h after its
    kickoff (a game's score lands in nflverse hours later; the page reads live state from ESPN)."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).replace(tzinfo=None)
    open_ = [g for g in sched if g["home_score"] is None
             and dt.datetime.fromisoformat(g["utc"]) + dt.timedelta(hours=4) > now]
    if not open_:
        g = max(sched, key=lambda g: g["utc"])
        return g["season"], g["week"]
    g = min(open_, key=lambda g: (g["season"], g["week"], g["utc"]))
    return g["season"], g["week"]


# ── rosters and identity ──────────────────────────────────────────────────────────────────────────────────
def rosters(season, max_age=CACHE_S):
    """{pid: {"name", "team", "pos", "depth_pos", "status", "headshot", "espn", "pfr", "jersey", "week"}} from the
    season's weekly rosters, each player's latest week."""
    out = {}
    for r in iter_rows(f"weekly_rosters/roster_weekly_{season}.csv", max_age):
        pid = pid_of(r.get("gsis_id"))
        if pid is None:
            continue
        wk = int(r.get("week") or 0)
        if pid in out and out[pid]["week"] > wk:
            continue
        out[pid] = {"name": r.get("full_name") or "", "team": team(r.get("team")), "pos": r.get("position") or "",
                    "depth_pos": r.get("depth_chart_position") or "", "status": r.get("status") or "",
                    "headshot": r.get("headshot_url") or None, "espn": r.get("espn_id") or None,
                    "pfr": r.get("pfr_id") or None, "jersey": r.get("jersey_number") or None, "week": wk,
                    "football_name": r.get("football_name") or ""}
    return out


class Resolver:
    """Book player names -> pids, scoped to the two teams of a game (about 110 players), never league-wide: the folded
    name (suffixes dropped; his football name in place of his first name counts too), then first initial + surname.
    A key counts only when it is unique within those rosters; an ambiguous name stays unresolved (None), never guessed."""

    def __init__(self, roster):
        self.by_team = {}
        for pid, r in roster.items():
            if r["team"]:
                w = nosfx(fold(r["name"])).split()
                full = {" ".join(w)}
                if r.get("football_name") and len(w) >= 2:
                    full.add(nosfx(fold(r["football_name"])) + " " + w[-1])
                self.by_team.setdefault(r["team"], []).append((pid, full, (w[0][:1], w[-1]) if len(w) >= 2 else None))

    def resolve(self, name, teams):
        cand = [c for t in teams for c in self.by_team.get(t, [])]
        f = nosfx(fold(name))
        hits = {pid for pid, full, _ in cand if f in full}
        if len(hits) == 1:
            return hits.pop()
        if hits:
            return None
        w = f.split()
        if len(w) >= 2:
            hits = {pid for pid, _, ini in cand if ini == (w[0][:1], w[-1])}
            if len(hits) == 1:
                return hits.pop()
        return None
