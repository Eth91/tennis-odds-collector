#!/usr/bin/env python3
"""Point-in-time snapshots of NBA.com's daily lineups (Expected / Confirmed starters, Active / Inactive) for
proj-1.1 (NBA_PROJ11_PREREG.md). The historical files only hold the final state; this keeps every change
with the time it was seen, so a lineup is used at tip − 30 min only if it was visible by then.
    python3 nba_lineups_poll.py --until 2026-10-27T03:30 --every 180 [--db PATH]
    python3 nba_lineups_poll.py --once --db ~/nba-engine/nba_lineups.sqlite       # one poll (cron)
Stores a snapshot only when the content changed (plus one per hour as a heartbeat).
"""
import argparse
import hashlib
import json
import sqlite3
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / ".projdata" / "lineups_live.sqlite"
H = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com", "Accept": "application/json"}
DDL = "CREATE TABLE IF NOT EXISTS snaps (fetched_at TEXT, date_et TEXT, sha TEXT, body BLOB)"


def et_date(now):
    return (now - timedelta(hours=4 if 3 <= now.month <= 10 else 5)).date().isoformat()


def poll_once(con, get, now=None):
    now = now or datetime.now(timezone.utc)
    d = et_date(now)
    r = get(f"https://stats.nba.com/js/data/leaders/00_daily_lineups_{d.replace('-', '')}.json")
    if r.status_code != 200:
        return f"http {r.status_code}"
    j = r.json()
    body = json.dumps(j, sort_keys=True).encode()
    sha = hashlib.sha1(body).hexdigest()
    last = con.execute("SELECT sha, fetched_at FROM snaps WHERE date_et = ? ORDER BY fetched_at DESC LIMIT 1", (d,)).fetchone()
    stale = last is None or last[0] != sha or now.isoformat() > (datetime.fromisoformat(last[1]) + timedelta(hours=1)).isoformat()
    if stale:
        con.execute("INSERT INTO snaps VALUES (?,?,?,?)", (now.isoformat(timespec="seconds"), d, sha, zlib.compress(body)))
        con.commit()
    return "stored" if stale else "same"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="UTC, e.g. 2026-10-27T03:30")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=int, default=180)
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args()
    from curl_cffi import requests as cr
    get = lambda u: cr.get(u, impersonate="chrome", timeout=30, headers=H)
    con = sqlite3.connect(a.db)
    con.execute(DDL)
    if a.once:
        print(datetime.now(timezone.utc).isoformat(timespec="seconds"), poll_once(con, get), flush=True)
        return
    end = datetime.fromisoformat(a.until).replace(tzinfo=timezone.utc)
    while datetime.now(timezone.utc) < end:
        try:
            print(datetime.now(timezone.utc).isoformat(timespec="seconds"), poll_once(con, get), flush=True)
        except Exception as e:                                         # noqa: BLE001
            print("error", type(e).__name__, str(e)[:80], flush=True)
        time.sleep(a.every)


if __name__ == "__main__":
    main()
