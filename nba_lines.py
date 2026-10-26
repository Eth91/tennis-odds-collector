#!/usr/bin/env python3
"""NBA prop line collector — FanDuel + DraftKings -> nba_lines.sqlite. MAC-ONLY.

WHY THIS EXISTS. Until 2026-10-22 nothing collected NBA prop lines anywhere: the VM's
lines DB held only WNBA, Actions ran `dk_collect.py --wnba` only (its NBA steps deleted,
the comments left behind), and the Mac's fanduel_props.sqlite had no NBA rows. nba_flags
had nothing to price against and printed "0 flags" through all of it.

WHERE. Both books answer from this Mac (probed 2026-10-22): FanDuel's sbapi over plain
`requests` (urllib has no CA certs here), DraftKings via curl_cffi impersonation (Akamai
blocks the Oracle VM by design). The NBA engine is Mac-only for the same reason — the slate
and rosters come from cdn.nba.com, which 403s the VM.

WHAT IT STORES — three tables, because they answer three different questions:
  board   the CURRENT pre-game board, one row per (book, player, stat, line, side), replaced
          per book on every SUCCESSFUL fetch. What nba_flags prices against.
  quotes  an append-only CHANGE LOG: a row whenever a rung is first seen, its price moves, or it
          is pulled (odds NULL — logged only on a fully successful fetch).
          The 2.0M-row history (basketball_nba_odds_hist.sqlite) is tip-snapshots only, so it
          cannot measure CLV or the news-window move. This can, from 2026-10-22 forward.
  cycles  one row per book per run: status, row counts, match/resolution coverage.

IDENTITY. Every line is resolved to an NBA person id, scoped to the two teams in that game
(~30 players), never league-wide: surname matching league-wide is how `Williams` hit 14
players and `a|brown` merged two receivers (reference_name_key_collapse). Exact folded name
first, then the same with suffixes stripped, then first-initial + surname — each only if it
is UNIQUE within the two rosters. Anything else stays pid=NULL and is counted, never guessed.

A book whose fetch FAILS leaves its board untouched (the engine's freshness check ages it
out) and makes this exit 2. A partial FanDuel fetch is counted, not hidden.

    python nba_lines.py            # collect both books (NBA_BOOKS overrides the default set)
    python nba_lines.py --status   # print the last cycles, write nothing
    python nba_lines.py --snapshot dk PATH   # fetch DraftKings only and write a snapshot file

WHERE IT RUNS SINCE 2026-10-23 (NBA_SPEED_PREREG.md amendment 4). The engine runs on the always-on
Oracle VM, which reaches FanDuel and cdn.nba.com (with curl_cffi impersonation) but NOT DraftKings.
DraftKings reaches the VM as a SNAPSHOT FILE: the Mac (or any host DraftKings serves) runs
`--snapshot dk`, ships the file, and the VM ingests it through this same cycle when
NBA_DK_SNAPSHOT names it. The snapshot keeps its own fetch time, so the board and the change log
date DraftKings' prices to when DraftKings showed them, not when they arrived. A snapshot older
than DK_SNAPSHOT_MAX_AGE_S is STALE: the board is left untouched (nba_flags ages it out), it is
logged, and it is NOT a failure, because DraftKings is the secondary book.
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
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import nba_rosters as R

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_lines.sqlite"
ET = ZoneInfo("America/New_York")
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}
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


def fold(s):
    n = unicodedata.normalize("NFKD", s or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", n.lower()).split())


def _nosfx(f):
    return " ".join(t for t in f.split() if t not in SUFFIX)


def _nick_key(s):
    """Last word of a team's name: 'New York Knicks' / 'NY Knicks' / 'Knicks' -> 'knicks';
    'Portland Trail Blazers' / 'POR Trail Blazers' -> 'blazers'."""
    w = fold(s).split()
    return w[-1] if w else ""


# ── fetchers — each returns (rows, detail) or raises ─────────────────────────────

LAST_FD_PAGE = {}     # the league page fetch_fd downloaded last (amendment 25: its game markets)
GAME_MARKETS = {"MONEY_LINE": "moneyline", "MATCH_HANDICAP_(2-WAY)": "spread", "TOTAL_POINTS_(OVER/UNDER)": "total"}


def fd_game_lines(page):
    """[(event, market, runner, line, decimal)] — FanDuel's main game markets (moneyline, spread,
    total) from the league page's attachments. Open markets only."""
    att = page.get("attachments", {})
    events = att.get("events", {})
    out = []
    for m in att.get("markets", {}).values():
        kind = GAME_MARKETS.get(m.get("marketType"))
        name = (events.get(str(m.get("eventId"))) or {}).get("name") or ""
        if not kind or m.get("marketStatus") != "OPEN" or "@" not in name:
            continue
        for r in m.get("runners", []):
            am = ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOddsInt")
            if am is None:
                continue
            out.append((name, kind, r.get("runnerName") or "", r.get("handicap"),
                        round(1 + (am / 100 if am > 0 else 100 / -am), 4)))
    return out


