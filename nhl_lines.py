#!/usr/bin/env python3
"""NHL prop line collector: FanDuel + DraftKings -> nhl_lines.sqlite. Runs on the Oracle VM (cron, every 5 min).

The NHL side of Pickz (nhl_research.py) reads this store the way the NFL side reads nfl_lines.sqlite: the tables are
nfl_lines' own (board, quotes, game_lines, cycles) and the cycle is nfl_lines.cycle, run with the NHL's League.

IDENTITY (nhl_common). gid = the NHL's game id as a string ("2026020230"), matched from the book's "Away @ Home" by both
teams' nicknames, among games not yet started. pid = the NHL player id, resolved by name within the two teams' rosters
only; a name that is not unique there stays pid NULL and is counted, never guessed.

MARKETS (stat keys): goals assists points shots blocks saves ppp (power-play points). Two-sided O/U rungs keep the
posted line; a one-sided "N+" ladder rung is an over at N - 0.5; the anytime goal scorer is an over 0.5 (2+ goals 1.5,
3+ 2.5). Full-game (regulation + overtime) markets only: anything by period, a first / last / nth scorer, an overtime
scorer, each-period, combined, either-player, a parlay or a special is left out.

DRAFTKINGS blocks the VM (Akamai), so it arrives as a SNAPSHOT, as the NFL's does: GitHub Actions (nba-dk.yml) and the
Mac (nba_dk_push.sh) run `--snapshot dk PATH`, nba_dk_receive.py writes nhl_dk_snapshot.json for a snapshot marked
league "nhl", and NHL_DK_SNAPSHOT names that file here.

    python3 nhl_lines.py                      # one cycle, both books (NHL_BOOKS overrides)
    python3 nhl_lines.py --status             # the last cycles, writes nothing
    python3 nhl_lines.py --snapshot dk PATH   # fetch DraftKings only, write a snapshot file (the sender side)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nfl_lines as L
import nhl_common as C

HERE = Path(__file__).resolve().parent
DB = Path(os.environ.get("NHL_LINES_DB", HERE / "nhl_lines.sqlite"))
DDL = L.DDL
STATS = ("goals", "assists", "points", "shots", "blocks", "saves", "ppp")
dec = L.dec

# ── FanDuel ─────────────────────────────────────────────────────────────────────────────────────────────
FD_AK, FD_BASE = L.FD_AK, L.FD_BASE
FD_TABS = ("popular", "goals", "points/assists", "shots", "goalies")
FD_DAYS = 3           # props are read for games within this many days (the league page lists the next week)
# the stat in FanDuel's marketType: PLAYER_TOTAL_{X} (O/U), PLAYER_ALT_{X} (one player's "N+" ladder),
# PLAYER_TO_RECORD_N+_{X} (one rung, runners are players)
FD_STAT = {"SHOTS": "shots", "SHOTS_ON_GOAL": "shots", "GOALS": "goals", "SAVES": "saves", "POINTS": "points",
           "ASSISTS": "assists", "BLOCKED_SHOTS": "blocks", "BLOCKS": "blocks", "POWER_PLAY_POINTS": "ppp",
           "POWERPLAY_POINTS": "ppp"}
# the market's name after the player's: "Connor McDavid Shots on Goal", "Matt Tomkins Alt Saves"
FD_SUFFIX = re.compile(r"(?i)\s+(alt\s+)?(shots on goal|total goals|total saves|saves|total points|points|total assists|"
                       r"assists|blocked shots|blocks|power ?play points)$")
NOT_FULL_GAME = re.compile(r"PERIOD|SGP|_/_|FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|LAST|OVERTIME|EACH|"
                           r"COMBINED|EITHER|SPECIAL|MINUTES|60_MIN")
_REC = re.compile(r"^PLAYER_TO_RECORD_(\d+)\+_(.+)$")
_SCORE = re.compile(r"^PLAYER_TO_SCORE_(\d+)\+_GOALS$")
_N_PLUS = re.compile(r"^(\d+)\+")


def fd_extract(m):
    """[(player, stat, line, side, odds)] from one FanDuel market; [] for anything that is not a full-game player prop
    in STATS. Read from the marketType, which FanDuel keeps steady where the names vary."""
    t = (m.get("marketType") or "").upper()
    nm = (m.get("marketName") or "").strip()
    runners = m.get("runners") or []
    if not t or NOT_FULL_GAME.search(t):
        return []
    rows = []

    def each_player(stat, line):                         # runners are players: an over at the line
        for r in runners:
            o = L._fd_odds(r)
            if o is not None and r.get("runnerName"):
                rows.append((r["runnerName"].strip(), stat, line, "over", o))
        return rows
    if t == "ANY_TIME_GOAL_SCORER":
        return each_player("goals", 0.5)
    if (mm := _SCORE.match(t)):
        return each_player("goals", int(mm.group(1)) - 0.5)
    if (mm := _REC.match(t)):
        stat = FD_STAT.get(mm.group(2))
        return each_player(stat, int(mm.group(1)) - 0.5) if stat else []
    for pre, alt in (("PLAYER_TOTAL_", False), ("PLAYER_ALT_", True)):
        if t.startswith(pre):
            stat = FD_STAT.get(t[len(pre):])
            player = FD_SUFFIX.sub("", nm).strip()
            if not stat or not player or player == nm:
                return []
            for r in runners:
                o, rn, h = L._fd_odds(r), (r.get("runnerName") or "").strip(), r.get("handicap")
                if o is None:
                    continue
                toks = rn.lower().split()
                if not alt and toks and toks[-1] in ("over", "under") and h not in (None, 0, 0.0):
                    rows.append((player, stat, float(h), toks[-1], o))
                elif (mm := _N_PLUS.match(rn)):              # an alt rung "24+": over 23.5
                    rows.append((player, stat, int(mm.group(1)) - 0.5, "over", o))
            return rows
    return []


LAST_FD_PAGE = {}


def fetch_fd(get=None, now=None):
    """(rows [(event, player, stat, line, side, odds)], detail). Every failed GET is counted."""
    now = now or dt.datetime.now(dt.timezone.utc)
    fails = Counter()
    if get is None:
        import requests
        s = requests.Session()
        s.headers.update({"User-Agent": C.UA, "Accept": "application/json"})

        def get(url):
            r = s.get(url, timeout=25)
            r.raise_for_status()
            return r.json()
    page = get(f"{FD_BASE}/content-managed-page?page=CUSTOM&customPageId=nhl&timezone=America%2FNew_York&_ak={FD_AK}")
    LAST_FD_PAGE["page"] = page
    evs = []
    for eid, e in (page.get("attachments", {}).get("events") or {}).items():
        nm, od = e.get("name") or "", e.get("openDate")
        if "@" not in nm or not od:                      # no start time: cannot prove it is pre-game, so skip
            continue
        try:
            t = dt.datetime.fromisoformat(od.replace("Z", "+00:00"))
        except ValueError:
            continue
        if now < t <= now + dt.timedelta(days=FD_DAYS):
            evs.append((eid, nm))

    def one(ev):
        eid, nm = ev
        url = f"{FD_BASE}/event-page?eventId={eid}&_ak={FD_AK}&timezone=America%2FNew_York"
        try:
            base = get(url)
        except Exception:                                                    # noqa: BLE001
            return nm, [], 1
        markets, bad = dict(base.get("attachments", {}).get("markets") or {}), 0
        titles = [(t.get("title") if isinstance(t, dict) else str(t)) or "" for t in
                  (base.get("layout", {}).get("tabs") or {}).values()]
        slugs = [t.lower().replace(" ", "-").replace("'", "") for t in titles]
        for slug in [s for s in slugs if s in FD_TABS]:
            try:
                j = get(f"{url}&tab={urllib.parse.quote(slug, safe='')}")
            except Exception:                                                # noqa: BLE001
                bad += 1
                continue
            markets.update(j.get("attachments", {}).get("markets") or {})
        out = []
        for m in markets.values():
            out += [(nm, *r) for r in fd_extract(m)]
        return nm, out, bad

    rows = []
    with ThreadPoolExecutor(4) as ex:
        for nm, rr, bad in ex.map(one, evs):
            rows += rr
            if bad:
                fails["tab"] += bad
    return rows, (f"partial: failed GETs {dict(fails)}" if fails else "")


# ── DraftKings ──────────────────────────────────────────────────────────────────────────────────────────
DK_LEAGUE = "42133"
# (categoryId, subcategory name lowercased) -> stat. The categories pin it: "Shots on Goal" is also a name in Live
# Props, Game Leaders, Combined Props and Either Props, none of them a player's full-game prop.
DK_STATS = {(1189, "shots on goal o/u"): "shots", (1189, "shots on goal"): "shots",
            (1675, "points o/u"): "points", (1675, "points"): "points",
            (1676, "assists o/u"): "assists", (1676, "assists"): "assists",
            (1679, "blocks o/u"): "blocks", (1679, "blocks"): "blocks",
            (1064, "saves o/u"): "saves", (1064, "saves"): "saves",
            (1190, "anytime goalscorer"): "goals", (1190, "player goal milestones"): "goals",
            (550, "power play points"): "ppp"}
DK_ANYTIME = (1190, "anytime goalscorer")
DK_LAST = {}


def dk_key(s):
    return (s.get("categoryId"), re.sub(r"\s+", " ", (s.get("name") or "").strip().lower()))


def dk_rows(j, events):
    """[(event, player, stat, line, side, odds)] from one DraftKings subcategory response (`j`, its key in j["_key"]).
    events = {eventId: name} of the games not yet started."""
    import dk_collect as D
    key = tuple(j.get("_key") or ())
    stat = DK_STATS.get(key)
    if stat is None:
        return []
    mk = {m["id"]: m for m in j.get("markets", [])}
    rows, seen = [], set()
    for sel in j.get("selections", []):
        m = mk.get(sel.get("marketId")) or {}
        eid = m.get("eventId")
        if eid not in events:
            continue
        player, odds = D._player(sel), D._dec(sel)
        if not player or odds is None:
            continue
        raw = (sel.get("label") or "").strip()
        if key == DK_ANYTIME:
            side, pts = "over", 0.5
        else:
            pts, low = sel.get("points"), raw.lower()
            side = "over" if low.startswith("over") else "under" if low.startswith("under") else None
            if side is None and pts is None and D._MILESTONE.fullmatch(raw):
                side, pts = "over", float(raw[:-1]) - 0.5
            if side is None or pts is None:
                continue
        k = (sel.get("marketId"), side, round(float(pts), 1), player)
        if k in seen:
            continue
        seen.add(k)
        rows.append((events[eid], player, stat, float(pts), side, odds))
    return rows


def fetch_dk(get=None):
    """(rows, detail) from DraftKings' NHL league: every mapped subcategory, games not yet started."""
    import dk_collect as D
    get = get or D._get
    root = get(f"{D.B}/leagues/{DK_LEAGUE}")
    events = {}
    now = dt.datetime.now(dt.timezone.utc)
    for e in root.get("events", []):
        st = (e.get("status") or "").upper()
        if st and st != "NOT_STARTED":
            continue
        sd = (e.get("startEventDate") or "")[:19]
        try:
            if sd and dt.datetime.fromisoformat(sd).replace(tzinfo=dt.timezone.utc) <= now:
                continue
        except ValueError:
            pass
        events[e["id"]] = e.get("name", "")
    rows, mapped, fail = [], 0, 0
    for s in root.get("subcategories", []):
        if dk_key(s) not in DK_STATS:
            continue
        mapped += 1
        try:
            j = get(f"{D.B}/leagues/{DK_LEAGUE}/categories/{s['categoryId']}/subcategories/{s['id']}")
        except Exception:                                                    # noqa: BLE001
            fail += 1
            continue
        j["_key"] = list(dk_key(s))
        rows += dk_rows(j, events)
    DK_LAST.update(mapped=mapped, subfail=fail)
    detail = (f"partial: {fail} subcategory fetch(es) failed" if fail else
              "no player-prop subcategories posted" if not mapped else "")
    return rows, detail


