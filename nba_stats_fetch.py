#!/usr/bin/env python3
"""NBA.com/stats families at player-game grain, for proj-1.1 research (NBA_PROJ11_PREREG.md).

Every family is fetched one game date at a time (DateFrom = DateTo), so each row is one player's single game
(GP = 1) as NBA.com stores it now. That is an as-of-game-end value: a feature may use it only for LATER
dates. Stat corrections rewrite these silently; the fetch time is kept so that is auditable.

Raw responses are kept, compressed, in `.projdata/nba_stats_raw.sqlite` (kind, key, fetched_at, status,
rows), so a parser change never needs a refetch and nothing is overwritten once fetched.

Requests are sequential per worker with a pause, exponential backoff, a stop after repeated failures, and a
schema check (the expected id column must be in the headers). Same request headers as the engine's other
NBA.com collectors (nba_tracking.py).
    python3 nba_stats_fetch.py                 # everything missing, in priority order
    python3 nba_stats_fetch.py --kinds adv,lineups --workers 1
    python3 nba_stats_fetch.py --status        # per-kind counts
"""
import argparse
import json
import pickle
import sqlite3
import sys
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / ".projdata"
RAW = DATA / "nba_stats_raw.sqlite"
H = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com", "Accept": "application/json",
     "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}
FILTERS = ("&College=&Conference=&Country=&Division=&DraftPick=&DraftYear=&GameScope=&GameSegment=&Height="
           "&LastNGames=0&LeagueID=00&Location=&Month=0&OpponentTeamID=0&Outcome=&PORound=0&PaceAdjust=N"
           "&Period=0&PlayerExperience=&PlayerPosition=&PlusMinus=N&Rank=N&SeasonSegment=&ShotClockRange="
           "&StarterBench=&TeamID=0&VsConference=&VsDivision=&Weight=")
S = "https://stats.nba.com/stats/"


def _dash(measure):
    return S + "leaguedashplayerstats?MeasureType=" + measure + "&PerMode=Totals" + FILTERS


def _pt(measure):
    return (S + "leaguedashptstats?PtMeasureType=" + measure + "&PerMode=Totals&PlayerOrTeam=Player"
            + FILTERS)


# kind -> (url template without Season/SeasonType/DateFrom/DateTo, id column the schema check needs)
KINDS = {
    "lineups": (None, "games"),                    # the daily lineups file: 2023-24 on (404 before)
    "starters": (S + "leaguedashplayerstats?MeasureType=Base&PerMode=Totals"
                 + FILTERS.replace("&StarterBench=", "&StarterBench=Starters"), "PLAYER_ID"),
    "adv": (_dash("Advanced"), "PLAYER_ID"),
    "pt_Possessions": (_pt("Possessions"), "PLAYER_ID"),
    "usage": (_dash("Usage"), "PLAYER_ID"),
    "pt_Drives": (_pt("Drives"), "PLAYER_ID"),
    "pt_CatchShoot": (_pt("CatchShoot"), "PLAYER_ID"),
    "pt_PullUpShot": (_pt("PullUpShot"), "PLAYER_ID"),
    "pt_Passing": (_pt("Passing"), "PLAYER_ID"),
    "pt_Rebounding": (_pt("Rebounding"), "PLAYER_ID"),
    "shotloc": (S + "leaguedashplayershotlocations?DistanceRange=By%20Zone&MeasureType=Base&PerMode=Totals" + FILTERS,
                "PLAYER_ID"),
    "scoring": (_dash("Scoring"), "PLAYER_ID"),
    "hustle": (S + "leaguehustlestatsplayer?PerMode=Totals" + FILTERS, "PLAYER_ID"),
    "misc": (_dash("Misc"), "PLAYER_ID"),
    "pt_Defense": (_pt("Defense"), "PLAYER_ID"),
    "defense": (_dash("Defense"), "PLAYER_ID"),
    "team_adv": (S + "leaguedashteamstats?MeasureType=Advanced&PerMode=Totals" + FILTERS, "TEAM_ID"),
    "team_opp": (S + "leaguedashteamstats?MeasureType=Opponent&PerMode=Totals" + FILTERS, "TEAM_ID"),
    "pt_SpeedDistance": (_pt("SpeedDistance"), "PLAYER_ID"),
    "pt_Efficiency": (_pt("Efficiency"), "PLAYER_ID"),
    "pt_ElbowTouch": (_pt("ElbowTouch"), "PLAYER_ID"),
    "pt_PostTouch": (_pt("PostTouch"), "PLAYER_ID"),
    "pt_PaintTouch": (_pt("PaintTouch"), "PLAYER_ID"),
}
PAUSE, TRIES, MAX_FAIL = 0.8, 5, 12

DDL = """CREATE TABLE IF NOT EXISTS raw (kind TEXT, key TEXT, season TEXT, url TEXT, fetched_at TEXT,
    status INTEGER, n INTEGER, body BLOB, PRIMARY KEY (kind, key))"""


def season_of(d):
    y, m = int(d[:4]), int(d[5:7])
    s = y if m >= 8 else y - 1
    return f"{s}-{str(s + 1)[2:]}"


