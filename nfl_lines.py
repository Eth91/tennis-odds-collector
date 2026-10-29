#!/usr/bin/env python3
"""NFL prop line collector: FanDuel + DraftKings -> nfl_lines.sqlite. Runs on the Oracle VM (cron, every 5 min).

The NFL side of Pickz (nfl_research.py) reads this store the way the NBA page reads nba_lines.sqlite, so the
tables are nba_lines' own, column for column:
  board   each book's CURRENT pre-kickoff board, one row per (book, player, stat, line, side), replaced per book on
          every successful fetch.
  quotes  an append-only CHANGE LOG: a row when a rung is first seen, when its price moves, and when it is pulled
          (odds NULL, logged only on a fully successful fetch). The line history and the open come from here.
  game_lines  FanDuel's moneyline / spread / total per game, a row whenever one changes.
  cycles  one row per book per run: status, rows, events matched, players resolved.

IDENTITY (nfl_common). gid = nflverse's game_id ("2026_08_CAR_GB"), matched from the book's "Away @ Home" by both
teams' nicknames, among games not yet kicked off. pid = the player's nflverse GSIS id as an integer, resolved by
name within the two teams' rosters only, never league-wide; a name that is not unique there stays pid NULL and is
counted, never guessed.

MARKETS (stat keys): pass_yds pass_tds pass_att pass_comp pass_int long_comp rush_yds rush_att long_rush rec rec_yds
long_rec rush_rec_yds pass_rush_yds anytime_td kick_pts fg_made sacks. Two-sided O/U rungs keep the posted line; a
one-sided "N+" milestone is an over at N - 0.5. Anytime TD is an over 0.5 (2+ TDs 1.5, 3+ 2.5). Full-game markets
only: anything by quarter, half or drive, first / last scorer, either-player, combined, most-of, head-to-head or
special is left out.

DRAFTKINGS blocks the VM (Akamai), so it arrives as a SNAPSHOT: GitHub Actions (nba-dk.yml) and the Mac
(nba_dk_push.sh) run `--snapshot dk PATH` and ship the file through nba_dk_receive.py, which writes
nfl_dk_snapshot.json for a snapshot marked league "nfl". NFL_DK_SNAPSHOT names that file here; older than
DK_SNAPSHOT_MAX_AGE_S it is stale: logged, the board left untouched, not a failure.

    python3 nfl_lines.py                      # one cycle, both books (NFL_BOOKS overrides)
    python3 nfl_lines.py --status             # the last cycles, writes nothing
    python3 nfl_lines.py --snapshot dk PATH   # fetch DraftKings only, write a snapshot file (the sender side)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nfl_common as C

HERE = Path(__file__).resolve().parent
DB = Path(os.environ.get("NFL_LINES_DB", HERE / "nfl_lines.sqlite"))
DDL = """
CREATE TABLE IF NOT EXISTS board (
    book TEXT, collected_at TEXT, gid TEXT, tip_utc TEXT, event TEXT, home TEXT, away TEXT,
    pid INTEGER, player TEXT, stat TEXT, line REAL, side TEXT, odds REAL,
    PRIMARY KEY (book, player, stat, line, side));
CREATE TABLE IF NOT EXISTS quotes (
    seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT,
    stat TEXT, line REAL, side TEXT, odds REAL);
CREATE INDEX IF NOT EXISTS quotes_key ON quotes (gid, pid, stat, line, side, seen_at);
CREATE TABLE IF NOT EXISTS game_lines (
    seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, market TEXT, side TEXT, line REAL, odds REAL);
CREATE INDEX IF NOT EXISTS game_lines_key ON game_lines (gid, market, side, seen_at);
CREATE TABLE IF NOT EXISTS cycles (
    ts TEXT, book TEXT, status TEXT, rows INTEGER, events INTEGER, matched_events INTEGER,
    resolved INTEGER, unresolved INTEGER, detail TEXT);
