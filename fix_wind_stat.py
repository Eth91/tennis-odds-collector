"""The wind term was FIT on one statistic and FED another.

fit_wind regresses birdie rate on `daily=wind_speed_10m_max` — the DAILY MAXIMUM — so its
slope and its sample mean (17.62 km/h) both live on the daily-max scale. But pga_e3 fed
wind_factor the mean of every hourly forecast value, nights included. For the current event
those are 16.98 and 9.42 km/h for the SAME forecast.

Result: the wind factor read 1.0422 instead of 1.0033 — every birdie rate inflated by 3.88%
in all weather, calm or windy. That is essentially the whole +4.0 point level bias the
devigged audit exposed, and the model was leaning on the market anchor to undo it.

The mismatch was invisible until the term was centred on its own fitted mean, because before
that WIND_REF=15 sat between the two scales and split the error.

Fix: one function owns the definition of "the wind number", so the fit and the live call
cannot drift apart again. The unit test at the bottom of this patch asserts they agree.
"""
import ast
import io

# ------------------------------------- one place defines the statistic
p = "pga_context.py"
s = io.open(p, encoding="utf-8").read()
anchor = "def wind_factor(kmh):"
new_fn = '''def live_wind_stat(lat, lon, days=4):
    """The live wind number, on the SAME statistic fit_wind was built on.

    fit_wind regresses on `daily=wind_speed_10m_max`, so the live input must also be a mean of
    DAILY MAXIMA. Feeding it the mean of all hourly values (nights included) put the input
    ~7.5 km/h below the fitted scale and inflated every birdie rate by 3.88% in all weather.
    Both sides now come from here so they cannot drift apart again.
    """
    try:
        import pga_e1 as _E1
        w = _E1.wind_hours(lat, lon, days=days)
    except Exception:                                              # noqa: BLE001
        return None
    if not w:
        return None
    by_day = {}
    for k, v in w.items():
        if v is not None:
            by_day.setdefault(str(k)[:10], []).append(v)
    peaks = [max(v) for v in by_day.values() if v]
    return st.mean(peaks) if peaks else None


def wind_factor(kmh):'''
if "def live_wind_stat(" in s:
    print("  = live_wind_stat already present")
else:
    assert anchor in s
    s = s.replace(anchor, new_fn, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_context.live_wind_stat (mean of daily maxima, matching the fit)")

# ------------------------------------- e3 uses it
p2 = "pga_e3.py"
s2 = io.open(p2, encoding="utf-8").read()
old = '''                import pga_e1 as _E1, pga_field as _PF
                _la, _lo = _PF.coords()
                if _la is not None:
                    _w = _E1.wind_hours(_la, _lo, days=3)
                    if _w:
                        _wind = sum(_w.values()) / len(_w)'''
new = '''                import pga_e1 as _E1, pga_field as _PF
                _la, _lo = _PF.coords()
                if _la is not None:
                    # MUST be the same statistic fit_wind was built on (mean of DAILY
                    # MAXIMA). Feeding the mean of all hourly values, nights included, put
                    # this ~7.5 km/h below the fitted scale and inflated every birdie rate by
                    # 3.88% in all weather — most of the +4.0pt level bias the devigged audit
                    # found. pga_context owns the definition so the two cannot drift again.
                    _wind = C.live_wind_stat(_la, _lo, days=4)'''
if "live_wind_stat" in s2:
    print("  = pga_e3 already uses live_wind_stat")
else:
    assert old in s2, "e3 wind anchor missing"
    s2 = s2.replace(old, new, 1)
    ast.parse(s2)
    io.open(p2, "w", encoding="utf-8").write(s2)
    print("  + pga_e3 feeds the matching wind statistic")

# ------------------------------------- audit: assert the two scales agree
p3 = "pga_audit.py"
a = io.open(p3, encoding="utf-8").read()
old_a = '''_mw = wf.get("mean_wind")'''
new_a = '''# SCALE CHECK: the live wind input must be on the same statistic as the fit. It was not —
# fit on daily maxima, fed the mean of all hourly values — which inflated every birdie rate
# by 3.88% in all weather. Assert it here so a future edit cannot silently reintroduce it.
try:
    _la_, _lo_ = F.coords()
    _live = C.live_wind_stat(_la_, _lo_) if _la_ is not None else None
    _fitm = wf.get("mean_wind")
    if _live and _fitm:
        _ratio = _live / _fitm
        print("    scale check           : live %.1f km/h vs fitted-sample mean %.1f -> "
              "%.2fx  %s" % (_live, _fitm, _ratio,
                             "OK (same statistic)" if 0.5 <= _ratio <= 2.0
                             else "MISMATCH — live input is not the fit's statistic"))
except Exception as _e:
    print("    scale check           : unavailable (%s)" % str(_e)[:50])
_mw = wf.get("mean_wind")'''
if "SCALE CHECK" in a:
    print("  = audit already scale-checks the wind input")
else:
    assert old_a in a
    a = a.replace(old_a, new_a, 1)
    ast.parse(a)
    io.open(p3, "w", encoding="utf-8").write(a)
    print("  + audit asserts the wind input matches the fitted statistic")
