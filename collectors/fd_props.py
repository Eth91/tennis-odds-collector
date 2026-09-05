"""FanDuel player-prop scraper (NFL + NCAAF) — replaces the dead Odds API feed.

Reads FanDuel's own sportsbook API (sbapi.<state>.sportsbook.fanduel.com, no login,
the same `_ak` fd_collect.py / fd_sgp.py have used since July). Two write paths:

  fd_quotes   every poll, every player market, raw + canonical      (time series)
  quotes      one immutable capture per (event, band) on the T-180/105/75/25/5
              ladder, schema-compatible with the retired Odds-API collector so
              fbe.leagues.nfl.pipeline_audit / ledger keep working (book='fanduel')
  fd_runs     heartbeat per run — a run that fetched nothing is still recorded

Cadence (call every 10 min): events inside the ladder window (T-210..T-1) are
fetched every call with the 5 prop tabs; everything inside --hours is swept with
EVERY tab at most once per --sweep-min. Alt ladders ("40+ Yards") are parsed to
half-integer lines, side=over, market=<canonical>_alternate. Unknown PLAYER_X_
market types are kept as raw:<type> and printed, never dropped silently.

    python3 fd_props.py poll --league nfl
    python3 fd_props.py poll --league ncaaf
    python3 fd_props.py status --league nfl
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

AK = os.environ.get("FD_AK", "FhMFpcPWXMeyZxOx")
STATE = os.environ.get("FD_STATE", "ny")
BASE = f"https://sbapi.{STATE}.sportsbook.fanduel.com/api"
# NCAAF player props are HIDDEN on every US state host (state bans) but LISTED on FanDuel Ontario —
# the .ca catalog the user actually bets on. Verified 2026-09-05: PLAYER_MEDIUM_{RECEIVING,RUSHING,
# PASSING}_YARDS_CFB two-sided + ALT ladders on sbapi.on.sportsbook.fanduel.ca. NFL stays on the US host.
BASE_BY_LEAGUE = {"nfl": BASE,
                  "ncaaf": os.environ.get("FD_NCAAF_BASE", "https://sbapi.on.sportsbook.fanduel.ca/api")}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json"}
TIMEOUT, PACE = 20, 0.7
DBS = {"nfl": Path.home() / "tennis-odds-collector" / "nfl_prekick_prices.sqlite",
       "ncaaf": Path.home() / "tennis-odds-collector" / "collectors" / "ncaaf_fd_prices.sqlite"}
PAGE = {"nfl": "nfl", "ncaaf": "ncaaf"}
BANDS = [("t180", 150, 210), ("t105", 95, 125), ("t075", 60, 90),
         ("t025", 15, 40), ("t005", 1, 14)]
LADDER_TABS = ["popular", "passing-props", "receiving-props", "rushing-props", "scoring",
               "touchdown-props", "td-scorer-props"]

# marketType fragment -> canonical market (Odds-API naming so downstream code is unchanged).
# Order matters: combined stats before their components.
STAT_MAP = [
    ("RUSHING_+_RECEIVING", "player_rush_reception_yds"), ("RUSH_+_REC", "player_rush_reception_yds"),
    ("RUSHING_AND_RECEIVING", "player_rush_reception_yds"),
    ("PASSING_YARDS", "player_pass_yds"), ("PASSING_TOUCHDOWNS", "player_pass_tds"),
    ("PASS_ATTEMPTS", "player_pass_attempts"), ("PASS_COMPLETIONS", "player_pass_completions"),
    ("PASSING_COMPLETIONS", "player_pass_completions"), ("INTERCEPTIONS", "player_pass_interceptions"),
    ("LONGEST_RECEPTION", "player_longest_reception"), ("LONGEST_RUSH", "player_longest_rush"),
    ("LONGEST_PASS", "player_longest_completion"), ("LONGEST_COMPLETION", "player_longest_completion"),
    ("RECEIVING_YARDS", "player_reception_yds"), ("RECEPTIONS", "player_receptions"),
    ("RUSHING_YARDS", "player_rush_yds"), ("RUSH_ATTEMPTS", "player_rush_attempts"),
    ("RUSHING_ATTEMPTS", "player_rush_attempts"),
    ("KICKING_POINTS", "player_kicking_points"), ("FIELD_GOALS", "player_field_goals"),
    ("TACKLES", "player_tackles_assists"), ("SACKS", "player_sacks"),
]
TD_MAP = {"ANY_TIME_TOUCHDOWN_SCORER": "player_anytime_td",
          "FIRST_TOUCHDOWN_SCORER": "player_first_td",
          "LAST_TOUCHDOWN_SCORER": "player_last_td",
          "TO_SCORE_2+_TOUCHDOWNS": "player_2plus_td",
          "TO_SCORE_3+_TOUCHDOWNS": "player_3plus_td"}
GAME_MAP = {"TOTAL_POINTS_(OVER/UNDER)": "game_total", "ALTERNATE_TOTAL": "game_total_alternate",
            "MATCH_HANDICAP_(2-WAY)": "game_spread", "ALTERNATE_HANDICAP": "game_spread_alternate",
            "MONEY_LINE": "game_ml", "HOME_TEAM_TOTAL_POINTS": "team_total",
            "AWAY_TEAM_TOTAL_POINTS": "team_total", "HOME_TEAM_ALTERNATE_TOTAL": "team_total_alternate",
            "AWAY_TEAM_ALTERNATE_TOTAL": "team_total_alternate", "FIRST_HALF_TOTAL": "game_total_1h",
            "FIRST_HALF_HANDICAP": "game_spread_1h"}
_PLUS = re.compile(r"\b(\d+(?:\.\d+)?)\+")
_PAREN = re.compile(r"\(([+-]?\d+(?:\.\d+)?)\)")


def _dec(american):
    a = float(american)
    return round(1 + (a / 100 if a > 0 else 100 / -a), 4)


def _con(league):
    p = Path(os.environ["FD_PROPS_DB"]) if os.environ.get("FD_PROPS_DB") else DBS[league]
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS quotes(
        event_id TEXT NOT NULL, commence TEXT NOT NULL, snap_kind TEXT NOT NULL,
        fetched_at TEXT NOT NULL, mins_to_kick REAL NOT NULL,
        book TEXT NOT NULL, market TEXT NOT NULL, player TEXT NOT NULL,
        side TEXT NOT NULL, line REAL NOT NULL, price REAL NOT NULL, last_update TEXT,
        PRIMARY KEY(event_id, snap_kind, book, market, player, side, line));
    CREATE TABLE IF NOT EXISTS fetch_log(
        fetched_at TEXT NOT NULL, event_id TEXT NOT NULL, snap_kind TEXT NOT NULL,
        mins_to_kick REAL, http INTEGER, cost INTEGER, remaining INTEGER,
        n_quotes INTEGER, state TEXT NOT NULL, err TEXT,
        PRIMARY KEY(fetched_at, event_id, snap_kind));
    CREATE INDEX IF NOT EXISTS q_ev ON quotes(event_id, snap_kind);
    CREATE TABLE IF NOT EXISTS fd_quotes(
        fetched_at TEXT NOT NULL, event_id TEXT NOT NULL, event_name TEXT, commence TEXT,
        mins_to_kick REAL, market_type TEXT NOT NULL, market_name TEXT, market_id TEXT,
        runner TEXT NOT NULL, market TEXT NOT NULL, player TEXT, side TEXT, line REAL,
        american INTEGER, price REAL, sgm INTEGER,
        PRIMARY KEY(fetched_at, event_id, market_type, market_name, runner));
    CREATE INDEX IF NOT EXISTS fq_ev ON fd_quotes(event_id, market, player);
    CREATE TABLE IF NOT EXISTS fd_runs(
        fetched_at TEXT PRIMARY KEY, league TEXT, kind TEXT, n_events INTEGER,
        n_requests INTEGER, n_rows INTEGER, n_errors INTEGER, unknown_types TEXT);
    """)
    return con


