#!/usr/bin/env python3
"""Prediction markets (Kalshi) — a SHADOW collector for NBA player props, and the gap / money reports.

NBA_SPEED_PREREG.md amendment 20. User, 2026-10-24: "look for big money being put on the markets on
certain props or big discrepancies between the prediction markets and FanDuel."

Kalshi lists props as threshold contracts ("Jarrett Allen: 25+ points", floor_strike 24.5): a YES is a
FanDuel over at the same line. Every minute, every open prop market whose game has not tipped (and tips
within 36 h) is read from the public REST API (no key). A row is stored only when bid, ask or volume
changed, so the table is a change log, and per-minute volume deltas are the money flow.

NOTHING HERE FLAGS, PINGS OR CARDS. Three tests are registered (T1 agreement cell, T2 Kalshi leads FD,
T3 big money); a test that passes is wired by a later amendment, never by this module.

    python3 nba_pm.py --loop 60     # the collector (service nba-pm)
    python3 nba_pm.py --once        # one poll
    python3 nba_pm.py --gaps        # upcoming games: Kalshi fair vs FanDuel fair at the same line
    python3 nba_pm.py --money 30    # the biggest pre-game volume minutes in the last 30 min
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

HERE = Path(__file__).resolve().parent
ET = ZoneInfo("America/New_York")
DB = HERE / "nba_pm.sqlite"
LINES = HERE / "nba_lines.sqlite"
API = "https://api.elections.kalshi.com/trade-api/v2"
HEAD = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
SERIES = {"KXNBAPTS": "points", "KXNBAREB": "rebounds", "KXNBAAST": "assists", "KXNBA3PT": "threes",
          "KXNBAPRA": "pra"}
MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                      "NOV", "DEC"), 1)}
HORIZON_H = 36
MAX_SPREAD = 0.10                     # a fair price needs a real two-sided market (amendment 20)
DDL = """CREATE TABLE IF NOT EXISTS pm_quotes (seen_at TEXT, venue TEXT, ticker TEXT, event TEXT,
    game_date TEXT, team TEXT, pid INTEGER, player TEXT, stat TEXT, line REAL, bid REAL, ask REAL,
    last REAL, volume REAL, oi REAL, tip_utc TEXT, gid TEXT);
CREATE INDEX IF NOT EXISTS pm_q_ticker ON pm_quotes (ticker, seen_at);
CREATE INDEX IF NOT EXISTS pm_q_seen ON pm_quotes (seen_at)"""


def _f(m, k):
    try:
        return float(m.get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_market(m):
    """A Kalshi prop market -> dict, or None if it is not a player threshold contract we can read.
    KXNBAPTS-26OCT24BKNCLE-CLEJALLEN31-25: series · 2026-10-24 · BKN @ CLE · the player's team (CLE)."""
    series, _, rest = (m.get("ticker") or "").partition("-")
    if series not in SERIES or m.get("strike_type") != "greater" or m.get("floor_strike") is None:
        return None
    ev, _, who = rest.partition("-")
    if len(ev) != 13 or ev[2:5] not in MONTHS or not who:
        return None
    gd = dt.date(2000 + int(ev[:2]), MONTHS[ev[2:5]], int(ev[5:7])).isoformat()
    name = (m.get("title") or "").split(":")[0].strip()
    if not name:
        return None
    return {"ticker": m["ticker"], "event": m.get("event_ticker"), "game_date": gd, "away": ev[7:10],
            "home": ev[10:13], "team": who[:3], "player": name, "stat": SERIES[series],
            "line": float(m["floor_strike"]), "bid": _f(m, "yes_bid_dollars"), "ask": _f(m, "yes_ask_dollars"),
            "last": _f(m, "last_price_dollars"), "volume": _f(m, "volume_fp"), "oi": _f(m, "open_interest_fp"),
            "tip": None}               # set from the NBA schedule: Kalshi's occurrence_datetime is ~tip + 3 h


def with_tips(parsed, sched):
    """Tip times from the NBA schedule, keyed by (ET date, away, home). A market whose game is not on the
    schedule is dropped: without a tip we cannot tell pre-game from in-game."""
    tips = {(g["date_et"], g["away"], g["home"]): (g["utc"], g.get("gid")) for g in sched}
    out = []
    for p in parsed:
        t, gid = tips.get((p["game_date"], p["away"], p["home"]), (None, None))
        if t:
            out.append(dict(p, tip=t, gid=gid))
    return out