"""
STATS = ("pass_yds", "pass_tds", "pass_att", "pass_comp", "pass_int", "long_comp", "rush_yds", "rush_att", "long_rush",
         "rec", "rec_yds", "long_rec", "rush_rec_yds", "pass_rush_yds", "anytime_td", "kick_pts", "fg_made", "sacks")

# a market by quarter, half or drive, a first / last scorer, a sum of players, a most-of or a special: never a
# full-game player prop. Checked on the market name before anything else is read from it.
NOT_FULL_GAME = re.compile(
    r"\b(quarter|qtr|half|halves|1h|2h|1q|2q|3q|4q|q[1-4]|drive|each|first|1st|2nd|3rd|4th|last|either|combine|combined|"
    r"most|h2h|special|specials|race|squares|exacta|exactas|parlay|sgp|overtime|team)\b")


def dec(am):
    if am is None:
        return None
    am = float(am)
    return round(1 + (am / 100 if am > 0 else 100 / -am), 4) if am else None


# ── FanDuel ─────────────────────────────────────────────────────────────────────────────────────────────
FD_AK = os.environ.get("FD_AK", "FhMFpcPWXMeyZxOx")
FD_BASE = f"https://sbapi.{os.environ.get('FD_STATE', 'ny')}.sportsbook.fanduel.com/api"
FD_TABS = ("popular", "passing-props", "rushing-props", "receiving-props", "td-scorer-props")
FD_TAB_WORDS = ("defense", "defensive", "kicking", "kicker", "special")
FD_DAYS = 10          # props are read for games within this many days (the league page lists the next weeks)
# the stat part of a FanDuel player market ("Jordan Love - Passing Yds", "Josh Jacobs - Alt Rushing Yds"); combos
# and "longest" before the single stats they contain
FD_STATS = (("rushing + receiving", "rush_rec_yds"), ("rush + rec", "rush_rec_yds"),
            ("passing + rushing", "pass_rush_yds"), ("pass + rush", "pass_rush_yds"),
            ("longest reception", "long_rec"), ("longest rush", "long_rush"), ("longest completion", "long_comp"),
            ("longest pass", "long_comp"),
            ("passing yds", "pass_yds"), ("passing yards", "pass_yds"),
            ("passing tds", "pass_tds"), ("passing touchdowns", "pass_tds"),
            ("pass attempts", "pass_att"), ("passing attempts", "pass_att"),
            ("completions", "pass_comp"), ("interceptions", "pass_int"),
            ("rushing yds", "rush_yds"), ("rushing yards", "rush_yds"),
            ("rushing attempts", "rush_att"), ("rush attempts", "rush_att"), ("carries", "rush_att"),
            ("receiving yds", "rec_yds"), ("receiving yards", "rec_yds"), ("receptions", "rec"),
            ("kicking points", "kick_pts"), ("kicking pts", "kick_pts"),
            ("field goals made", "fg_made"), ("made field goals", "fg_made"), ("field goals", "fg_made"),
            ("sacks", "sacks"))
_N_PLUS = re.compile(r"(\d+)\+")
_YARD_REC = re.compile(r"(?i)^players? to record an? (\d+)\+ yards? reception$")
_SACK = re.compile(r"(?i)^players? to record (?:an?|(\d+)\+) sacks?$")
_TDS = re.compile(r"(?i)^to score (\d+)\+ touchdowns$")


def _fd_odds(r):
    return dec(((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOdds"))


def _fd_stat(part):
    low = part.lower()
    return next((k for p, k in FD_STATS if p in low), None)


def fd_extract(m):
    """[(player, stat, line, side, odds)] from one FanDuel market; [] for anything that is not a full-game player
    prop in STATS."""
    nm = (m.get("marketName") or "").strip()
    low = nm.lower()
    rows = []
    runners = m.get("runners") or []
    if low == "any time touchdown scorer":
        line = 0.5
    elif (mm := _TDS.match(nm)):
        line = int(mm.group(1)) - 0.5
    else:
        line = None
    if line is not None:                                    # runners are players: an over at the line
        for r in runners:
            o = _fd_odds(r)
            if o is not None and r.get("runnerName"):
                rows.append((r["runnerName"].strip(), "anytime_td", line, "over", o))
        return rows
    for pat, stat in ((_YARD_REC, "long_rec"), (_SACK, "sacks")):
        if (mm := pat.match(nm)):
            line = int(mm.group(1)) - 0.5 if mm.group(1) else 0.5
            for r in runners:
                o = _fd_odds(r)
                if o is not None and r.get("runnerName"):
                    rows.append((r["runnerName"].strip(), stat, line, "over", o))
            return rows
    if NOT_FULL_GAME.search(low) or " - " not in nm:
        return rows
    player, part = (x.strip() for x in re.split(r"\s+-\s+", nm, 1))
    stat = _fd_stat(part)
    if stat is None or not player:
        return rows
    for r in runners:
        o, rn, h = _fd_odds(r), (r.get("runnerName") or ""), r.get("handicap")
        if o is None:
            continue
        toks = rn.lower().split()
        if toks and toks[-1] in ("over", "under") and h not in (None, 0, 0.0):
            rows.append((player, stat, float(h), toks[-1], o))
        elif (mm := _N_PLUS.search(rn)):                    # an alt rung "Josh Jacobs 25+ Yards": over N - 0.5
            rows.append((player, stat, int(mm.group(1)) - 0.5, "over", o))
    return rows


FD_GAME = {"MONEY_LINE": "moneyline", "MATCH_HANDICAP_(2-WAY)": "spread", "TOTAL_POINTS_(OVER/UNDER)": "total"}


def fd_game_lines(page):
    """[(event, market, runner, line, decimal)]: FanDuel's moneyline / spread / total from the league page."""
    att = page.get("attachments", {})
    events = att.get("events", {})
    out = []
    for m in (att.get("markets") or {}).values():
        kind = FD_GAME.get(m.get("marketType"))
        name = (events.get(str(m.get("eventId"))) or {}).get("name") or ""
        if not kind or m.get("marketStatus") != "OPEN" or "@" not in name:
            continue
        for r in m.get("runners") or []:
            o = _fd_odds(r)
            if o is not None:
                out.append((name, kind, r.get("runnerName") or "", r.get("handicap"), o))
    return out


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
    page = get(f"{FD_BASE}/content-managed-page?page=CUSTOM&customPageId=nfl&timezone=America%2FNew_York&_ak={FD_AK}")
    LAST_FD_PAGE["page"] = page
    evs = []
    for eid, e in (page.get("attachments", {}).get("events") or {}).items():
        nm, od = e.get("name") or "", e.get("openDate")
        if "@" not in nm or not od:                      # no kickoff time: cannot prove it is pre-game, so skip
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
        want = [s for s in slugs if s in FD_TABS or any(w in s for w in FD_TAB_WORDS)]
        for slug in want:
            try:
                j = get(f"{url}&tab={slug}")
            except Exception:                                                # noqa: BLE001
                bad += 1
                continue
            markets.update(j.get("attachments", {}).get("markets") or {})
        out = []
        for m in markets.values():
            out += [(nm, *r) for r in fd_extract(m)]
        return nm, out, bad

    rows = []
    with ThreadPoolExecutor(6) as ex:
        for nm, rr, bad in ex.map(one, evs):
            rows += rr
            if bad:
                fails["tab"] += bad
    return rows, (f"partial: failed GETs {dict(fails)}" if fails else "")