def get(url, stats):
    stats["req"] += 1
    r = requests.get(url, headers=H, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def parse_market(m):
    """-> list of (market, player, side, line, american, runner_name). Empty if not a player market."""
    mt = (m.get("marketType") or "").upper()
    name = m.get("marketName") or ""
    out = []
    runners = m.get("runners") or []
    core = mt[:-4] if mt.endswith("_CFB") else mt      # college market types carry a _CFB suffix
    if core in TD_MAP:
        mt = core
    if mt in TD_MAP:
        for r in runners:
            a = ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOddsInt")
            if a is None:
                continue
            out.append((TD_MAP[mt], r.get("runnerName"), "yes", 0.5, int(a), r.get("runnerName")))
        return out
    if core in GAME_MAP and core != mt and "TOTAL_" not in mt:
        mt = core
    if mt in GAME_MAP or mt.endswith("_CFB") and ("TOTAL_" in mt):
        # game / team markets: runner = team or Over/Under, line = handicap (alt: "50+"/"Over 45.5")
        market = GAME_MAP.get(mt, "team_" + mt.lower().replace("_-_o/u_cfb", "").replace("_cfb", ""))
        for r in runners:
            a = ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOddsInt")
            rn = r.get("runnerName") or ""
            if a is None:
                continue
            low = rn.lower()
            pm = _PAREN.search(rn)                      # "Over (45.5)", "Clemson (-3.5)"
            side = ("over" if "over" in low else "under" if "under" in low
                    else _PAREN.sub("", rn).strip())    # team name for spreads / ML
            hc = r.get("handicap")
            line = (float(pm.group(1)) if pm else
                    float(hc) if hc not in (None, "") else None)
            if (line is None or line == 0) and _PLUS.search(rn):
                line, side = float(_PLUS.search(rn).group(1)) - 0.5, "over"
            if line is None:
                line = 0.0                              # money line
            out.append((market, name.split(" - ")[0].strip() if " - " in name else name,
                        side, line, int(a), rn))
        return out
    if not mt.startswith(("PLAYER_X_", "PLAYER_MEDIUM_", "PLAYER_HIGH_", "PLAYER_LOW_")):
        return out
    canon = next((c for k, c in STAT_MAP if k in mt), None)
    player = name.split(" - ")[0].strip() if " - " in name else None
    alt = "_ALT_" in mt or mt.startswith("PLAYER_X_ALT")
    market = (canon + ("_alternate" if alt else "")) if canon else f"raw:{mt}"
    for r in runners:
        a = ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}).get("americanOddsInt")
        rn = r.get("runnerName") or ""
        if a is None:
            continue
        side, line = None, None
        if alt:
            mm = _PLUS.search(rn)
            if mm:
                line, side = float(mm.group(1)) - 0.5, "over"
        else:
            low = rn.lower()
            if " over" in low or low.startswith("over"):
                side = "over"
            elif " under" in low or low.startswith("under"):
                side = "under"
            hc = r.get("handicap")
            line = float(hc) if hc not in (None, "", 0, 0.0) else None
        out.append((market, player, side, line, int(a), rn))
    return out


