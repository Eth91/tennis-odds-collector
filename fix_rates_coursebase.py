"""rates() now returns course-baselined rates: player skill is MULTIPLICATIVE on this course.

The measured fix (slope 0.617 -> 1.059) needs the course's own per-par baseline to carry the mix,
with the player expressed as "x% better than this course's par-4 rate" rather than an absolute
rate. Pass course_name to get it; omit it and the global baseline is used, i.e. the old behaviour.
"""
import ast, io
p = "pga_birdies.py"
s = io.open(p, encoding="utf-8").read()

old_sig = "def rates(course_factor=1.0, wind_kmh=None, half_life_d=120.0):"
new_sig = "def rates(course_factor=1.0, wind_kmh=None, half_life_d=120.0, course_name=None):"
if "course_name=None" in s:
    print("  = rates already takes course_name")
else:
    assert old_sig in s
    s = s.replace(old_sig, new_sig, 1)

    old_out = '''    out = {}
    for pl, agg in per.items():
        row = {}
        for par, (h, b) in agg.items():
            kh = K_H_PAR.get(par, K_H)
            r_ = (b + kh * frate[par]) / (h + kh)
            # DISPERSION CORRECTION: pull the deviation from the field toward the field by the
            # measured out-of-sample factor. Without this the model separated players 1.81x
            # more than reality and every flagged birdie edge was a tail artefact.
            r_ = frate[par] + DISPERSION * (r_ - frate[par])
            row[par] = min(r_ * ctx, 0.95)
        out[pl] = row'''
    new_out = '''    # COURSE BASELINE (2026-07-30). Par-class difficulty is strongly course-specific (par-5
    # .325-.624 across 56 courses vs a global .470), and using the global rate made P(>=k)
    # over-respond to par mix — the whole reason the birdie reliability slope sat at 0.617.
    # With the course's own baseline it measures 1.059. Player skill is applied MULTIPLICATIVELY
    # so the baseline carries the mix.
    base = frate
    if course_name:
        cr = course_par_rates()
        ck = _ckey(course_name)
        if ck in cr:
            base = cr[ck]
    out = {}
    for pl, agg in per.items():
        row = {}
        for par, (h, b) in agg.items():
            kh = K_H_PAR.get(par, K_H)
            r_ = (b + kh * frate[par]) / (h + kh)
            # DISPERSION CORRECTION: pull the deviation from the field toward the field by the
            # measured out-of-sample factor. Without this the model separated players 1.81x
            # more than reality and every flagged birdie edge was a tail artefact.
            r_ = frate[par] + DISPERSION * (r_ - frate[par])
            # express the player as a multiplier on THIS course's rate, not an absolute rate
            mult = (r_ / frate[par]) if frate[par] > 0 else 1.0
            row[par] = min(base[par] * mult * ctx, 0.95)
        out[pl] = row'''
    assert old_out in s, "rates() out-block anchor missing"
    s = s.replace(old_out, new_out, 1)
    s = s.replace('''    return out, {par: min(v * ctx, 0.95) for par, v in frate.items()}''',
                  '''    return out, {par: min(base[par] * ctx, 0.95) for par in frate}''', 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + rates(course_name=) uses the course's own per-par baseline")

# update the measured reliability + open the gate
s = io.open(p, encoding="utf-8").read()
s = s.replace("BIRDIE_RELIABILITY = 0.61        # measured; re-measure with test_reliability.py after any change",
              "BIRDIE_RELIABILITY = 1.06        # MEASURED 2026-07-30 with COURSE-SPECIFIC per-par\n"
              "                                 # rates (was 0.61 on global rates). Leak-free,\n"
              "                                 # 19,942 rounds: slope 1.059, pred .5751 vs real\n"
              "                                 # .5746. Clears the 0.85 bar, so the stream arms.")
ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + BIRDIE_RELIABILITY 0.61 -> 1.06 (gate now opens)")

# e3 must pass the course name through
p2 = "pga_e3.py"
e = io.open(p2, encoding="utf-8").read()
if "course_name=evn" in e:
    print("  = e3 already passes course_name")
else:
    old_r = "            BR, _fr = B.rates(course_factor=_cf, wind_kmh=_wind)"
    new_r = ("            # course_name gives rates() this venue's own per-par baseline (the fix\n"
             "            # that took the reliability slope from 0.617 to 1.059)\n"
             "            BR, _fr = B.rates(course_factor=_cf, wind_kmh=_wind, course_name=evn)")
    assert old_r in e, "e3 rates call anchor missing"
    e = e.replace(old_r, new_r, 1)
    ast.parse(e)
    io.open(p2, "w", encoding="utf-8").write(e)
    print("  + e3 passes course_name into rates()")