Stale = L.Stale
DK_SNAPSHOT = os.environ.get("NHL_DK_SNAPSHOT")
DK_SNAPSHOT_MAX_AGE_S = L.DK_SNAPSHOT_MAX_AGE_S


def fetch_dk_snapshot(path=None, now=None):
    """DraftKings from the pushed snapshot file -> (rows, detail, fetched_at)."""
    p = Path(path or DK_SNAPSHOT)
    if not p.exists():
        raise Stale(f"no snapshot at {p}")
    snap = json.loads(p.read_text())
    if snap.get("league") != "nhl":
        raise Stale(f"{p} is not an NHL snapshot")
    at = snap["fetched_at"]
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    age = (now - dt.datetime.fromisoformat(at)).total_seconds()
    if age > DK_SNAPSHOT_MAX_AGE_S:
        raise Stale(f"snapshot {age / 60:.0f} min old (fetched {at}; sender asleep?)")
    return [tuple(r) for r in snap["rows"]], snap.get("detail", ""), at


def write_snapshot(book, path):
    """Fetch one book here and write {book, league, fetched_at, rows, detail} atomically (the sender side)."""
    at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat()
    rows, detail = {"fd": fetch_fd, "dk": fetch_dk}[book]()
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps({"book": book, "league": "nhl", "fetched_at": at, "rows": [list(r) for r in rows],
                               "detail": detail}))
    tmp.replace(path)
    print(f"[{at}] nhl {book} snapshot -> {path}: {len(rows)} rows" + (f" · {detail}" if detail else ""))