def _band(mins):
    for lab, lo, hi in BANDS:
        if lo <= mins <= hi:
            return lab
    return None


def _done(con, eid, band):
    return con.execute("SELECT 1 FROM fetch_log WHERE event_id=? AND snap_kind=? "
                       "AND state IN ('ok','empty') LIMIT 1", (eid, band)).fetchone() is not None


def poll(league, hours, sweep_min, limit, verbose):
    con, stats = _con(league), {"req": 0}
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    pid = PAGE[league]
    base = BASE_BY_LEAGUE.get(league, BASE)
    try:
        page = get(f"{base}/content-managed-page?page=CUSTOM&customPageId={pid}"
                   f"&pbHorizonId={pid}&_ak={AK}&timezone=America%2FNew_York", stats)
    except Exception as exc:
        con.execute("INSERT OR REPLACE INTO fd_runs VALUES (?,?,?,?,?,?,?,?)",
                    (stamp, league, "page-fail", 0, stats["req"], 0, 1, str(exc)[:200]))
        con.commit()
        print(f"[{stamp}] {league}: EVENT PAGE FAILED: {exc}", file=sys.stderr)
        return 1
    evs = (page.get("attachments") or {}).get("events") or {}
    real = [(str(v["eventId"]), v) for v in evs.values()
            if v.get("openDate") and "@" in (v.get("name") or "")]
    if not real:
        con.execute("INSERT OR REPLACE INTO fd_runs VALUES (?,?,?,?,?,?,?,?)",
                    (stamp, league, "zero-events", 0, stats["req"], 0, 1, ""))
        con.commit()
        print(f"[{stamp}] {league}: FanDuel returned ZERO matches — refusing to treat as empty slate",
              file=sys.stderr)
        return 1
    last = con.execute("SELECT MAX(fetched_at) FROM fd_runs WHERE league=? AND kind='sweep'",
                       (league,)).fetchone()[0]
    sweep_due = (last is None or
                 (now - dt.datetime.fromisoformat(last)).total_seconds() >= sweep_min * 60)
    cut = now + dt.timedelta(hours=hours)
    todo = []
    for eid, v in sorted(real, key=lambda kv: kv[1]["openDate"]):
        k = dt.datetime.fromisoformat(v["openDate"].replace("Z", "+00:00"))
        mins = (k - now).total_seconds() / 60
        band = _band(mins)
        ladder = 1 <= mins <= 210
        if ladder or (sweep_due and k <= cut):
            todo.append((eid, v, mins, band, ladder))
    if limit:
        todo = todo[:limit]
    if verbose:
        print(f"[{stamp}] {league}: {len(real)} matches, {len(todo)} to fetch "
              f"({'sweep' if sweep_due else 'ladder-only'})")
    n_rows = n_err = 0
    unknown = set()
    for eid, v, mins, band, ladder in todo:
        rows, err, tabs_done = {}, None, 0
        try:
            d = get(f"{base}/event-page?eventId={eid}&_ak={AK}&timezone=America%2FNew_York", stats)
            mk = dict((d.get("attachments") or {}).get("markets") or {})
            titles = [(t.get("title") if isinstance(t, dict) else str(t))
                      for t in ((d.get("layout") or {}).get("tabs") or {}).values()]
            slugs = list(LADDER_TABS)
            if not ladder or sweep_due:
                slugs += [(t or "").lower().replace(" ", "-").replace("'", "").replace("™", "")
                          for t in titles]
            seen = set()
            for slug in slugs:
                if not slug or slug in seen:
                    continue
                seen.add(slug)
                time.sleep(PACE)
                try:
                    r = get(f"{base}/event-page?eventId={eid}&tab={slug}&_ak={AK}"
                            f"&timezone=America%2FNew_York", stats)
                    mk.update((r.get("attachments") or {}).get("markets") or {})
                    tabs_done += 1
                except Exception as exc:
                    n_err += 1
                    if verbose:
                        print(f"   {eid} tab {slug}: {type(exc).__name__}")
            for m in mk.values():
                for market, player, side, line, am, rn in parse_market(m):
                    if market.startswith("raw:"):
                        unknown.add(market[4:])
                    rows[(m.get("marketType"), m.get("marketName"), rn)] = (
                        market, player, side, line, am, m.get("marketId"), int(bool(m.get("sgmMarket"))))
        except Exception as exc:
            err, n_err = f"{type(exc).__name__}: {exc}"[:200], n_err + 1
        # time series: everything, every poll
        con.executemany(
            "INSERT OR IGNORE INTO fd_quotes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(stamp, eid, v.get("name"), v.get("openDate"), round(mins, 1), mt, mn, mid, rn,
              market, player, side, line, am, _dec(am), sgm)
             for (mt, mn, rn), (market, player, side, line, am, mid, sgm) in rows.items()])
        n_rows += len(rows)
        # ladder: one immutable capture per band, canonical markets only
        if band and not _done(con, eid, band):
            canon = [(eid, v.get("openDate"), band, stamp, round(mins, 1), "fanduel",
                      market, player, side, line, _dec(am), None)
                     for (mt, mn, rn), (market, player, side, line, am, mid, sgm) in rows.items()
                     if not market.startswith("raw:") and player and side and line is not None]
            con.executemany("INSERT OR IGNORE INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", canon)
            state = "error" if err else ("ok" if canon else "empty")
            con.execute("INSERT OR IGNORE INTO fetch_log VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (stamp, eid, band, round(mins, 1), 200 if not err else 0, 0, 0,
                         len(canon), state, err))
        if verbose:
            print(f"   {v.get('name')[:34]:34s} T-{mins:6.0f}min {('['+band+']') if band else '':8s}"
                  f" tabs {tabs_done:2d} rows {len(rows):4d}" + (f"  {err}" if err else ""))
        con.commit()
    con.execute("INSERT OR REPLACE INTO fd_runs VALUES (?,?,?,?,?,?,?,?)",
                (stamp, league, "sweep" if sweep_due else "ladder", len(todo), stats["req"],
                 n_rows, n_err, ",".join(sorted(unknown))))
    con.commit()
    if verbose:
        print(f"   stored {n_rows} rows in {stats['req']} requests, {n_err} errors"
              + (f"; UNKNOWN player market types: {sorted(unknown)}" if unknown else ""))
    con.close()
    return 0


