#!/usr/bin/env python3
"""⛳ Golf line collector (FanDuel, generic capture). Grabs EVERY market on the FD pga page
(outrights, matchups, 3-balls, props — whatever posts) into golf_lines.sqlite. Runs via cron
every 30 min on the VM. Generic on purpose: market shapes for derivatives are unknown until
they post; the meters parse from the captured shapes. Phase-4 of PGA_PLAN.md."""
import datetime as dt
import json
import sqlite3
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
AK = "FhMFpcPWXMeyZxOx"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=25))

def main():
    con = sqlite3.connect(HERE / "golf_lines.sqlite")
    con.execute("""CREATE TABLE IF NOT EXISTS golf_lines(
        collected_at TEXT, event TEXT, market TEXT, mtype TEXT, runner TEXT,
        handicap REAL, odds REAL)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_gl ON golf_lines(event, market, runner)")
    ts = dt.datetime.utcnow().replace(microsecond=0).isoformat()
    n = 0
    for slug in ("pga", "golf-3-balls", "golf-matchups", "golf-props", "the-open", "lpga"):
        try:
            d = get(f"https://sbapi.ny.sportsbook.fanduel.com/api/content-managed-page?"
                    f"page=CUSTOM&customPageId={slug}&pbHorizontal=false&_ak={AK}"
                    f"&timezone=America%2FNew_York")
        except Exception:
            continue
        att = d.get("attachments") or {}
        evs = {str(k): (v.get("name") or "?") for k, v in (att.get("events") or {}).items()}
        for m in (att.get("markets") or {}).values():
            ev = evs.get(str(m.get("eventId")), "?")
            mname = m.get("marketName") or "?"
            mtype = m.get("marketType") or "?"
            for r in m.get("runners") or []:
                odds = (((r.get("winRunnerOdds") or {}).get("trueOdds") or {})
                        .get("decimalOdds") or {}).get("decimalOdds")
                if odds:
                    con.execute("INSERT INTO golf_lines VALUES (?,?,?,?,?,?,?)",
                                (ts, ev, mname, mtype, r.get("runnerName") or "?",
                                 r.get("handicap"), round(float(odds), 4)))
                    n += 1
    con.commit()
    print(f"golf_collect {ts}: {n} rows")

if __name__ == "__main__":
    main()