def url_for(kind, d):
    if kind == "lineups":
        return f"https://stats.nba.com/js/data/leaders/00_daily_lineups_{d.replace('-', '')}.json"
    return (KINDS[kind][0] + f"&Season={season_of(d)}&SeasonType=Regular%20Season&DateFrom={d}&DateTo={d}")


def rows_of(kind, j):
    """Row count after the schema check; raises ValueError when the response is not the expected shape."""
    need = KINDS[kind][1]
    if kind == "lineups":
        if "games" not in j:
            raise ValueError("no games key")
        return sum(len(g[t]["players"]) for g in j["games"] for t in ("homeTeam", "awayTeam"))
    rs = j["resultSets"]
    rs = rs[0] if isinstance(rs, list) else rs
    hdr = rs["headers"]
    cols = hdr[-1]["columnNames"] if hdr and isinstance(hdr[0], dict) else hdr
    if need not in cols:
        raise ValueError(f"{need} not in headers")
    return len(rs["rowSet"])


def dates():
    """Regular-season game dates: the box-score rows (2022-23..2025-26) plus this season's finished games."""
    rows = pickle.loads((DATA / "cache.pkl").read_bytes())["rows"]
    out = {r["date"] for r in rows}
    m = sqlite3.connect(f"file:{DATA / 'nba_matchup.sqlite'}?mode=ro", uri=True)
    out |= {d for (d,) in m.execute("SELECT date FROM games WHERE home_pts IS NOT NULL")}
    return sorted(out)


def fetch_one(get, kind, d):
    url = url_for(kind, d)
    err = None
    for k in range(TRIES):
        try:
            r = get(url)
            if r.status_code == 404:
                return url, 404, 0, None                               # not published for this date: final
            if r.status_code == 200:
                j = r.json()
                n = rows_of(kind, j)
                return url, 200, n, zlib.compress(json.dumps(j).encode())
            err = f"http {r.status_code}"
        except Exception as e:                                         # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(5 * 2 ** k)
    raise RuntimeError(err)


def run(kinds, workers=2, get=None):
    con = sqlite3.connect(RAW, check_same_thread=False)
    con.execute(DDL)
    lock = threading.Lock()
    have = {(k, key) for k, key in con.execute("SELECT kind, key FROM raw WHERE status IN (200, 404)")}
    todo = [(k, d) for k in kinds for d in dates() if (k, d) not in have]
    print(f"nba_stats_fetch: {len(todo)} requests to make ({len(have)} already stored)", flush=True)
    fails = [0]
    done = [0]
    t0 = time.time()
    if get is None:
        from curl_cffi import requests as cr
        get = lambda u: cr.get(u, impersonate="chrome", timeout=60, headers=H)

    def worker(items):
        for kind, d in items:
            if fails[0] >= MAX_FAIL:
                return
            try:
                url, st, n, body = fetch_one(get, kind, d)
                with lock:
                    con.execute("INSERT OR IGNORE INTO raw VALUES (?,?,?,?,?,?,?,?)",
                                (kind, d, season_of(d), url, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 st, n, body))
                    con.commit()
                    fails[0] = 0
                    done[0] += 1
                    if done[0] % 100 == 0:
                        el = time.time() - t0
                        print(f"  {done[0]}/{len(todo)} · {kind} {d} · {el / 60:.0f} min, "
                              f"~{el / done[0] * (len(todo) - done[0]) / 60:.0f} min left", flush=True)
            except RuntimeError as e:
                with lock:
                    fails[0] += 1
                    print(f"  FAILED {kind} {d}: {e} ({fails[0]} in a row)", flush=True)
            time.sleep(PAUSE)

    chunks = [todo[i::workers] for i in range(workers)]
    th = [threading.Thread(target=worker, args=(c,)) for c in chunks]
    for t in th:
        t.start()
    for t in th:
        t.join()
    left = len(todo) - done[0]
    print(f"nba_stats_fetch: stored {done[0]}, missing {left}" + (" — STOPPED after repeated failures"
                                                                   if fails[0] >= MAX_FAIL else ""), flush=True)
    return 1 if fails[0] >= MAX_FAIL else 0


def status():
    con = sqlite3.connect(RAW)
    con.execute(DDL)
    n_dates = len(dates())
    for kind in KINDS:
        n, rows = con.execute("SELECT COUNT(*), COALESCE(SUM(n), 0) FROM raw WHERE kind = ? AND status = 200",
                              (kind,)).fetchone()
        print(f"{kind:18s} {n:4d}/{n_dates} dates  {rows:8d} rows")


def load(kind, con=None):
    """{date: parsed JSON} for a stored kind."""
    con = con or sqlite3.connect(f"file:{RAW}?mode=ro", uri=True)
    return {key: json.loads(zlib.decompress(b)) for key, b in
            con.execute("SELECT key, body FROM raw WHERE kind = ? AND status = 200", (kind,))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kinds", default=",".join(KINDS))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        return status()
    kinds = [k for k in a.kinds.split(",") if k]
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        sys.exit(f"unknown kinds: {bad}")
    sys.exit(run(kinds, a.workers))


if __name__ == "__main__":
    main()