# ── DraftKings ──────────────────────────────────────────────────────────────────────────────────────────
DK_LEAGUE = "88808"
# subcategory name (lowercased; the O/U ones are two-sided, the others "N+" milestone ladders) -> stat. Exact names
# only, so the "- 1Q" / "- 1H" variants never match.
DK_STATS = {
    "pass yards": "pass_yds", "pass tds": "pass_tds", "pass attempts": "pass_att", "completions": "pass_comp",
    "interceptions": "pass_int", "pass + rush yards": "pass_rush_yds", "longest completion": "long_comp",
    "rush yards": "rush_yds", "rush attempts": "rush_att", "rush + rec yards": "rush_rec_yds",
    "longest rush": "long_rush", "rec yards": "rec_yds", "receiving yards": "rec_yds", "receptions": "rec",
    "longest reception": "long_rec", "kicking pts": "kick_pts", "fg made": "fg_made",
}
DK_TD_SUBCATS = ("td scorer", "3+ tds")
DK_TD_MARKETS = {"anytime td scorer": 0.5, "2+ tds": 1.5, "3+ tds": 2.5}
DK_LAST = {}


def dk_stat(subcat):
    return DK_STATS.get(re.sub(r"\s*o/u\s*$", "", (subcat or "").strip().lower()))