BOOKS = {"fd": fetch_fd, "dk": fetch_dk_snapshot if DK_SNAPSHOT else fetch_dk}
DEFAULT_BOOKS = tuple(b for b in os.environ.get("NHL_BOOKS", "fd,dk").split(",") if b)


def league():
    return L.League(C, STATS, DB, BOOKS, DEFAULT_BOOKS, LAST_FD_PAGE, "nhl")


def cycle(books=None, now=None, sched=None, roster=None, fetchers=None, db=None):
    """One refresh of each book (nfl_lines.cycle with the NHL's League)."""
    return L.cycle(books, now=now, sched=sched, roster=roster, fetchers=fetchers, db=db, lg=league())


def status(n=8):
    if not DB.exists():
        print("no nhl_lines.sqlite yet")
        return
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    for r in con.execute("SELECT * FROM cycles ORDER BY ts DESC, book LIMIT ?", (n,)):
        print(r)
    q = con.execute("SELECT COUNT(*), MIN(seen_at), MAX(seen_at) FROM quotes").fetchone()
    print(f"quotes: {q[0]:,} rows {q[1]} -> {q[2]}")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--book", choices=sorted(BOOKS), action="append")
    ap.add_argument("--snapshot", nargs=2, metavar=("BOOK", "PATH"))
    a = ap.parse_args()
    if a.snapshot:
        write_snapshot(a.snapshot[0], a.snapshot[1])
        sys.exit(0)
    if a.status:
        status()
        sys.exit(0)
    sys.exit(2 if cycle(tuple(a.book) if a.book else None) else 0)
