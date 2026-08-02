"""The audit hardcoded `wind = 10.9`, so section 6 kept grading the OLD wrong-scale input.

An audit that feeds the model a different number than production does is measuring a model
nobody runs. It now pulls the same live statistic pga_e3 uses (mean of daily maxima) and falls
back to the fitted sample mean — a neutral factor — rather than to an arbitrary constant.
"""
import ast, io
p = "pga_audit.py"
s = io.open(p, encoding="utf-8").read()
old = '''mix = B.mix_for("R2026524")
wind = 10.9'''
new = '''mix = B.mix_for("R2026524")
# Use the SAME wind statistic production uses. This was hardcoded to 10.9, which is on the
# mean-of-all-hourly-values scale the model no longer feeds — so section 6 was grading an
# input pga_e3 does not use. Falling back to the fitted sample mean gives a neutral factor
# rather than an arbitrary one.
try:
    _lat_a, _lon_a = F.coords()
    wind = C.live_wind_stat(_lat_a, _lon_a) if _lat_a is not None else None
except Exception:                                                   # noqa: BLE001
    wind = None
if not wind:
    wind = (C.fit_wind(verbose=False) or {}).get("mean_wind") or C.WIND_REF
print("    (section 6 wind input: %.1f km/h, live statistic matching the fit)" % wind)'''
if "same wind statistic production uses" in s.lower():
    print("  = already fixed")
else:
    assert old in s, "audit wind constant anchor missing"
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + audit section 6 now uses the live wind statistic")