def dk_rows(j, events):
    """[(event, player, stat, line, side, odds)] from one DraftKings subcategory response (`j`, of subcategory
    named j["_name"]). events = {eventId: name} of the games not yet started."""
    import dk_collect as D
    name = (j.get("_name") or "").strip().lower()
    td = name in DK_TD_SUBCATS
    stat = None if td else dk_stat(name)
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
        if td:
            line = DK_TD_MARKETS.get((m.get("name") or "").strip().lower())
            if line is None:
                continue
            st, side, pts = "anytime_td", "over", line
        else:
            st, pts = stat, sel.get("points")
            low = raw.lower()
            side = "over" if low.startswith("over") else "under" if low.startswith("under") else None
            if side is None and pts is None and D._MILESTONE.fullmatch(raw):
                side, pts = "over", float(raw[:-1]) - 0.5
            if side is None or pts is None:
                continue
        k = (sel.get("marketId"), side, round(float(pts), 1), player)
        if k in seen:
            continue
        seen.add(k)
        rows.append((events[eid], player, st, float(pts), side, odds))
    return rows


def fetch_dk(get=None):
    """(rows, detail) from DraftKings' NFL league: every mapped subcategory, games not yet started."""
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
        nm = (s.get("name") or "").strip().lower()
        if s.get("categoryId") is None or not (dk_stat(nm) or nm in DK_TD_SUBCATS):
            continue
        mapped += 1
        try:
            j = get(f"{D.B}/leagues/{DK_LEAGUE}/categories/{s['categoryId']}/subcategories/{s['id']}")
        except Exception:                                                    # noqa: BLE001
            fail += 1
            continue
        j["_name"] = nm
        rows += dk_rows(j, events)
    DK_LAST.update(mapped=mapped, subfail=fail)
    detail = (f"partial: {fail} subcategory fetch(es) failed" if fail else
              "no player-prop subcategories posted" if not mapped else "")
    return rows, detail


class Stale(Exception):
    """A book's snapshot is too old to use: logged, board untouched, not a failure."""


DK_SNAPSHOT = os.environ.get("NFL_DK_SNAPSHOT")
DK_SNAPSHOT_MAX_AGE_S = 600


def fetch_dk_snapshot(path=None, now=None):
    """DraftKings from the pushed snapshot file -> (rows, detail, fetched_at)."""
    p = Path(path or DK_SNAPSHOT)
    if not p.exists():
        raise Stale(f"no snapshot at {p}")
    snap = json.loads(p.read_text())
    if snap.get("league") != "nfl":
        raise Stale(f"{p} is not an NFL snapshot")
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
    tmp.write_text(json.dumps({"book": book, "league": "nfl", "fetched_at": at, "rows": [list(r) for r in rows],
                               "detail": detail}))
    tmp.replace(path)
    print(f"[{at}] nfl {book} snapshot -> {path}: {len(rows)} rows" + (f" · {detail}" if detail else ""))


BOOKS = {"fd": fetch_fd, "dk": fetch_dk_snapshot if DK_SNAPSHOT else fetch_dk}
DEFAULT_BOOKS = tuple(b for b in os.environ.get("NFL_BOOKS", "fd,dk").split(",") if b)


# ── matching ────────────────────────────────────────────────────────────────────────────────────────────
def match_event(event, upcoming):
    """A book's 'Away @ Home' -> the not-yet-started schedule game with those two teams (the nearest kickoff)."""
    if "@" not in event:
        return None
    a, h = (C.team_of_name(x) for x in event.split("@", 1))
    hits = [g for g in upcoming if g["away"] == a and g["home"] == h]
    return min(hits, key=lambda g: g["utc"]) if hits else None


def is_team(player, g):
    """A row whose 'player' is one of the game's teams ("GB Packers") or a defense ("Arizona Defense", "GB D/ST"):
    a team market, not a player prop."""
    f = C.fold(player)
    return f.endswith((" defense", " d st", " dst")) or any(f.endswith(C.fold(C.TEAMS[t][1])) for t in (g["home"], g["away"]))


