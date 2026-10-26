#!/usr/bin/env python3
"""OFFICIAL NBA injury report — the authority on who is out, and the NEWS CLOCK.

The league publishes a game-dated PDF every 15 minutes at
    ak-static.cms.nba.com/referee/injury/Injury-Report_YYYY-MM-DD_HH_MM{AM,PM}.pdf
about 4 seconds after each :00/:15/:30/:45 mark (probed 2026-10-22: 40 reports in 10 hours,
Last-Modified 16:00:04 for the 16:00 report). Same layout as the WNBA's, so the WNBA parser
is reused unchanged (wnba_injury_report._parse, with its hyphen-wrap and page-footer fixes),
handed the NBA's 30 team names.

WHY THE OFFICIAL REPORT. The WNBA engine runs on it alone (user, 2026-07-28: "the minute a new
report comes out that says the player won't play then they are out"): ESPN disagreed with the
league on 4 of 22 audited rows, always over-reporting Out. An official Out is bound to a
specific game, so it is confirmed for that game by construction.

WHY A NEWS CLOCK. The WNBA record's edge is partly SPEED — its bets beat the close 67% of the
time; bought at the close the same bets earned +11.5% instead of +20.2%. Measuring that for the
NBA needs the moment each ruling became public. Every report is stored with its publish time,
so "first published Out" per (game, player) is exact to the 15-minute mark.

⚠️ NAMES ARE RESOLVED AGAINST THE TEAM'S ROSTER, because the PDF's text splits multi-word
surnames: "Lively II, Dereck" arrives as `Lively` `II,` `Dereck`, and the WNBA parser (which
takes the word before the comma as the surname) yields "Dereck II" — a name matching nobody,
for a player who was OUT that day. Each parsed row is matched within ITS team's current roster
(stats.nba.com player index): first name at the start, the comma word at the end, UNIQUE only.
That recovers Lively II / Jackson Jr. / Jones Garcia and gives the NBA person id directly.
Anything unresolved is stored with pid NULL and counted — never guessed.

    python nba_injury_report.py              # fetch any new report, store it, print summary
    python nba_injury_report.py --verify N   # parse the last N published reports, check every
                                             # matchup's two teams were found
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import nba_rosters as R
import wnba_injury_report as W

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_news.sqlite"
ET = ZoneInfo("America/New_York")
# AMENDMENT 15: Doubtful is an absence. Every trigger and speed-layer check reads this, not "Out".
ABSENT = ("Out", "Doubtful")
ABSENT_SQL = "status IN ('Out', 'Doubtful')"
URL = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_{d}_{h:02d}_{m:02d}{ap}.pdf"
TEAMS = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR", "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}
DDL = """
CREATE TABLE IF NOT EXISTS reports (
    mark TEXT PRIMARY KEY, url TEXT, published_at TEXT, fetched_at TEXT,
    n_rows INTEGER, n_matchups INTEGER, unresolved INTEGER, missing_teams TEXT);
CREATE TABLE IF NOT EXISTS snapshots (
    mark TEXT, published_at TEXT, game_date TEXT, matchup TEXT, team TEXT,
    pid INTEGER, player TEXT, status TEXT, reason TEXT);
CREATE INDEX IF NOT EXISTS snap_game ON snapshots (game_date, team, pid, mark);
CREATE TABLE IF NOT EXISTS not_submitted (mark TEXT, game_date TEXT, team TEXT);
"""


def fold(s):
    n = unicodedata.normalize("NFKD", s or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", n.lower()).split())


def marks(now_et, back=8):
    """(mark_iso, url) for the 15-minute grid, newest first."""
    t = now_et.replace(minute=(now_et.minute // 15) * 15, second=0, microsecond=0)
    for _ in range(back):
        h12, ap = t.hour % 12 or 12, ("AM" if t.hour < 12 else "PM")
        yield (t.strftime("%Y-%m-%dT%H:%M"),
               URL.format(d=t.strftime("%Y-%m-%d"), h=h12, m=t.minute, ap=ap))
        t -= dt.timedelta(minutes=15)


def parse(pdf_bytes):
    """wnba_injury_report._parse with the NBA's teams. Returns (rows, submitted, matchups)."""
    saved = W.TEAMS
    W.TEAMS = TEAMS
    try:
        rows, submitted = W._parse(pdf_bytes)
    finally:
        W.TEAMS = saved
    matchups = {(r["game_date"], r["matchup"]) for r in rows if r.get("matchup")}
    return rows, submitted, matchups


SFX = {"jr", "sr", "ii", "iii", "iv", "v"}


class Resolver:
    """Parsed 'First LastWord' -> NBA person id, within one team's current roster."""

    def __init__(self, index):
        self.by_team = {}
        for pid, (tri, name, _pos) in index.items():
            self.by_team.setdefault(tri, []).append((pid, name, fold(name)))

    def __call__(self, parsed_name, tri):
        f = fold(parsed_name).split()
        if not f:
            return None, None
        first, lastw = f[0], f[-1]
        pool = self.by_team.get(tri, [])
        exact = [(p, n) for p, n, c in pool if c == " ".join(f)]
        if len(exact) == 1:
            return exact[0]
        hit = [(p, n) for p, n, c in pool
               if c.split()[:1] == [first] and c.split()[-1:] == [lastw]]
        if len(hit) == 1:
            return hit[0]
        # SUFFIX AFTER THE COMMA: the league writes "Udeh, Jr., Ernest", which parses as
        # "Jr., Ernest Udeh" (2026-10-22). Drop suffix words on both sides and match first + last.
        ns = [t for t in f if t not in SFX]
        if len(ns) >= 2:
            hit = [(p, n) for p, n, c in pool
                   if [t for t in c.split() if t not in SFX][:1] == ns[:1]
                   and [t for t in c.split() if t not in SFX][-1:] == ns[-1:]]
            if len(hit) == 1:
                return hit[0]
        return None, None