def store_game_lines(con, page, upcoming, ts, book="fd"):
    """Write the page's game lines that CHANGED, for games not yet started (match_event only knows
    those). Sides: home / away (spread, moneyline), over / under (total). Returns rows written."""
    n = 0
    for event, kind, runner, line, odds in fd_game_lines(page):
        g = match_event(event, upcoming)
        if g is None:
            continue
        rk = _nick_key(runner)
        side = ("home" if rk == _nick_key(g["home_nick"]) else "away" if rk == _nick_key(g["away_nick"])
                else fold(runner))
        last = con.execute("SELECT line, odds FROM game_lines WHERE gid=? AND book=? AND market=? AND side=? "
                           "ORDER BY seen_at DESC LIMIT 1", (g["gid"], book, kind, side)).fetchone()
        if last == (line, odds):
            continue
        con.execute("INSERT INTO game_lines VALUES (?,?,?,?,?,?,?,?)",
                    (ts, book, g["gid"], g["utc"], kind, side, line, odds))
        n += 1
    return n


def fetch_fd(event_filter=None):
    """FanDuel via fd_collect's parser (the NBA branch shares WNBA's market naming), with a
    requests-based getter because urllib has no CA certs on this Mac. Every failed GET is
    COUNTED: collect_page swallows per-event failures, which would otherwise read as a
    smaller slate. `event_filter(name)` limits the fetch to some events (the per-game refresh)."""
    import requests
    import fd_collect as FD
    s = requests.Session()
    s.headers.update({"User-Agent": FD.UA, "Accept": "application/json"})
    fails = Counter()

    def get(url):
        try:
            r = s.get(url, timeout=25)
            r.raise_for_status()
            j = r.json()
            if "content-managed-page" in url:
                LAST_FD_PAGE["page"] = j
            return j
        except Exception:
            fails["event" if "event-page" in url else "page"] += 1
            raise
    FD.get = get
    raw = FD.collect_page("nba", "nba",
                          lambda n: "@" in n and (event_filter is None or event_filter(n)))
    rows = [(r[1], r[2], r[3], float(r[4]), r[5], float(r[6])) for r in raw]
    return rows, (f"failed GETs {dict(fails)}" if fails else "")


def fetch_dk():
    import dk_collect as D
    raw = D.collect_league("nba", D.LEAGUES["nba"])
    h = D.LAST.get("nba", {})
    if h.get("subfail"):
        detail = f"partial: {h['subfail']} subcategory fetch(es) failed"
    elif not h.get("mapped"):
        detail = "no player-prop subcategories posted"
    else:
        detail = ""
    return [(r[1], r[2], r[3], float(r[4]), r[5], float(r[6])) for r in raw], detail


class Stale(Exception):
    """A book's snapshot is too old to use: logged, board untouched, not a failure."""


DK_SNAPSHOT = os.environ.get("NBA_DK_SNAPSHOT")
DK_SNAPSHOT_MAX_AGE_S = 600


def fetch_dk_snapshot():
    """DraftKings from a pushed snapshot file -> (rows, detail, fetched_at)."""
    p = Path(DK_SNAPSHOT)
    if not p.exists():
        raise Stale(f"no snapshot at {p}")
    snap = json.loads(p.read_text())
    at = snap["fetched_at"]
    age = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
           - dt.datetime.fromisoformat(at)).total_seconds()
    if age > DK_SNAPSHOT_MAX_AGE_S:
        raise Stale(f"snapshot {age / 60:.0f} min old (fetched {at}; sender asleep?)")
    return [tuple(r) for r in snap["rows"]], snap.get("detail", ""), at


def write_snapshot(book, path):
    """Fetch one book here and write {fetched_at, rows, detail} atomically (the sender side)."""
    at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat()
    rows, detail = BOOKS[book]()
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps({"book": book, "fetched_at": at, "rows": rows, "detail": detail}))
    tmp.replace(path)
    print(f"[{at}] {book} snapshot -> {path}: {len(rows)} rows" + (f" · {detail}" if detail else ""))