def status(league):
    con = _con(league)
    print(f"{league}: fd_quotes {con.execute('SELECT COUNT(*) FROM fd_quotes').fetchone()[0]:,} rows, "
          f"events {con.execute('SELECT COUNT(DISTINCT event_id) FROM fd_quotes').fetchone()[0]}")
    for r in con.execute("SELECT market, COUNT(*), COUNT(DISTINCT player) FROM fd_quotes "
                         "GROUP BY 1 ORDER BY 2 DESC"):
        print(f"   {r[0]:36s} {r[1]:8,d} rows {r[2]:5d} players")
    print("ladder (quotes):")
    for lab, _, _ in BANDS:
        r = con.execute("SELECT COUNT(DISTINCT event_id), COUNT(*) FROM quotes WHERE snap_kind=?",
                        (lab,)).fetchone()
        print(f"   {lab}  events {r[0]:4d}  quotes {r[1]:7,d}")
    print("runs:")
    for r in con.execute("SELECT * FROM fd_runs ORDER BY 1 DESC LIMIT 5"):
        print("  ", r)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["poll", "status"])
    ap.add_argument("--league", default="nfl", choices=list(DBS))
    ap.add_argument("--hours", type=float, default=96)
    ap.add_argument("--sweep-min", type=float, default=30)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.cmd == "status":
        status(a.league)
    else:
        sys.exit(poll(a.league, a.hours, a.sweep_min, a.limit, not a.quiet))
