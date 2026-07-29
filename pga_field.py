"""⛳ PGA field / tee times / scores — ESPN golf (the same infra the WNBA bot already
trusts from this box; PGA Tour's own GraphQL needs a rotating key, ESPN does not).

Everything here fails SOFT: pre-Wednesday there are no tee times and the meter simply
waits; a fetch failure serves the last cached scoreboard so grading never dies mid-week.
"""
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "pga_scoreboard_cache.json"
META = HERE / "pga_meta.json"
UA = {"User-Agent": "Mozilla/5.0"}
SB = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard"


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))


def scoreboard(fresh=True):
    """Current PGA scoreboard; caches every good fetch, serves the cache on failure."""
    if fresh:
        try:
            d = _get(SB)
            tmp = CACHE.with_suffix(".tmp")
            tmp.write_text(json.dumps(d))
            tmp.replace(CACHE)
            return d
        except Exception as e:                                # noqa: BLE001
            print(f"pga scoreboard fetch failed ({str(e)[:40]}) — using cache")
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def event(sb=None):
    """The active (or most recent) PGA event dict."""
    evs = (sb or scoreboard()).get("events") or []
    return evs[0] if evs else {}


def _walk(o, key, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key and v:
                out.append(v)
            _walk(v, key, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, key, out)


def coords(ev=None):
    """(lat, lon) for the course. ESPN embeds them inconsistently, so: walk the event for
    latitude/longitude; else geocode the venue city (open-meteo, free); cache the answer
    per event id so the lookup happens once a week."""
    ev = ev or event()
    eid = str(ev.get("id") or "")
    try:
        m = json.loads(META.read_text())
        if m.get("id") == eid and m.get("lat") is not None:
            return m["lat"], m["lon"]
    except (OSError, ValueError):
        pass
    lat = lon = None
    lats, lons = [], []
    _walk(ev, "latitude", lats)
    _walk(ev, "longitude", lons)
    if not lats:
        # scoreboard rarely carries the venue pre-tournament; the CORE api event links it.
        # Follow the venue , then fall through to city geocoding below if needed.
        try:
            core = _get("https://sports.core.api.espn.com/v2/sports/golf/leagues/pga/events/" + eid)
            refs = []
            _walk(core, "", refs)
            for r in refs:
                if "/venues/" in str(r):
                    ven = _get(str(r).replace("http://", "https://"))
                    _walk(ven, "latitude", lats)
                    _walk(ven, "longitude", lons)
                    if not lats:
                        ev = {"id": eid, "name": ev.get("name"), "_venue": ven, **ev}
                    break
        except Exception:                                     # noqa: BLE001
            pass
    if lats and lons:
        lat, lon = float(lats[0]), float(lons[0])
    else:
        addrs = []
        _walk(ev, "address", addrs)
        q = None
        for a in addrs:
            if isinstance(a, dict) and a.get("city"):
                q = a["city"]
                break
        if q:
            try:
                g = _get("https://geocoding-api.open-meteo.com/v1/search?name="
                         + urllib.request.quote(q) + "&count=1")
                r0 = (g.get("results") or [{}])[0]
                lat, lon = r0.get("latitude"), r0.get("longitude")
            except Exception:                                 # noqa: BLE001
                pass
    if lat is not None:
        META.write_text(json.dumps({"id": eid, "name": ev.get("name"),
                                    "lat": lat, "lon": lon}))
    return lat, lon


def competitors(ev=None):
    ev = ev or event()
    comp = (ev.get("competitions") or [{}])[0]
    return comp.get("competitors") or []


def tee_times(ev=None):
    """{player_name: iso_teetime} for the NEXT unplayed round. ESPN stamps teeTime on the
    competitor (current round) — pre-release this is empty and callers must wait."""
    out = {}
    for c in competitors(ev):
        nm = ((c.get("athlete") or {}).get("displayName") or "").strip()
        if not nm:
            continue
        tts = []
        _walk(c.get("status") or {}, "teeTime", tts)
        if not tts:
            _walk(c, "teeTime", tts)
        if tts:
            out[nm] = tts[0]
    return out


def round_scores(ev=None):
    """{player: [r1, r2, ...]} completed-round strokes from linescores."""
    out = {}
    for c in competitors(ev):
        nm = ((c.get("athlete") or {}).get("displayName") or "").strip()
        if not nm:
            continue
        rs = []
        for ls in c.get("linescores") or []:
            v = ls.get("value")
            if isinstance(v, (int, float)) and v > 0:
                rs.append(v)
        out[nm] = rs
    return out


def status(ev=None):
    ev = ev or event()
    st = ((ev.get("status") or {}).get("type") or {})
    return st.get("state") or "", st.get("description") or ""


if __name__ == "__main__":
    ev = event()
    la, lo = coords(ev)
    tt = tee_times(ev)
    st_, desc = status(ev)
    print(f"event: {ev.get('name')}  [{desc}]  coords: {la},{lo}")
    print(f"field: {len(competitors(ev))}  tee times known: {len(tt)}")
    for nm, t in list(tt.items())[:5]:
        print(f"   {nm:<26} {t}")