# a book may print the short form of a first name the roster spells out ("Drew" Ogletree is Andrew), or the other way
NICK = {"drew": "andrew", "andy": "andrew", "mike": "michael", "matt": "matthew", "chris": "christopher",
        "nick": "nicholas", "tony": "anthony", "josh": "joshua", "jake": "jacob", "will": "william", "bill": "william",
        "rob": "robert", "bob": "robert", "dan": "daniel", "danny": "daniel", "jon": "jonathan", "joe": "joseph",
        "tom": "thomas", "zach": "zachary", "alex": "alexander", "sam": "samuel", "ben": "benjamin", "pat": "patrick",
        "ken": "kenneth", "greg": "gregory", "jeff": "jeffrey", "tim": "timothy", "nate": "nathan", "cam": "cameron",
        "gabe": "gabriel", "dave": "david", "steve": "steven", "rick": "richard", "ted": "theodore", "ed": "edward"}


def name_tries(player):
    """The book's name, then the same with its first name swapped for the long or short form (NICK)."""
    w = C.fold(player).split()
    out = [player]
    if len(w) >= 2:
        alts = {NICK.get(w[0])} | {k for k, v in NICK.items() if v == w[0]}
        out += [" ".join([a] + w[1:]) for a in sorted(x for x in alts if x)]
    return out


def store_game_lines(con, page, upcoming, ts, book="fd"):
    """The page's game lines that CHANGED, for games not yet kicked off. Sides home / away (spread, moneyline),
    over / under (total). Returns rows written."""
    n = 0
    for event, kind, runner, line, odds in fd_game_lines(page):
        g = match_event(event, upcoming)
        if g is None:
            continue
        rt = C.team_of_name(runner)
        side = "home" if rt == g["home"] else "away" if rt == g["away"] else C.fold(runner)
        last = con.execute("SELECT line, odds FROM game_lines WHERE gid=? AND book=? AND market=? AND side=? "
                           "ORDER BY seen_at DESC LIMIT 1", (g["gid"], book, kind, side)).fetchone()
        if last == (line, odds):
            continue
        con.execute("INSERT INTO game_lines VALUES (?,?,?,?,?,?,?,?)", (ts, book, g["gid"], g["utc"], kind, side, line, odds))
        n += 1
    return n


