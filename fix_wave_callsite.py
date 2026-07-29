"""Patch ONLY the live call site (wave_shift_for), leaving fit_wave on the archive.

The previous attempt added _wind_for_days but never called it: its guard tested for the
string "_wind_for_days(lat, lon, days)", which the new `def _wind_for_days(lat, lon, days):`
line itself contains, so the edit was skipped as already-applied. Splitting the file at the
function boundary makes the target unambiguous — fit_wave MUST keep using the archive
(history) while wave_shift_for MUST use the forecast (live).
"""
import ast, io
p = "pga_wave.py"
s = io.open(p, encoding="utf-8").read()
marker = "def wave_shift_for("
i = s.index(marker)
head, tail = s[:i], s[i:]
old = "    wind_h = _wind_hourly(lat, lon, days[0].isoformat(), days[-1].isoformat())"
new = "    wind_h = _wind_for_days(lat, lon, days)"
if new in tail:
    print("  = live call site already correct")
else:
    assert old in tail, "live call site not found"
    tail = tail.replace(old, new, 1)
    s = head + tail
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + wave_shift_for now uses _wind_for_days (forecast for future rounds)")
# fit_wave must NOT have changed
assert "_wind_hourly(lat, lon," in head or "_wind_hourly(lat, lon," in s, "archive path lost"
print("  fit_wave still archive-backed:", s.count("_wind_hourly(lat, lon,"))