def published_at(url):
    r = requests.head(url, timeout=10)
    if r.status_code != 200:
        return None
    lm = r.headers.get("Last-Modified")
    return (dt.datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S %Z")
            .replace(tzinfo=dt.timezone.utc).isoformat() if lm else None)


def ingest(mark, url, pub, index, con):
    """Fetch, parse, resolve and store one report. Returns a summary dict."""
    b = requests.get(url, timeout=30)
    b.raise_for_status()
    rows, submitted, matchups = parse(b.content)
    resolve = Resolver(index)
    out, unresolved = [], []
    for r in rows:
        pid, name = resolve(r["player"], r["team"])
        if pid is None:
            unresolved.append(f"{r['player']} ({r['team']})")
        out.append((mark, pub, r["game_date"], r["matchup"], r["team"], pid,
                    name or r["player"], r["status"], r["reason"]))
    # A matchup's team missing from the PDF is a MIS-ASSIGNMENT RISK only if that matchup also has
    # rows we could not resolve: an unrecognised team header leaves its players under the previous
    # team's name, where the roster match fails. A team with nobody to list is simply OMITTED by the
    # league (MIL, 2026-10-23) — benign, and not recorded as missing.
    unres_mu = {(r["game_date"], r["matchup"]) for r, o in zip(rows, out) if o[5] is None}
    missing = []
    for gdate, mu in sorted(matchups):
        for tri in mu.split("@"):
            if f"{gdate}|{tri}" not in submitted and (gdate, mu) in unres_mu:
                missing.append(f"{gdate} {tri}")
    con.execute("DELETE FROM snapshots WHERE mark=?", (mark,))
    con.execute("DELETE FROM not_submitted WHERE mark=?", (mark,))
    con.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)", out)
    con.executemany("INSERT INTO not_submitted VALUES (?,?,?)",
                    [(mark, *k.split("|")) for k, v in submitted.items() if v is False])
    con.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?,?)",
                (mark, url, pub, dt.datetime.now(dt.timezone.utc).isoformat(), len(out),
                 len(matchups), len(unresolved), ",".join(missing)))
    con.commit()
    return {"mark": mark, "rows": len(out), "matchups": len(matchups),
            "unresolved": unresolved, "missing_teams": missing,
            "out": sum(1 for o in out if o[7] == "Out")}


def fetch_new(now=None, con=None):
    """Store any published report not yet stored (newest first, last 2 hours).
    Returns [summary] for reports ingested this call."""
    now = now or dt.datetime.now(dt.timezone.utc)
    own = con is None
    con = con or sqlite3.connect(DB, timeout=60)
    con.executescript(DDL)
    have = {m for (m,) in con.execute("SELECT mark FROM reports")}
    index, _ = R.player_index(now.astimezone(ET).date().isoformat())
    done = []
    for mark, url in marks(now.astimezone(ET)):
        if mark in have:
            break                                  # everything older is already stored
        pub = published_at(url)
        if pub is None:
            continue                               # not published (yet) at this mark
        done.append(ingest(mark, url, pub, index, con))
    if own:
        con.close()
    return done


def current(game_date, con=None):
    """{pid: (name, team, status, first_published_at_of_this_status)} from the NEWEST stored
    report that lists game_date — the engine's view of who is out tonight, with news times."""
    own = con is None
    con = con or sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    m = con.execute("SELECT MAX(mark) FROM snapshots WHERE game_date=?", (game_date,)).fetchone()[0]
    out = {}
    if m:
        for pid, name, team, status in con.execute(
                "SELECT pid, player, team, status FROM snapshots WHERE mark=? AND game_date=? "
                "AND pid IS NOT NULL", (m, game_date)):
            first = con.execute(
                "SELECT MIN(published_at) FROM snapshots WHERE game_date=? AND pid=? AND status=?",
                (game_date, pid, status)).fetchone()[0]
            out[pid] = (name, team, status, first)
    if own:
        con.close()
    return out, m


def verify(n):
    """Parse the last n published reports without storing; check structure end to end."""
    now = dt.datetime.now(dt.timezone.utc)
    index, _ = R.player_index(now.astimezone(ET).date().isoformat())
    resolve = Resolver(index)
    bad = 0
    for mark, url in list(marks(now.astimezone(ET), back=n * 2)):
        if n <= 0:
            break
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            continue
        n -= 1
        rows, submitted, matchups = parse(r.content)
        miss = [f"{g} {t}" for g, mu in sorted(matchups) for t in mu.split("@")
                if f"{g}|{t}" not in submitted]
        unres = [f"{x['player']} ({x['team']})" for x in rows
                 if resolve(x["player"], x["team"])[0] is None]
        bad += bool(miss)
        print(f"{mark}: {len(rows):3d} rows · {len(matchups):2d} matchups · teams missing "
              f"{miss or 0} · unresolved {len(unres)}" + (f" {unres[:4]}" if unres else ""))
    return bad == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", type=int, metavar="N")
    a = ap.parse_args()
    if a.verify:
        sys.exit(0 if verify(a.verify) else 1)
    for s in fetch_new():
        print(f"nba report {s['mark']}: {s['rows']} rows, {s['out']} Out, {s['matchups']} "
              f"matchups, unresolved {len(s['unresolved'])}"
              + (f" {s['unresolved'][:5]}" if s["unresolved"] else "")
              + (f" !! TEAMS MISSING {s['missing_teams']}" if s["missing_teams"] else ""))
