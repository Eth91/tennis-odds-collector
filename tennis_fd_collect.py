#!/usr/bin/env python3
"""🎾 tennis_fd_collect — every FanDuel tennis market, every pass. ATP / WTA / everything else.

WHY GENERIC. FanDuel exposes up to 43 market types on a deep pre-match tennis board, and the set is
not stable: it varies by tour, by round, by how close to start time we are, and FanDuel adds
products without warning. So NOTHING is hardcoded. One row per (market, runner) with the market
type carried as data, which means a market family that appears next month is captured the first
time it is seen instead of being silently dropped by a schema that never heard of it.

TOUR FILTER: the ask was ATP and WTA. Everything tennis is stored anyway and TAGGED by tour,
because filtering at read time is free and un-collected data is gone forever - and ITF turned out
to carry the largest set-shape gap of any tier (+0.1238 against ATP's +0.0918), so discarding it at
write time would have thrown away the most interesting tier.

THE TAB GOTCHA THIS IS BUILT AROUND. An unknown tab name does NOT error - FanDuel silently returns
the 6-market default. Two separate analysis passes concluded "no deep boards exist" because they
asked for tab=all, which is not a real tab. The working tab is `popular`. This collector therefore
ASSERTS depth: if a pass banks markets but almost none of them are deep, it says so loudly rather
than quietly recording a shallow board forever.

STORAGE. WAL + busy_timeout set BEFORE the journal switch (the ordering that broke golf_lines and
golf_moves), and INSERT OR IGNORE on a natural key so re-running a pass is idempotent.
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "tennis_fd.sqlite"
AK = "FhMFpcPWXMeyZxOx"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
B = "https://sbapi.ny.sportsbook.fanduel.com/api"
TZ = "&timezone=America%2FNew_York"
EVENT_TYPE_TENNIS = 2          # Betfair taxonomy, inherited by Flutter. NOT customPageId=tennis.

DDL = """
CREATE TABLE IF NOT EXISTS fd_tennis(
  collected_at TEXT NOT NULL,
  event_id     TEXT NOT NULL,
  event_name   TEXT,
  competition  TEXT,
  tour         TEXT,
  best_of      INTEGER,
  start_time   TEXT,
  market_id    TEXT NOT NULL,
  market_type  TEXT,
  market_name  TEXT,
  runner_id    TEXT NOT NULL,
  runner_name  TEXT,
  handicap     REAL,
  odds         REAL,
  PRIMARY KEY (collected_at, event_id, market_id, runner_id)
);
CREATE INDEX IF NOT EXISTS ix_fd_event  ON fd_tennis(event_id, market_type);
CREATE INDEX IF NOT EXISTS ix_fd_type   ON fd_tennis(market_type, collected_at);
CREATE INDEX IF NOT EXISTS ix_fd_start  ON fd_tennis(start_time);
-- CHANGE-ONLY storage needs a cheap "what did we last see" lookup, and a last_seen stamp so a
-- price that never moves is distinguishable from a market that vanished.
CREATE TABLE IF NOT EXISTS fd_current(
  event_id TEXT NOT NULL, market_id TEXT NOT NULL, runner_id TEXT NOT NULL,
  odds REAL, handicap REAL, last_seen TEXT,
  PRIMARY KEY (event_id, market_id, runner_id)
);
"""


def get(u, timeout=30):
    r = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=timeout))


def odds_of(runner):
    t = (runner.get("winRunnerOdds") or {}).get("trueOdds")
    if isinstance(t, dict):
        return (t.get("decimalOdds") or {}).get("decimalOdds")
    return None


SLAMS = ("US OPEN", "AUSTRALIAN OPEN", "WIMBLEDON", "FRENCH OPEN", "ROLAND GARROS")


def tour_of(competition, event_name):
    """FanDuel does NOT say ATP/WTA on Grand Slam boards - it says Men's / Women's."""
    s = ("%s %s" % (competition or "", event_name or "")).upper()
    if "WOMEN" in s or "LADIES" in s or "WTA" in s:
        return "WTA"
    if "ATP" in s or "MEN" in s:                 # after WOMEN, since WOMEN contains MEN
        return "ATP"
    if "ITF" in s:
        return "ITF"
    if "CHALLENGER" in s:
        return "ATP"
    return "OTHER"


def best_of_for(competition, event_name):
    """Men's Grand Slam is best-of-FIVE. Everything else is best-of-three.

    Stored rather than re-derived downstream: applying best-of-3 maths to Men's Slam matches once
    already manufactured a convincing ATP/WTA split that was pure format artifact.
    """
    s = ("%s %s" % (competition or "", event_name or "")).upper()
    if tour_of(competition, event_name) == "ATP" and any(x in s for x in SLAMS):
        return 5
    return 3


def open_db():
    con = sqlite3.connect(str(DB), timeout=60)
    con.execute("PRAGMA busy_timeout=60000")      # MUST precede the WAL switch
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass                                       # already WAL, or a reader holds it
    con.executescript(DDL)
    con.commit()
    return con


def main():
    ts = dt.datetime.utcnow().isoformat(timespec="seconds")
    try:
        board = get("%s/content-managed-page?page=SPORT&eventTypeId=%d&pbHorizontal=false&_ak=%s%s"
                    % (B, EVENT_TYPE_TENNIS, AK, TZ))
    except Exception as e:                                              # noqa: BLE001
        print("FATAL: board fetch failed: %s" % str(e)[:120])
        return 2
    att = board.get("attachments") or {}
    evs = att.get("events") or {}
    comps = {str(k): str(v.get("name")) for k, v in (att.get("competitions") or {}).items()}
    matches = [v for v in evs.values() if " v " in str(v.get("name", ""))]
    if not matches:
        print("FATAL: board returned %d events but no head-to-head matches — shape changed?"
              % len(evs))
        return 2

    con = open_db()
    rows = 0
    seen_now = 0
    deep = 0
    per_type = Counter()
    per_tour = Counter()
    errs = 0
    for v in matches:
        eid = str(v.get("eventId"))
        comp = comps.get(str(v.get("competitionId")), "")
        tour = tour_of(comp, v.get("name"))
        bo = best_of_for(comp, v.get("name"))
        try:
            # tab=popular is the ONLY tab that returns the deep board; an unknown tab name
            # silently degrades to the 6-market default instead of erroring.
            e = get("%s/event-page?eventId=%s&tab=popular&_ak=%s%s" % (B, eid, AK, TZ))
        except Exception:                                               # noqa: BLE001
            errs += 1
            continue
        mk = (e.get("attachments") or {}).get("markets") or {}
        if len(mk) >= 20:
            deep += 1
        batch = []
        cur = {}
        for r in con.execute("SELECT market_id, runner_id, odds FROM fd_current WHERE event_id=?",
                             (eid,)):
            cur[(r[0], r[1])] = r[2]
        touched = []
        for mid, m in mk.items():
            mtype = str(m.get("marketType"))
            for r in (m.get("runners") or []):
                o = odds_of(r)
                if o is None:
                    continue
                rid = str(r.get("selectionId") or r.get("runnerName"))
                touched.append((eid, str(mid), rid, float(o), r.get("handicap"), ts))
                prev = cur.get((str(mid), rid))
                # WRITE ONLY ON CHANGE. First sighting (prev is None) always writes, so the
                # series is reconstructable: an unchanged price is the last row before your
                # timestamp of interest.
                if prev is not None and abs(prev - float(o)) < 1e-9:
                    continue
                batch.append((ts, eid, str(v.get("name")), comp, tour, bo, str(v.get("openDate")),
                              str(mid), mtype, str(m.get("marketName")), rid,
                              str(r.get("runnerName")), r.get("handicap"), float(o)))
                per_type[mtype] += 1
            per_tour[tour] += 1
        if batch:
            con.executemany("INSERT OR IGNORE INTO fd_tennis VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            batch)
            rows += len(batch)
        if touched:
            con.executemany(
                "INSERT INTO fd_current(event_id,market_id,runner_id,odds,handicap,last_seen) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(event_id,market_id,runner_id) DO UPDATE SET "
                "odds=excluded.odds, handicap=excluded.handicap, last_seen=excluded.last_seen",
                touched)
            seen_now += len(touched)
        con.commit()
        time.sleep(0.18)

    # SCHEMA GUARD. A column-order mismatch does not raise - SQLite accepts 14 values into 14
    # columns whether or not they are the RIGHT 14. This asserts the shape of what we stored:
    # a market_type is an upper-case enum, never a numeric market id.
    bad = con.execute("SELECT COUNT(*) FROM fd_tennis WHERE market_type GLOB '*[0-9].[0-9]*' "
                      "OR market_type != UPPER(market_type)").fetchone()[0]
    tot_rows = con.execute("SELECT COUNT(*) FROM fd_tennis").fetchone()[0]
    if tot_rows and bad > 0.05 * tot_rows:
        print("ALERT: %d of %d rows have a market_type that is not an upper-case enum — the "
              "column order has drifted from the INSERT order" % (bad, tot_rows))
        con.close()
        return 2

    tot = con.execute("SELECT COUNT(*) FROM fd_tennis").fetchone()[0]
    con.close()

    print("tennis_fd_collect %s: %d matches, %d deep boards, %d quotes seen, %d CHANGED "
          "and written (%d total rows), %d fetch errors"
          % (ts, len(matches), deep, seen_now, rows, tot, errs))
    print("   by tour: %s" % dict(per_tour.most_common()))
    print("   top market types: %s" % dict(per_type.most_common(6)))

    # LOUD ASSERTIONS. Silence is how a collector rots: the tab gotcha produced a shallow board
    # that looked perfectly healthy, and a schema-shape change would produce zero rows forever.
    # rows==0 is NORMAL here once warm: it means no price moved this pass. The real failure
    # is seeing no QUOTES at all, which means the endpoint or the response shape changed.
    if seen_now == 0:
        print("ALERT: saw ZERO quotes across %d matches — endpoint or shape has changed"
              % len(matches))
        return 2
    if matches and deep == 0:
        print("ALERT: not one deep board in %d matches. Either every match is in-play, or the "
              "`popular` tab has been renamed and we are silently recording the 6-market default."
              % len(matches))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
