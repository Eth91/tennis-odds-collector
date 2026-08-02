"""@UnderdogWNBA STARTING-LINEUP parser.

Underdog posts confirmed fives in a fixed shape, ~30-60 min before tip:

    Lineup alert: Liberty will start Ionescu, Astier, Allen, Stewart, Jones on Tuesday.
    Lineup alert: Fire will start Leite, Carleton, Engstler, Puoch, DiLeo on Tuesday.

That is the fastest confirmed-starters signal we get, and the user reads it directly. Names
are SURNAMES ONLY, so resolution is team-scoped and refuses ambiguity (the RotoWire lesson:
an ambiguous surname must be skipped, never guessed).

DESIGN NOTE -- this emits a ROLE signal, NOT an injury status.
"Not in the starting five" is much weaker than "ruled out": a 23-mpg player can be a sixth
woman. So `non_starters()` returns only players who USUALLY START (>= USUAL_START_RATE of
their recent appearances) and are missing from a confirmed five -- for them the signal is
real (benched, minutes-restricted, or a late scratch). Everyone else is ignored. Nothing here
ever writes an Out; injuries() keeps its own precedence
(@UnderdogWNBA rulings > official report > RotoWire).
"""
import datetime as dt
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "underdog_log.jsonl"
ROSTER = HERE / "wnba_players_cache.json"
MIN_GP = 5                   # ignore fringe bodies when ranking a team's expected five

# Underdog uses team NICKNAMES; map to the abbreviations the rest of the pipeline speaks.
NICK = {
    "aces": "LV", "dream": "ATL", "fever": "IND", "liberty": "NY", "lynx": "MIN",
    "mercury": "PHX", "mystics": "WSH", "sky": "CHI", "sparks": "LA", "storm": "SEA",
    "sun": "CON", "wings": "DAL", "valkyries": "GSV", "fire": "POR", "tempo": "TOR",
}
LINEUP_RE = re.compile(
    r"lineup alert:\s*(?P<team>[A-Za-z .'-]+?)\s+will start\s+(?P<names>.+?)\s+on\s+\w+",
    re.I)


def _roster():
    try:
        return json.loads(ROSTER.read_text()).get("players", {})
    except (OSError, ValueError):
        return {}


def parse_tweet(text):
    """-> (team_abbr, [surnames]) or None. Pure text -> shape; no roster needed."""
    m = LINEUP_RE.search(text or "")
    if not m:
        return None
    team = NICK.get(m.group("team").strip().lower())
    if not team:
        return None
    raw = m.group("names")
    names = [n.strip(" .") for n in re.split(r",\s*|\s+and\s+", raw) if n.strip(" .")]
    return (team, names) if names else None


def _resolve(surname, team, roster):
    """Team-scoped surname -> full roster name. Ambiguous or unknown -> None (never guess)."""
    s = surname.strip().lower()
    cands = [n for n, v in roster.items()
             if (v.get("team") or "").upper() == team
             and (n.lower() == s or n.lower().split()[-1] == s
                  or n.lower().endswith(" " + s))]
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:                       # e.g. two Smiths -- try initial+surname form
        tight = [n for n in cands if n.lower().split()[-1] == s]
        if len(tight) == 1:
            return tight[0]
    return None


def lineups(date_iso=None, tz=None):
    """{team_abbr: [full names]} of CONFIRMED fives posted for that ET date."""
    if date_iso is None:
        # default to "today" IN THE SLATE'S TIMEZONE. On a UTC host, a 9pm-ET lineup alert is
        # already tomorrow in UTC, so a naive date.today() looked for the wrong day and found
        # nothing.
        date_iso = (dt.datetime.now(tz).date().isoformat() if tz is not None
                    else dt.date.today().isoformat())
    roster = _roster()
    out = {}
    try:
        lines = LOG.read_text().splitlines()
    except OSError:
        return out
    for ln in lines:                          # oldest -> newest, so a re-post wins
        if not ln.strip():
            continue
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        txt = e.get("text") or ""
        if "lineup alert" not in txt.lower():
            continue
        when = (e.get("t") or "")[:10]
        if tz is not None:
            try:
                when = dt.datetime.fromisoformat(e["t"]).astimezone(tz).date().isoformat()
            except Exception:
                pass
        if when != date_iso:
            continue
        got = parse_tweet(txt)
        if not got:
            continue
        team, surnames = got
        five = [r for r in (_resolve(sn, team, roster) for sn in surnames) if r]
        if five:
            out[team] = five
    return out


def usual_starters(team, roster=None, unavailable=()):
    """The five we'd EXPECT to start: top-5 by season minutes among AVAILABLE players.

    An earlier version inferred a "start rate" from each player's own minutes distribution.
    That was broken by construction -- it counted games at-or-above the player's own median,
    so it could never exceed ~0.5 and Breanna Stewart scored 0.50, under the bar. Nothing ever
    flagged. Team minutes RANK is the honest measure: coaches start their highest-minute
    available players, so a top-5 name missing from a confirmed five is a real role change.
    """
    roster = roster if roster is not None else _roster()
    pool = [(v.get("min") or 0.0, n) for n, v in roster.items()
            if (v.get("team") or "").upper() == team
            and (v.get("gp") or 0) >= MIN_GP and n not in set(unavailable)]
    pool.sort(reverse=True)
    return [n for _, n in pool[:5]]


def non_starters(team, date_iso=None, tz=None, unavailable=()):
    """Expected starters ABSENT from today's confirmed five -- a role signal, never an Out.

    `unavailable` = players already known out, so the expected five is computed from who can
    actually play. Returns [] when no five was posted: silence is not evidence.
    """
    five = (lineups(date_iso, tz=tz) or {}).get(team)
    if not five:
        return []
    return sorted(n for n in usual_starters(team, unavailable=unavailable) if n not in five)


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else None
    lu = lineups(d)
    print("confirmed fives for %s: %d team(s)" % (d or "today", len(lu)))
    for t, five in sorted(lu.items()):
        print("  %-4s %s" % (t, ", ".join(five)))
    for t in sorted(lu):
        ns = non_starters(t, d)
        if ns:
            print("  %-4s USUAL STARTERS NOT IN THE FIVE: %s" % (t, ", ".join(ns)))