# ── one cycle ───────────────────────────────────────────────────────────────────────────────────────────
def cycle(books=None, now=None, sched=None, roster=None, fetchers=None, db=None):
    """One refresh of each book. A book whose fetch fails leaves its board untouched and is returned in the failed
    list (exit 2). sched / roster / fetchers / db: for tests."""
    books = books or DEFAULT_BOOKS
    fetchers = fetchers or BOOKS
    now = now or dt.datetime.now(dt.timezone.utc)
    ts = now.replace(microsecond=0, tzinfo=None).isoformat()
    naive = now.astimezone(dt.timezone.utc).replace(tzinfo=None)
    season = C.season_of(naive.date())
    if sched is None:
        sched = C.schedule(season)
    upcoming = [g for g in sched if g["home_score"] is None and dt.datetime.fromisoformat(g["utc"]) > naive]
    if roster is None:
        roster = C.rosters(season)
    res, cache = C.Resolver(roster), {}

    def resolve(player, g):
        k = (player, g["gid"])
        if k not in cache:
            cache[k] = next((pid for n in name_tries(player)
                             if (pid := res.resolve(n, (g["away"], g["home"]))) is not None), None)
        return cache[k]

    con = sqlite3.connect(db or DB, timeout=60)
    con.executescript(DDL)
    report, failed = [], []
    for book in books:
        t0 = time.time()
        try:
            got = fetchers[book]()
            rows, detail = got[0], got[1]
            bts = got[2] if len(got) > 2 else ts             # a snapshot keeps its own fetch time
            if book == "fd" and LAST_FD_PAGE.get("page"):
                try:
                    store_game_lines(con, LAST_FD_PAGE.pop("page"), upcoming, ts)
                except Exception as e:                                       # noqa: BLE001
                    report.append(f"game lines: {type(e).__name__}")
        except Stale as e:
            con.execute("INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?)", (ts, book, "stale", 0, 0, 0, 0, 0, str(e)[:200]))
            report.append(f"{book}=stale ({e}) — board left untouched")
            continue
        except Exception as e:                                               # noqa: BLE001
            failed.append(book)
            msg = f"{type(e).__name__}: {str(e)[:90]}"
            con.execute("INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?)", (ts, book, "error", 0, 0, 0, 0, 0, msg))
            report.append(f"{book}=error ({msg}) — board left untouched")
            continue
        # one price per rung: the O/U market's over 2.5 and the "3+" milestone are one bet, often at two prices;
        # keep the better one, or the board flips between them and logs moves that never happened
        best = {}
        for r in rows:
            if r[2] not in STATS:
                continue
            k = (r[1], r[2], round(float(r[3]), 1), r[4])
            if k not in best or r[5] > best[k][5]:
                best[k] = (r[0], r[1], r[2], round(float(r[3]), 1), r[4], r[5])
        rows = list(best.values())
        last = con.execute("SELECT MAX(collected_at) FROM board WHERE book=?", (book,)).fetchone()[0]
        if bts != ts and last and bts <= last:
            report.append(f"{book}=unchanged (snapshot {bts} already ingested)")
            continue
        events = {r[0] for r in rows}
        gm = {e: match_event(e, upcoming) for e in events}
        unmatched = sorted(e for e, g in gm.items() if g is None)
        board, unresolved, team_rows = [], set(), 0
        for event, player, stat, line, side, odds in rows:
            g = gm.get(event)
            if g is None:
                continue
            if is_team(player, g):
                team_rows += 1
                continue
            pid = resolve(player, g)
            if pid is None:
                unresolved.add(player)
            board.append((book, bts, g["gid"], g["utc"], event, g["home"], g["away"], pid, player, stat, line, side, odds))
        prev_rows = {(r[0], r[1], r[2], r[3]): r for r in con.execute(
            "SELECT player, stat, line, side, odds, gid, tip_utc, pid FROM board WHERE book=?", (book,))}
        prev = {k: r[4] for k, r in prev_rows.items()}
        changed = [(bts, b[0], b[2], b[3], b[7], b[8], b[9], b[10], b[11], b[12])
                   for b in board if prev.get((b[8], b[9], b[10], b[11])) != b[12]]
        con.execute("DELETE FROM board WHERE book=?", (book,))
        con.executemany("INSERT OR REPLACE INTO board VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", board)
        con.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", changed)
        players = {b[8] for b in board}
        status = "partial" if detail.startswith(("partial", "failed")) else "ok" if board else "no_lines"
        if status == "ok":                    # a pulled rung, logged odds NULL, only on a fully successful fetch
            now_keys = {(b[8], b[9], b[10], b[11]) for b in board}
            gone = [(bts, book, r[5], r[6], r[7], k[0], k[1], k[2], k[3], None)
                    for k, r in prev_rows.items() if k not in now_keys]
            con.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", gone)
        else:
            gone = []
        if unmatched:
            detail = (detail + "; " if detail else "") + f"unmatched events {unmatched[:3]}"
        if team_rows:
            detail = (detail + "; " if detail else "") + f"dropped {team_rows} team-market rows"
        con.execute("INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?)",
                    (bts, book, status, len(board), len(events), len(events) - len(unmatched),
                     len(players) - len(unresolved), len(unresolved), detail))
        covered = {gm[e]["gid"] for e in events if gm[e]}
        stats = Counter(b[9] for b in board)
        report.append(f"{book}={status} rows={len(board)} (+{len(changed)} quote changes, {len(gone)} pulled) "
                      f"games={len(covered)} players={len(players)} unresolved={len(unresolved)} "
                      f"{time.time() - t0:.0f}s" + (f" · {detail}" if detail else ""))
        report.append(f"   {book} stats: {dict(sorted(stats.items()))}")
        if unresolved:
            report.append(f"   {book} unresolved names: {sorted(unresolved)[:8]}")
    con.commit()
    con.close()
    print(f"[{ts}] nfl lines -> {Path(db or DB).name}")
    for line in report:
        print("  NFLLINES " + line if not line.startswith("   ") else line)
    return failed


def status(n=8):
    if not DB.exists():
        print("no nfl_lines.sqlite yet")
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