def resolve(p, index):
    """The NBA person id: the exact folded full name within the player's team, else within the two teams
    of the game. Never a surname guess (reference_name_key_collapse)."""
    from nba_news_watch import fold
    key = lambda n: " ".join(w for w in fold(n).split() if w not in ("jr", "sr", "ii", "iii", "iv"))
    want = key(p["player"])                            # "Jimmy Butler" == "Jimmy Butler III"; never a surname
    for teams in ((p["team"],), (p["away"], p["home"])):
        hits = [pid for pid, (t, n, _) in index.items() if t in teams and key(n) == want and " " in want]
        if len(hits) == 1:
            return hits[0]
    return None


def fetch(series):
    out, cur = [], None
    while True:
        params = {"series_ticker": series, "status": "open", "limit": 1000}
        if cur:
            params["cursor"] = cur
        r = requests.get(f"{API}/markets", params=params, headers=HEAD, timeout=30)
        r.raise_for_status()
        j = r.json()
        out += j.get("markets", [])
        cur = j.get("cursor")
        if not cur:
            return out


def _db(path=None):
    con = sqlite3.connect(path or DB, timeout=60)
    con.executescript(DDL)
    if "gid" not in {r[1] for r in con.execute("PRAGMA table_info(pm_quotes)")}:
        con.execute("ALTER TABLE pm_quotes ADD COLUMN gid TEXT")       # the FD quotes index leads with gid
    return con


def store(con, parsed, now, last):
    """Write the markets whose bid, ask or volume changed since `last` ({ticker: (bid, ask, volume)}).
    Pre-game only: a market at or after its tip is skipped. Returns the number written."""
    stamp = now.replace(microsecond=0, tzinfo=None).isoformat()
    n = 0
    for p in parsed:
        tip = dt.datetime.fromisoformat((p["tip"] or "").replace("Z", "+00:00")) if p["tip"] else None
        if not tip or tip <= now or tip > now + dt.timedelta(hours=HORIZON_H):
            continue
        key = (p["bid"], p["ask"], p["volume"])
        if last.get(p["ticker"]) == key:
            continue
        last[p["ticker"]] = key
        con.execute("INSERT INTO pm_quotes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (stamp, "kalshi", p["ticker"], p["event"], p["game_date"], p["team"], p.get("pid"),
                     p["player"], p["stat"], p["line"], p["bid"], p["ask"], p["last"], p["volume"], p["oi"],
                     tip.replace(tzinfo=None).isoformat(), p.get("gid")))
        n += 1
    con.commit()
    return n


