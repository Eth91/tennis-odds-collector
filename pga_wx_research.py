#!/usr/bin/env python3
"""Research-side weather: correct coordinates PER EVENT-YEAR, then daily conditions. Resumable.

WHY REBUILD. pga_context's latlon cache geocodes a BARE CITY NAME and keys the result by
TOURNAMENT NAME. Both are wrong:
    bare city    Augusta -> Maine (1,598 km off), Dublin -> Ireland (5,742 km), Rio Grande ->
                 Brazil (5,793 km, wrong hemisphere), North Berwick -> Maine (4,870 km)
    name-keyed   the U.S. Open, PGA Championship and The Open ROTATE venues every year, so one
                 coordinate per name cannot be right for more than one edition
At least 10.6% of the weather rows in the ix table came from a known-wrong coordinate, and that is
a lower bound because the ambiguity applies everywhere. Weather interactions were being tested
against another continent's wind.

TWO FIXES, both structural rather than a patch of the bad entries:
    KEY BY event_id, not by name. An event_id is one tournament in one year, so a rotating major
    resolves to the venue it was actually played at.
    GEOCODE WITH CONTEXT. city + admin1(state) + country, and REJECT a hit whose country does not
    match what ESPN reported. Ambiguous city names are the entire failure mode, so the country
    check is the fix, not a nicety.

FAILS LOUD. A venue that cannot be resolved is recorded with a reason and NO coordinate. The bug
being fixed is precisely that an unresolvable venue silently returned {} and the row was then
analysed as if the weather were merely missing at random -- it was not, it was missing for whole
tournaments at a time, which is why coverage collapsed from 86% of 2024 rounds to 3% of 2026.

⚠️ WRITES ONLY TO pga_wx.sqlite. The production simulator is frozen and pga_context's cache feeds
the live wind_factor; this touches neither.
"""
import datetime as dt
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "pga_wx.sqlite"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}


def get(u, timeout=25):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA),
                                            timeout=timeout))


