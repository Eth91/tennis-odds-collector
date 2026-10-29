#!/usr/bin/env python3
"""Collect historical IN-PLAY WNBA player-prop quotes for backtesting.

Every pull is PERSISTED so re-analysis never re-spends credits. Idempotent on
(event_id, snapshot_ts, book, player, market, line, side).

⚠️ We store the price AS POSTED at that snapshot. Whether it was takeable is a separate question,
measured later -- never silently assumed.
"""
import sqlite3, requests, datetime as dt, sys, time
from pathlib import Path
KEY = "64d04fb6d6276d1e7a2783c2b48d0488"
B = "https://api.the-odds-api.com/v4"
DB = Path("/home/ubuntu/tennis-odds-collector/research/live_odds.sqlite")
OFFSETS = [10, 25, 40, 55, 70, 85]          # minutes after tip: Q1 .. Q4
MARKETS = "player_points,player_rebounds,player_assists"

con = sqlite3.connect(DB, timeout=120)
con.execute("PRAGMA journal_mode=WAL")
con.execute("""CREATE TABLE IF NOT EXISTS q(
  event_id TEXT, tip TEXT, box_date TEXT, home TEXT, away TEXT,
  offset_min INTEGER, snap_ts TEXT, book TEXT, last_update TEXT,
  player TEXT, market TEXT, line REAL, side TEXT, price REAL,
  PRIMARY KEY(event_id, snap_ts, book, player, market, line, side))""")
con.execute("CREATE TABLE IF NOT EXISTS done(event_id TEXT, offset_min INTEGER, "
            "PRIMARY KEY(event_id, offset_min))")
con.commit()
spent = 0
def get(url, params, lab):
    global spent
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=60)
        except Exception as e:
            time.sleep(3); continue
        spent += int(r.headers.get("x-requests-last") or 0)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (401, 429):
            print(f"  !! {lab} {r.status_code} {r.text[:120]}"); return None
        return None
    return None

def et_date(tip_utc):
    """Box-score date = the ET calendar date of tip. A 02:00Z tip is the PREVIOUS ET day."""
    return (tip_utc - dt.timedelta(hours=4)).date().isoformat()

dates = sys.argv[1:] or []
seen_events = {}
for d in dates:
    j = get(f"{B}/historical/sports/basketball_wnba/events",
            {"apiKey": KEY, "date": f"{d}T12:00:00Z"}, f"events {d}")
    if not j: continue
    for e in (j.get("data") or []):
        tip = dt.datetime.fromisoformat(str(e["commence_time"]).replace("Z", "+00:00"))
        if et_date(tip) == d:
            seen_events[e["id"]] = (tip, e.get("home_team"), e.get("away_team"))
print(f"{len(seen_events)} events across {len(dates)} dates  (credits so far {spent})", flush=True)

todo = con.execute("SELECT event_id, offset_min FROM done").fetchall()
already = {(a, b) for a, b in todo}
rows_added = 0
for eid, (tip, home, away) in sorted(seen_events.items(), key=lambda kv: kv[1][0]):
    for off in OFFSETS:
        if (eid, off) in already: continue
        snap = (tip + dt.timedelta(minutes=off)).strftime("%Y-%m-%dT%H:%M:%SZ")
        j = get(f"{B}/historical/sports/basketball_wnba/events/{eid}/odds",
                {"apiKey": KEY, "date": snap, "regions": "us", "markets": MARKETS,
                 "oddsFormat": "decimal"}, f"{eid[:8]}+{off}")
        con.execute("INSERT OR IGNORE INTO done VALUES(?,?)", (eid, off))
        if not j:
            con.commit(); continue
        ts = j.get("timestamp"); dd = j.get("data") or {}
        batch = []
        for bk in (dd.get("bookmakers") or []):
            for m in (bk.get("markets") or []):
                for o in (m.get("outcomes") or []):
                    if o.get("point") is None or not o.get("price"): continue
                    batch.append((eid, tip.isoformat(), et_date(tip), home, away, off, ts,
                                  bk.get("key"), bk.get("last_update"), o.get("description"),
                                  m.get("key"), float(o["point"]), o.get("name"), float(o["price"])))
        if batch:
            con.executemany("INSERT OR IGNORE INTO q VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
            rows_added += len(batch)
        con.commit()
    print(f"  {et_date(tip)} {away} @ {home}: rows now {rows_added}, credits {spent}", flush=True)
n = con.execute("SELECT COUNT(*) FROM q").fetchone()[0]
ev = con.execute("SELECT COUNT(DISTINCT event_id) FROM q").fetchone()[0]
dd = con.execute("SELECT COUNT(DISTINCT box_date) FROM q").fetchone()[0]
print(f"\nTOTAL stored: {n} quotes over {ev} events / {dd} DISTINCT DATES. credits spent {spent}")
con.close()
