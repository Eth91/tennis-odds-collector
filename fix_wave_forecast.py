"""wave_shift_for was asking the ARCHIVE API about a tournament that has not happened yet.

The split came back live and correct (147 players, 78 am / 69 pm from the orchestrator sheet
while ESPN still had 0) but the shift was +0.000 with "wind unavailable" — because
_wind_hourly hits archive-api.open-meteo.com, which only serves dates in the past. The
historical FIT needs the archive; a live shift needs the forecast. Pick by date.

Same window and key format either way, so _exposure is unchanged and the fitted beta applies
to both without recalibration.
"""
import ast
import io

p = "pga_wave.py"
s = io.open(p, encoding="utf-8").read()

anchor = '''def _exposure(wind_h, tee_ms):'''
new_fn = '''def _wind_forecast(lat, lon, days=10):
    """{iso_hour_utc: wind km/h} from the FORECAST endpoint — the archive has nothing for a
    tournament that has not been played yet, which is the live case that matters."""
    u = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
         "&hourly=wind_speed_10m&forecast_days=%d&timezone=UTC"
         % (lat, lon, max(1, min(16, int(days)))))
    try:
        d = json.load(urllib.request.urlopen(
            urllib.request.Request(u, headers=UA), timeout=30))
        h = d.get("hourly") or {}
        return dict(zip(h.get("time") or [], h.get("wind_speed_10m") or []))
    except Exception:                                               # noqa: BLE001
        return {}


def _wind_for_days(lat, lon, days):
    """Archive for past dates, forecast for future ones, merged. A tournament straddling
    today (round 1 played, round 2 tomorrow) needs both."""
    out = {}
    today = dt.datetime.now(dt.timezone.utc).date()
    past = [d for d in days if d < today]
    fut = [d for d in days if d >= today]
    if past:
        out.update(_wind_hourly(lat, lon, min(past).isoformat(), max(past).isoformat()))
    if fut:
        span = (max(fut) - today).days + 2
        out.update(_wind_forecast(lat, lon, days=span))
    return out


def _exposure(wind_h, tee_ms):'''
if "_wind_for_days" not in s:
    assert anchor in s
    s = s.replace(anchor, new_fn, 1)

old_use = '''    wind_h = _wind_hourly(lat, lon, days[0].isoformat(), days[-1].isoformat())
    if not wind_h:
        return wv, 0.0, "wave split known, wind unavailable"'''
new_use = '''    wind_h = _wind_for_days(lat, lon, days)
    if not wind_h:
        return wv, 0.0, "wave split known, wind unavailable"'''
if "_wind_for_days(lat, lon, days)" not in s:
    assert old_use in s
    s = s.replace(old_use, new_use, 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_wave.py  live shift uses the forecast API for future rounds")