def walk(o, key, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                acc.append(v)
            walk(v, key, acc)
    elif isinstance(o, list):
        for v in o:
            walk(v, key, acc)


# ESPN spells countries as free text ("USA", "Scotland"); the geocoder answers ISO2 + a long name.
# Both sides normalise here before the gate compares them. Rejecting a correct match is not a
# safe failure -- it is how 130 venues went unresolved and the weather branch stayed blocked.
_ISO = {
    "USA": "US", "UNITED STATES": "US", "UNITED STATES OF AMERICA": "US", "U.S.A.": "US",
    "SCOTLAND": "GB", "ENGLAND": "GB", "WALES": "GB", "NORTHERN IRELAND": "GB",
    "UNITED KINGDOM": "GB", "UK": "GB", "GREAT BRITAIN": "GB",
    "IRELAND": "IE", "REPUBLIC OF IRELAND": "IE",
    "CANADA": "CA", "MEXICO": "MX", "JAPAN": "JP", "CHINA": "CN", "SOUTH KOREA": "KR",
    "KOREA": "KR", "BERMUDA": "BM", "BAHAMAS": "BS", "DOMINICAN REPUBLIC": "DO",
    "PUERTO RICO": "PR", "SPAIN": "ES", "FRANCE": "FR", "ITALY": "IT", "GERMANY": "DE",
    "SWITZERLAND": "CH", "AUSTRALIA": "AU", "NEW ZEALAND": "NZ", "SOUTH AFRICA": "ZA",
    "UNITED ARAB EMIRATES": "AE", "UAE": "AE", "SAUDI ARABIA": "SA", "QATAR": "QA",
    "SINGAPORE": "SG", "THAILAND": "TH", "INDIA": "IN", "KENYA": "KE", "MALAYSIA": "MY",
    "PORTUGAL": "PT", "NETHERLANDS": "NL", "BELGIUM": "BE", "SWEDEN": "SE", "DENMARK": "DK",
    "AUSTRIA": "AT", "CZECH REPUBLIC": "CZ", "CZECHIA": "CZ", "MOROCCO": "MA",
}


def iso2(x):
    t = str(x or "").strip().upper()
    if not t:
        return ""
    if len(t) == 2:
        return t
    return _ISO.get(t, t[:2] if len(t) > 2 else t)


# Hand-verified, and they WIN over any lookup. Every one of these is a fixed venue whose city
# name is ambiguous enough that a geocoder gets it wrong (there are six US Augustas).
CURATED = {
    "masters tournament": (33.5030, -82.0199),            # Augusta National, Augusta GA
    "the memorial tournament": (40.1462, -83.1524),       # Muirfield Village, Dublin OH
    "memorial tournament": (40.1462, -83.1524),
    "the players championship": (30.1975, -81.3947),      # TPC Sawgrass, Ponte Vedra Beach FL
    "players championship": (30.1975, -81.3947),
    "genesis scottish open": (56.0400, -2.8300),          # The Renaissance, North Berwick
    "puerto rico open": (18.3800, -65.8000),              # Grand Reserve, Rio Grande PR
    "hero world challenge": (24.9900, -77.5300),          # Albany, New Providence, Bahamas
    "sentry tournament of champions": (20.9970, -156.6690),   # Kapalua Plantation, Maui
    "the sentry": (20.9970, -156.6690),
    "sony open in hawaii": (21.2700, -157.8200),          # Waialae CC, Honolulu
    "rbc heritage": (32.1400, -80.8100),                  # Harbour Town, Hilton Head SC
    "travelers championship": (41.7600, -72.7300),        # TPC River Highlands, Cromwell CT
    "wm phoenix open": (33.6400, -111.9100),              # TPC Scottsdale
    "arnold palmer invitational": (28.4200, -81.5000),    # Bay Hill, Orlando FL
    "valspar championship": (28.0900, -82.6600),          # Innisbrook, Palm Harbor FL
    "charles schwab challenge": (32.7200, -97.4100),      # Colonial, Fort Worth TX
    "wells fargo championship": (35.1600, -80.8500),      # Quail Hollow, Charlotte NC
    "truist championship": (35.1600, -80.8500),
    "john deere classic": (41.4500, -90.4600),            # TPC Deere Run, Silvis IL
    "rocket mortgage classic": (42.3900, -83.1000),       # Detroit GC
    "rocket classic": (42.3900, -83.1000),
    "wyndham championship": (36.1000, -79.8600),          # Sedgefield CC, Greensboro NC
    "fedex st. jude championship": (35.0500, -89.8000),   # TPC Southwind, Memphis TN
    "fedex st jude championship": (35.0500, -89.8000),
    "the genesis invitational": (34.0500, -118.5000),     # Riviera CC, Pacific Palisades CA
    "genesis invitational": (34.0500, -118.5000),
    "the american express": (33.6900, -116.3100),         # PGA West, La Quinta CA
    "farmers insurance open": (32.9000, -117.2500),       # Torrey Pines, San Diego CA
    "at&t pebble beach pro-am": (36.5680, -121.9500),     # Pebble Beach CA
}


def curated(name):
    k = " ".join(str(name or "").lower().split())
    if k in CURATED:
        return CURATED[k]
    for c, v in CURATED.items():
        if c in k:
            return v
    return None


def espn_venue(eid):
    """(lat, lon, city, state, country, why) for ONE event_id."""
    core = None
    try:
        core = get("https://sports.core.api.espn.com/v2/sports/golf/leagues/pga/events/%s" % eid)
    except Exception:                                                   # noqa: BLE001
        core = None
    if core is None:
        # sports.core does not carry every event id; the SITE summary exposes the same venue.
        try:
            site = get("https://site.api.espn.com/apis/site/v2/sports/golf/pga/summary?event=%s"
                       % eid)
        except Exception as e:                                          # noqa: BLE001
            return None, None, None, None, None, "core 404 and site failed: %s" % str(e)[:34]
        la, lo, city, st, ctry = [], [], [], [], []
        walk(site, "latitude", la)
        walk(site, "longitude", lo)
        walk(site, "city", city)
        walk(site, "state", st)
        walk(site, "country", ctry)
        if city or la:
            return ((la[0] if la else None), (lo[0] if lo else None),
                    (city[0] if city else None), (st[0] if st else None),
                    (ctry[0] if ctry else None), "espn site summary")
        return None, None, None, None, None, "core 404 and site had no venue"
    refs = []
    walk(core, "$ref", refs)
    vref = next((str(r) for r in refs if "/venues/" in str(r)), None)
    if not vref:
        return None, None, None, None, None, "no venue reference on the event"
    try:
        ven = get(vref.replace("http://", "https://"))
    except Exception as e:                                              # noqa: BLE001
        return None, None, None, None, None, "venue fetch failed: %s" % str(e)[:40]
    la, lo, city, st, ctry = [], [], [], [], []
    walk(ven, "latitude", la)
    walk(ven, "longitude", lo)
    walk(ven, "city", city)
    walk(ven, "state", st)
    walk(ven, "country", ctry)
    return ((la[0] if la else None), (lo[0] if lo else None),
            (city[0] if city else None), (st[0] if st else None),
            (ctry[0] if ctry else None), "espn venue")


def geocode(city, state, country):
    """open-meteo geocoding, REJECTING any hit whose country disagrees with ESPN."""
    if not city:
        return None, None, "no city to geocode"
    u = ("https://geocoding-api.open-meteo.com/v1/search?name=%s&count=20&language=en&format=json"
         % urllib.parse.quote(str(city)))
    try:
        j = get(u)
    except Exception as e:                                              # noqa: BLE001
        return None, None, "geocode failed: %s" % str(e)[:40]
    hits = j.get("results") or []
    if not hits:
        return None, None, "no geocoder hit for %r" % str(city)[:20]
    want_c = str(country or "").strip().upper()
    want_s = str(state or "").strip().upper()

    want_i = iso2(want_c)

    def score(h):
        s = 0
        cc = str(h.get("country_code") or "").upper()
        cn = str(h.get("country") or "").upper()
        a1 = str(h.get("admin1") or "").upper()
        if want_i and (want_i == iso2(cc) or want_i == iso2(cn)):
            s += 10
        if want_s and (want_s == a1 or want_s in a1 or a1[:2] == want_s[:2]):
            s += 5
        s += min((h.get("population") or 0) / 1e6, 3)
        return s

    hits.sort(key=score, reverse=True)
    top = hits[0]
    # AMBIGUITY GATE. With no state from ESPN, two same-country candidates cannot be separated
    # by anything but population, which is a tiebreak and not evidence. Refuse.
    if not str(state or "").strip():
        wi = iso2(want_c)
        same = [h for h in hits
                if not wi or wi in (iso2(h.get("country_code")), iso2(h.get("country")))]
        want_n = " ".join(str(city or "").lower().split())
        exact = [h for h in same
                 if " ".join(str(h.get("name") or "").lower().split()) == want_n]
        if len(exact) > 1:
            # Several DIFFERENT places share this exact city name in the same country -- six US
            # Augustas. Population is a tiebreak, not evidence. Counting distinct names instead
            # let one unrelated hit ("Thayer") defeat the gate.
            return None, None, ("ambiguous %r: %d same-name same-country places, no state"
                                % (str(city)[:18], len(exact)))
    # HARD GATE: if ESPN gave a country and the best hit still disagrees, refuse.
    cc = str(top.get("country_code") or "").upper()
    cn = str(top.get("country") or "").upper()
    if want_i and not (want_i == iso2(cc) or want_i == iso2(cn)):
        return None, None, ("country mismatch: espn=%s geocoder=%s/%s"
                            % (want_c[:12], cc, cn[:14]))
    return top.get("latitude"), top.get("longitude"), ("geocoded %s/%s" % (
        top.get("admin1") or "?", cc or "?"))


def main():
    con = sqlite3.connect(str(OUT), timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("""CREATE TABLE IF NOT EXISTS venue(
        event_id TEXT PRIMARY KEY, event TEXT, year INT, lat REAL, lon REAL,
        city TEXT, state TEXT, country TEXT, why TEXT, ts TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS wx(
        event_id TEXT, date TEXT, wind REAL, gust REAL, precip REAL, tmax REAL, tmin REAL,
        rh REAL, ts TEXT, PRIMARY KEY(event_id, date))""")
    con.commit()

    pm = sqlite3.connect("file:pga_model.sqlite?mode=ro", uri=True, timeout=60)
    evs = pm.execute("SELECT event_id, event, MIN(date), MAX(date) FROM rounds "
                     "GROUP BY event_id ORDER BY MIN(date)").fetchall()
    pm.close()
    done = {r[0] for r in con.execute("SELECT event_id FROM venue WHERE lat IS NOT NULL")}
    print("events %d | venues already resolved %d" % (len(evs), len(done)), flush=True)

    nres = nfail = 0
    for i, (eid, evn, d0, d1) in enumerate(evs, 1):
        if str(eid) in done:
            continue
        cur = curated(evn)
        if cur:
            lat, lon, city, st, ctry, why = cur[0], cur[1], None, None, None, "CURATED"
        else:
            lat, lon, city, st, ctry, why = espn_venue(eid)
        if lat is None or lon is None:
            lat, lon, why2 = geocode(city, st, ctry)
            why = "%s -> %s" % (why, why2)
        con.execute("INSERT OR REPLACE INTO venue VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (str(eid), str(evn), int(str(d0)[:4]), lat, lon, city, st, ctry, why,
                     dt.datetime.utcnow().isoformat(timespec="seconds")))
        con.commit()
        if lat is not None:
            nres += 1
        else:
            nfail += 1
        if i % 20 == 0:
            print("   %d/%d  resolved %d  unresolved %d" % (i, len(evs), nres, nfail), flush=True)
        time.sleep(0.35)
    print("venues done: %d resolved, %d unresolved this pass" % (nres, nfail), flush=True)

    # ── daily weather for every resolved venue over its own date window ────────────────────────
    rows = con.execute("SELECT event_id, lat, lon FROM venue WHERE lat IS NOT NULL").fetchall()
    span = {}
    pm = sqlite3.connect("file:pga_model.sqlite?mode=ro", uri=True, timeout=60)
    for eid, d0, d1 in pm.execute("SELECT event_id, MIN(date), MAX(date) FROM rounds "
                                  "GROUP BY event_id"):
        span[str(eid)] = (str(d0), str(d1))
    pm.close()
    havewx = {r[0] for r in con.execute("SELECT DISTINCT event_id FROM wx")}
    todo = [r for r in rows if r[0] not in havewx and r[0] in span]
    print("weather to pull for %d events" % len(todo), flush=True)
    for i, (eid, lat, lon) in enumerate(todo, 1):
        d0, d1 = span[eid]
        s = (dt.date.fromisoformat(d0) - dt.timedelta(days=3)).isoformat()
        u = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
             "&start_date=%s&end_date=%s&daily=wind_speed_10m_max,wind_gusts_10m_max,"
             "precipitation_sum,temperature_2m_max,temperature_2m_min,"
             "relative_humidity_2m_mean&timezone=UTC" % (lat, lon, s, d1))
        try:
            j = get(u, timeout=40)
        except Exception as e:                                          # noqa: BLE001
            print("   %s weather FAILED %s" % (eid, str(e)[:40]), flush=True)
            continue
        dd = j.get("daily") or {}
        ts = dd.get("time") or []
        now = dt.datetime.utcnow().isoformat(timespec="seconds")
        for k, t in enumerate(ts):
            def g(key):
                v = dd.get(key) or []
                return v[k] if k < len(v) else None
            con.execute("INSERT OR REPLACE INTO wx VALUES(?,?,?,?,?,?,?,?,?)",
                        (eid, t, g("wind_speed_10m_max"), g("wind_gusts_10m_max"),
                         g("precipitation_sum"), g("temperature_2m_max"),
                         g("temperature_2m_min"), g("relative_humidity_2m_mean"), now))
        con.commit()
        if i % 20 == 0:
            print("   wx %d/%d" % (i, len(todo)), flush=True)
        time.sleep(0.35)

    v = con.execute("SELECT COUNT(*), SUM(lat IS NOT NULL) FROM venue").fetchone()
    w = con.execute("SELECT COUNT(*), COUNT(DISTINCT event_id) FROM wx").fetchone()
    print("\nDONE  venues %d (%d resolved)  wx rows %d over %d events" % (v[0], v[1], w[0], w[1]))
    print("unresolved reasons:")
    for why, c in con.execute("SELECT why, COUNT(*) FROM venue WHERE lat IS NULL "
                              "GROUP BY why ORDER BY COUNT(*) DESC LIMIT 8"):
        print("   %4d  %s" % (c, str(why)[:78]))
    con.close()


if __name__ == "__main__":
    main()
