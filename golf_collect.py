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

    # DISCOVERY TRAP (2026-07-29): the user sees a birdies-or-better market in-app
    # ($2,880 limit) that none of the page slugs above have EVER returned. Sweep the
    # busiest current event's event-page across candidate tabs, store what appears, and
    # shout on any marketType never seen before — so the day FD posts it, we have it.
    try:
        seenf = HERE / ".golf_mtypes_seen.json"
        try:
            seen = set(json.loads(seenf.read_text()))
        except Exception:
            seen = set()
        row = con.execute("SELECT event, COUNT(*) c FROM golf_lines WHERE collected_at=? "
                          "AND event LIKE '%PGA%' GROUP BY event ORDER BY c DESC LIMIT 1",
                          (ts,)).fetchone()
        d0 = get(f"https://sbapi.ny.sportsbook.fanduel.com/api/content-managed-page?"
                 f"page=CUSTOM&customPageId=pga&pbHorizontal=false&_ak={AK}"
                 f"&timezone=America%2FNew_York")
        evs0 = (d0.get("attachments") or {}).get("events") or {}
        eid0 = next((k for k, v in evs0.items()
                     if row and (v.get("name") or "").strip() == row[0].strip()),
                    next(iter(evs0), None))
        new_types = set()
        if eid0:
            for tab in ("", "player-props", "props", "specials", "scoring", "performances",
                        "round-1", "round-leader", "to-make-the-cut", "player-performance"):
                tq = f"&tab={tab}" if tab else ""
                try:
                    e2 = get(f"https://sbapi.ny.sportsbook.fanduel.com/api/event-page?"
                             f"eventId={eid0}{tq}&_ak={AK}&timezone=America%2FNew_York")
                except Exception:
                    continue
                att2 = e2.get("attachments") or {}
                evn2 = ((att2.get("events") or {}).get(str(eid0)) or {}).get("name") or "?"
                for m in (att2.get("markets") or {}).values():
                    mt2 = m.get("marketType") or "?"
                    if mt2 not in seen:
                        new_types.add(mt2)
                    for r in m.get("runners") or []:
                        odds = (((r.get("winRunnerOdds") or {}).get("trueOdds") or {})
                                .get("decimalOdds") or {}).get("decimalOdds")
                        if odds:
                            con.execute("INSERT INTO golf_lines VALUES (?,?,?,?,?,?,?)",
                                        (ts, evn2, m.get("marketName") or "?", mt2,
                                         r.get("runnerName") or "?", r.get("handicap"),
                                         round(float(odds), 4)))
        con.commit()
        # COUPON-HYDRATION WATCH (2026-07-29): the pga page's "Birdies or Better" module
        # (id 2240) carries coupons that are isCollapsed:true = content withheld from every
        # API shape we could name (~30 tried, both .com and .ca hosts). The default tab's
        # coupons sit isCollapsed:false + hasAttachments:true = hydrated inline — FD flips
        # this server-side when a tab is promoted (typically Wed). Watch the flip: the
        # moment ANY birdie-module coupon uncollapses, the same page fetch will contain the
        # markets and this collector captures them automatically — announce it loudly.
        try:
            mods = []
            def _wm(o):
                if isinstance(o, dict):
                    if o.get("type") == "COUPON" and "irdie" in str(o.get("title", "")):
                        mods.append(o)
                    for v in o.values():
                        _wm(v)
                elif isinstance(o, list):
                    for v in o:
                        _wm(v)
            _wm(d0)
            for mo in mods:
                open_c = [c.get("id") for c in mo.get("coupons") or []
                          if not c.get("isCollapsed")]
                if open_c or mo.get("hasAttachments"):
                    print(f"golf trap: 🐦 BIRDIES COUPON HYDRATING (module {mo.get('id')}, "
                          f"open coupons {open_c}) — markets should land this pass or next")
        except Exception:
            pass
        if new_types:
            print(f"golf trap: NEW MARKET TYPES seen: {sorted(new_types)[:6]}")
            if any("BIRD" in t.upper() for t in new_types):
                print("golf trap: 🐦 BIRDIES MARKET CAPTURED — the pricer can start calibrating")
        seen |= new_types
        seenf.write_text(json.dumps(sorted(seen)))
    except Exception as _te:
        print(f"golf trap skipped: {str(_te)[:60]}")
    con.commit()
    print(f"golf_collect {ts}: {n} rows")

if __name__ == "__main__":
    main()
