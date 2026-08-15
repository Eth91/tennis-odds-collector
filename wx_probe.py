#!/usr/bin/env python3
"""Is the weather gap a sticky NEGATIVE CACHE, or genuinely unresolvable venues? READ-ONLY probe.

The ix interaction table has wind on 86% of 2024 rounds, 14% of 2025 and 3% of 2026. That is not
an API failure -- open-meteo served the 2024 rows fine. weather_for() returns {} whenever
_course_latlon() yields None, and that lookup caches its FAILURES as permanently as its successes:

    if k in store:
        v = store[k]
        return (v[0], v[1]) if v else (None, None)

So a single transient ESPN error blacklists a course forever, and nothing ever retries it. The
cache holds 125 entries, 59 resolved and 66 failed, and the failures are dominated by DP World /
international events (Abu Dhabi, Dubai, Singapore, Kenya) -- but TOUR Championship is in there too,
which is a PGA Tour event that certainly has a venue, and that is the tell.

Two competing explanations with different fixes:
    STICKY NEGATIVE   a retry resolves them -> the fix is to stop caching failures, and the
                      weather branch unblocks for free
    GENUINELY MISSING ESPN's PGA league really does not carry these events -> the fix is a
                      separate coordinate source, and international events stay out of scope

⚠️ WRITES NOTHING. pga_context's cache feeds the LIVE wind_factor, and the simulator is frozen;
repairing it in place would change production inputs. This only measures. Any repair goes into a
RESEARCH-side store.
"""
import json
import urllib.request

import pga_context as C

UA = {"User-Agent": "Mozilla/5.0"}
store = (C._cache().get("latlon") or {})
failed = [k for k, v in store.items() if not v]
print("failed entries: %d" % len(failed))

PROBE = ["TOUR Championship", "Abu Dhabi HSBC Championship", "Dubai Desert Classic",
         "Genesis Scottish Open", "Truist Championship", "Procore Championship"]
PROBE = [p for p in PROBE if p in store] or failed[:6]
print("probing %d names (no writes)\n" % len(PROBE))

for nm in PROBE:
    eid, _d = (None, None)
    try:
        eid, _d = C._espn_event_id(nm)
    except Exception as e:                                              # noqa: BLE001
        print("   %-34s _espn_event_id RAISED %s" % (nm[:34], type(e).__name__))
        continue
    if not eid:
        print("   %-34s no ESPN event id -> genuinely not in ESPN's PGA league" % nm[:34])
        continue
    lat = lon = None
    try:
        core = json.load(urllib.request.urlopen(urllib.request.Request(
            "https://sports.core.api.espn.com/v2/sports/golf/leagues/pga/events/%s" % eid,
            headers=UA), timeout=25))
        refs = []
        C._walk_key(core, "$ref", refs)
        vref = next((str(r) for r in refs if "/venues/" in str(r)), None)
        if vref:
            ven = json.load(urllib.request.urlopen(urllib.request.Request(
                vref.replace("http://", "https://"), headers=UA), timeout=25))
            la, lo = [], []
            C._walk_key(ven, "latitude", la)
            C._walk_key(ven, "longitude", lo)
            if la and lo:
                lat, lon = la[0], lo[0]
            city = []
            C._walk_key(ven, "city", city)
            print("   %-34s eid=%-10s venue=%-22s lat/lon=%s"
                  % (nm[:34], eid, str(city[0] if city else "?")[:22],
                     ("%s,%s" % (lat, lon)) if lat else "NONE IN VENUE"))
        else:
            print("   %-34s eid=%-10s no /venues/ ref in the event" % (nm[:34], eid))
    except Exception as e:                                              # noqa: BLE001
        print("   %-34s venue fetch failed: %s" % (nm[:34], str(e)[:40]))

print("\nRESOLVED-side sanity: a few that DID work, to prove the chain still functions")
for nm in [k for k, v in store.items() if v][:3]:
    print("   %-34s %s" % (nm[:34], store[nm]))