BOOKS = {"fd": fetch_fd, "dk": fetch_dk_snapshot if DK_SNAPSHOT else fetch_dk}
DEFAULT_BOOKS = tuple(b for b in os.environ.get("NBA_BOOKS", "fd,dk").split(",") if b)


# ── matching ─────────────────────────────────────────────────────────────────────

def match_event(event, upcoming):
    """Book event 'Away @ Home' -> the schedule game (not yet started) with those nicknames."""
    if "@" not in event:
        return None
    a, h = (_nick_key(x) for x in event.split("@", 1))
    hits = [g for g in upcoming if _nick_key(g["away_nick"]) == a and _nick_key(g["home_nick"]) == h]
    return min(hits, key=lambda g: g["utc"]) if hits else None


class Resolver:
    """Book player name -> NBA person id, scoped to one game's two current rosters."""

    def __init__(self, cur_team, name):
        self.by_team = defaultdict(list)
        for pid, tri in cur_team.items():
            self.by_team[tri].append((pid, fold(name.get(pid, ""))))
        self.cache = {}

    def __call__(self, player, home, away):
        k = (player, home, away)
        if k in self.cache:
            return self.cache[k]
        pool = self.by_team[home] + self.by_team[away]
        f = fold(player)
        pid = None
        for test in (lambda c: c == f,
                     lambda c: _nosfx(c) == _nosfx(f),
                     lambda c: (_nosfx(c).split()[-1:] == _nosfx(f).split()[-1:]
                                and c[:1] == f[:1])):
            hit = {p for p, c in pool if c and test(c)}
            if len(hit) == 1:
                pid = hit.pop()
                break
            if len(hit) > 1:                   # ambiguous at this tier: refuse, never guess
                break
        self.cache[k] = pid
        return pid


# ── one cycle ────────────────────────────────────────────────────────────────────