def poll(con, last, index, sched, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    parsed, errs = [], []
    for s in SERIES:
        try:
            parsed += [p for p in (parse_market(m) for m in fetch(s)) if p]
        except Exception as e:                                           # noqa: BLE001
            errs.append(f"{s}: {type(e).__name__}")
    parsed = with_tips(parsed, sched)
    for p in parsed:
        p["pid"] = resolve(p, index)
    return store(con, parsed, now, last), len(parsed), errs


def loop(interval=60):
    import nba_rosters as R
    con, last, index, day, sched, sched_at = _db(), {}, {}, None, [], 0.0
    while True:
        t0 = time.time()
        today = dt.datetime.now(ET).date().isoformat()           # the slate day, as player_index expects
        try:
            if today != day:                                 # rosters change; refresh once a day
                index, _ = R.player_index(today)
                day = today
            if time.time() - sched_at > 1800:                # tip times: refresh every 30 min
                sched, sched_at = R.schedule(), time.time()
            n, seen, errs = poll(con, last, index, sched)
            print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] nba_pm: {seen} markets, {n} changed"
                  + (f" · errors {errs}" if errs else ""), flush=True)
        except Exception as e:                                           # noqa: BLE001
            print(f"nba_pm: poll failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
        time.sleep(max(5.0, interval - (time.time() - t0)))


def fd_fair(q, gid, pid, stat, line, at):
    """FanDuel's over probability at `line`, at time `at`: de-vigged if FD posts both sides, else raw.
    -> (p, 'DEVIG'|'RAW') or None."""
    sides = {}
    for side, odds in q.execute("SELECT side, odds FROM quotes WHERE gid=? AND pid=? AND stat=? AND line=? "
                                "AND book='fd' AND seen_at <= ? ORDER BY seen_at", (gid, pid, stat, line, at)):
        sides[side] = odds                                   # the latest quote per side wins
    o, u = sides.get("over"), sides.get("under")
    if not o:
        return None
    if u:
        return (1 / o) / ((1 / o) + (1 / u)), "DEVIG"
    return 1 / o, "RAW"


def gaps(min_gap=0.05, limit=25, path=None, lines=None, now=None, devig_only=True):
    """Upcoming games: the latest Kalshi fair vs FanDuel fair at the same player, stat and line.
    devig_only: FanDuel's over-only ladder rungs carry their margin in the raw price (first night: RAW
    gaps averaged -0.057 vs -0.013 de-vigged), so by default only two-sided lines are compared."""
    now = (now or dt.datetime.now(dt.timezone.utc)).replace(tzinfo=None, microsecond=0).isoformat()
    con = sqlite3.connect(f"file:{path or DB}?mode=ro", uri=True)
    q = sqlite3.connect(f"file:{lines or LINES}?mode=ro", uri=True)
    rows = con.execute("SELECT p.* FROM pm_quotes p JOIN (SELECT ticker, MAX(seen_at) m FROM pm_quotes "
                       "GROUP BY ticker) l ON p.ticker = l.ticker AND p.seen_at = l.m "
                       "WHERE p.tip_utc > ? AND p.pid IS NOT NULL", (now,)).fetchall()
    out = []
    for (seen, _v, tk, _e, gd, team, pid, player, stat, line, bid, ask, _l, vol, _oi, tip, gid) in rows:
        if ask <= 0 or ask - bid > MAX_SPREAD:
            continue
        fd = fd_fair(q, gid, pid, stat, line, now)
        if not fd or (devig_only and fd[1] != "DEVIG"):
            continue
        k = (bid + ask) / 2
        out.append({"player": player, "team": team, "stat": stat, "line": line, "k": k, "fd": fd[0], "how": fd[1],
                    "gap": k - fd[0], "volume": vol, "tip": tip})
    out.sort(key=lambda r: -abs(r["gap"]))
    return [r for r in out if abs(r["gap"]) >= min_gap][:limit]


def money(minutes=30, limit=20, path=None, now=None):
    """The biggest pre-game volume jumps between consecutive stored quotes in the last `minutes`."""
    now = now or dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(minutes=minutes)).replace(tzinfo=None, microsecond=0).isoformat()
    con = sqlite3.connect(f"file:{path or DB}?mode=ro", uri=True)
    prev, out = {}, []
    for seen, tk, player, team, stat, line, bid, ask, vol in con.execute(
            "SELECT seen_at, ticker, player, team, stat, line, bid, ask, volume FROM pm_quotes "
            "ORDER BY ticker, seen_at"):
        p = prev.get(tk)
        prev[tk] = (seen, bid, ask, vol)
        if p and seen >= since and vol - p[3] > 0:
            out.append({"at": seen, "player": player, "team": team, "stat": stat, "line": line,
                        "dvol": vol - p[3], "dk": (bid + ask) / 2 - (p[1] + p[2]) / 2})
    out.sort(key=lambda r: -r["dvol"])
    return out[:limit]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, metavar="SECONDS")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--gaps", action="store_true")
    ap.add_argument("--money", type=int, metavar="MINUTES")
    a = ap.parse_args()
    if a.loop:
        loop(a.loop)
    elif a.once:
        import nba_rosters as R
        idx, _ = R.player_index(dt.datetime.now(ET).date().isoformat())
        print(poll(_db(), {}, idx, R.schedule()))
    elif a.gaps:
        for r in gaps():
            print(f"  {r['team']} {r['player']:<24} {r['stat']:<8} o{r['line']:<5} Kalshi {r['k']:.2f} · FD {r['fd']:.2f}"
                  f" {r['how']:<5} · gap {r['gap']:+.2f} · vol {r['volume']:,.0f}")
    elif a.money:
        for r in money(a.money):
            print(f"  {r['at'][11:16]} {r['team']} {r['player']:<24} {r['stat']:<8} o{r['line']:<5} "
                  f"+{r['dvol']:,.0f} contracts · fair {r['dk']:+.2f}")