def cycle(books=None, only_gids=None):
    """One refresh. `only_gids` (amendment 12): FanDuel is fetched and written for THOSE games only.
    That covers the event list plus one event's tabs, ~2 s instead of the ~12 s full board, for the
    trigger path. Every write is scoped to those games (board replace, change log, pulled rungs), so
    the other games' rows and quotes are untouched, and the cycle is logged as status 'game' so it
    never reads as a full FanDuel refresh. Other books run as usual."""
    books = books or DEFAULT_BOOKS
    now = dt.datetime.now(dt.timezone.utc)
    ts = now.replace(microsecond=0, tzinfo=None).isoformat()
    sched = R.schedule()                                  # raises R.Blind — caller handles
    boxes, _ = R.season_boxes(sched)
    today_et = now.astimezone(ET).date().isoformat()
    index, inote = R.player_index(today_et)               # raises R.Blind if unusable
    apps, cur_team, name = R.state(today_et, boxes, index=index)
    upcoming = [g for g in sched if g["status"] == 1]
    soon = [g for g in upcoming
            if dt.datetime.fromisoformat(g["utc"].replace("Z", "+00:00")) - now
            <= dt.timedelta(hours=24)]
    resolve = Resolver(cur_team, name)

    con = sqlite3.connect(DB, timeout=60)
    con.executescript(DDL)
    report, failed = [], []
    for book in books:
        t0 = time.time()
        scope = set(only_gids) if (only_gids and book == "fd") else None
        try:
            if scope:
                keys = {(_nick_key(g["away_nick"]), _nick_key(g["home_nick"]))
                        for g in upcoming if g["gid"] in scope}
                got = fetch_fd(lambda n: tuple(_nick_key(x) for x in n.split("@", 1)) in keys)
            else:
                got = BOOKS[book]()
            rows, detail = got[0], got[1]
            bts = got[2] if len(got) > 2 else ts          # a snapshot keeps its own fetch time
            if book == "fd" and LAST_FD_PAGE.get("page"):  # amendment 25: game lines, never fatal
                try:
                    store_game_lines(con, LAST_FD_PAGE.pop("page"), upcoming, ts)
                except Exception as e:                                   # noqa: BLE001
                    report.append(f"game lines: {type(e).__name__}")
        except Stale as e:
            con.execute("INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?)",
                        (ts, book, "stale", 0, 0, 0, 0, 0, str(e)[:200]))
            report.append(f"{book}=stale ({e}) — board left untouched")
            continue
        except Exception as e:
            failed.append(book)
            msg = f"{type(e).__name__}: {str(e)[:90]}"
            con.execute("INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?)",
                        (ts, book, "error", 0, 0, 0, 0, 0, msg))
            report.append(f"{book}=error ({msg}) — board left untouched")
            continue
        # ONE PRICE PER RUNG. A book posts the same bet twice — the O/U market's over 14.5 and
        # the "15+" milestone are one wager at two slightly different prices (120 FanDuel and
        # 131 DraftKings rungs on 2026-10-22). Keeping whichever came last made the board flip
        # between them, and every flip logged a fake price move (cycle 2 "moved" 251 rungs in
        # 90s; none had moved). Keep the BEST over/under per rung — the one you would take.
        best = {}
        for r in rows:
            k = (r[1], r[2], r[3], r[4])
            if k not in best or r[5] > best[k][5]:
                best[k] = r
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
            # TEAM MARKETS ARE NOT PLAYER PROPS. FanDuel posts team totals in the same
            # "{name} - Points" shape the shared parser reads as a player prop, so on 2026-10-22
            # "Denver Nuggets" / "Cleveland Cavaliers" arrived as players with points lines. They
            # never resolve to a person id (the engine ignored them), but they polluted the board
            # and the quote log. Drop any row whose "player" is one of the two teams in the event.
            if any(fold(player).endswith(fold(n)) for n in (g["home_nick"], g["away_nick"]) if n):
                team_rows += 1
                continue
            pid = resolve(player, g["home"], g["away"])
            if pid is None:
                unresolved.add(player)
            board.append((book, bts, g["gid"], g["utc"], event, g["home"], g["away"],
                          pid, player, stat, line, side, odds))
        if scope:                                      # per-game refresh: only these games
            board = [b for b in board if b[2] in scope]
            qmarks = ",".join("?" * len(scope))
            prev_rows = {(r[0], r[1], r[2], r[3]): r for r in con.execute(
                "SELECT player, stat, line, side, odds, gid, tip_utc, pid FROM board WHERE book=? "
                f"AND gid IN ({qmarks})", (book, *sorted(scope)))}
        else:
            prev_rows = {(r[0], r[1], r[2], r[3]): r for r in con.execute(
                "SELECT player, stat, line, side, odds, gid, tip_utc, pid FROM board WHERE book=?",
                (book,))}
        prev = {k: r[4] for k, r in prev_rows.items()}
        changed = [(bts, b[0], b[2], b[3], b[7], b[8], b[9], b[10], b[11], b[12])
                   for b in board if prev.get((b[8], b[9], b[10], b[11])) != b[12]]
        if scope:
            con.execute(f"DELETE FROM board WHERE book=? AND gid IN ({qmarks})", (book, *sorted(scope)))
        else:
            con.execute("DELETE FROM board WHERE book=?", (book,))
        con.executemany("INSERT OR REPLACE INTO board VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", board)
        con.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", changed)
        players = {b[8] for b in board}
        status = ("partial" if detail.startswith(("partial", "failed")) else
                  "ok" if board else "no_lines")
        # PULLED RUNGS. The change log must say when a rung STOPPED being offered, or the close
        # cannot be reconstructed: a line taken down before tip would read as still open at its
        # last price. A pulled rung is logged with odds NULL — but ONLY on a fully successful
        # fetch: on a partial one, a missing rung may just be a failed sub-request.
        if status == "ok":
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
                    (bts, book, "game" if scope else status, len(board), len(events),
                     len(events) - len(unmatched),
                     len(players) - len(unresolved), len(unresolved), detail))
        covered = {gm[e]["gid"] for e in events if gm[e]}
        report.append(
            f"{book}={status} rows={len(board)} (+{len(changed)} quote changes, "
            f"{len(gone)} pulled) "
            f"games={len(covered)} [{len({g['gid'] for g in soon} & covered)}/{len(soon)} of the "
            f"next 24h] players={len(players)} unresolved={len(unresolved)} "
            f"{time.time() - t0:.0f}s" + (f" · {detail}" if detail else ""))
        if unresolved:
            report.append(f"   {book} unresolved names: {sorted(unresolved)[:8]}")
    con.commit()
    con.close()
    print(f"[{ts}] nba lines -> {DB.name}" + (f"  !! {inote}" if inote else ""))
    for line in report:
        print("  NBALINES " + line if not line.startswith("   ") else line)
    return failed


def status(n=8):
    if not DB.exists():
        print("no nba_lines.sqlite yet")
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
    try:
        bad = cycle(tuple(a.book) if a.book else None)
    except R.Blind as e:
        print(f"nba lines: BLIND — cdn.nba.com unreachable ({e}); cannot match events to games")
        sys.exit(2)
    sys.exit(2 if bad else 0)
