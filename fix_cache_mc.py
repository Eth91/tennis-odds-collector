"""Three protective fixes found while checking the last assumed numbers.

(1) THE FITTED TERMS LIVE IN A TRACKED FILE THE LOOP REVERTS. pga_context_cache.json holds the
    wind coefficient, the wave beta and the bridge — every term measured today — and the loop
    does `git add -A -f` then resets/replays. The geocode cache was already silently wiped
    (0 entries where there were 51). The fits themselves survived this time, but a revert to an
    older copy would silently restore OLD coefficients with no error anywhere: a silent model
    regression, which is the failure mode hardest to notice. Move the authoritative cache
    OUTSIDE the repo, seeding once from the in-repo copy so nothing measured is lost.

(2) WIND_REF = 15 was assumed. fit_wind's slope is unbiased (within-event demeaned), but the
    factor is applied as 1 + w*(kmh - WIND_REF), so if typical wind is not 15 the term carries
    a standing bias at average conditions that gets absorbed invisibly by the course factor or
    the market anchor. The fit now records the sample's own mean wind and wind_factor centres
    on it, so the term is mean-zero by construction and WIND_REF is only a fallback.

(3) n_sims = 8000 leaves real Monte Carlo noise: measured across five seeds, worst-case 0.70
    points on top-20 and 1.00 on make-cut — 14-20% of the 5-point edge threshold, so a flagged
    5.0% edge could be 4.3% or 5.7% from sampling alone. Raising n_sims 4x would fix it but
    quadruples a (n_sims, k, 4) array on a 956MB box. Averaging four independent 8000-sim reps
    halves the noise at CONSTANT peak memory instead.
"""
import ast
import io

# ------------------------------------------------- (1) cache outside the repo
p = "pga_context.py"
s = io.open(p, encoding="utf-8").read()
old = 'CACHE = HERE / "pga_context_cache.json"'
new = '''# AUTHORITATIVE CACHE LIVES OUTSIDE THE REPO. It holds every fitted term (wind coefficient,
# wave beta, scoring->birdie bridge, geocodes) and the loop does `git add -A -f` then
# resets/replays tracked files — which already wiped the geocode cache once. A revert to an
# older copy would silently reinstate OLD coefficients with no error raised anywhere, so the
# in-repo file is now only a one-time SEED and a fallback for a fresh clone.
CACHE = Path.home() / ".pga_context_cache.json"
SEED_CACHE = HERE / "pga_context_cache.json"'''
if "AUTHORITATIVE CACHE LIVES OUTSIDE THE REPO" in s:
    print("  = cache already relocated")
else:
    assert old in s
    s = s.replace(old, new, 1)
    old_c = '''def _cache():
    try:
        return json.loads(CACHE.read_text())
    except Exception:                                              # noqa: BLE001
        return {}'''
    new_c = '''def _cache():
    """Read the external cache; on first run, seed it from the in-repo copy so the terms
    measured before the move are not lost."""
    try:
        return json.loads(CACHE.read_text())
    except Exception:                                              # noqa: BLE001
        pass
    try:
        seeded = json.loads(SEED_CACHE.read_text())
        if seeded:
            CACHE.write_text(json.dumps(seeded))
        return seeded
    except Exception:                                              # noqa: BLE001
        return {}'''
    assert old_c in s
    s = s.replace(old_c, new_c, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_context: cache moved to ~/.pga_context_cache.json (seeded from repo copy)")

# --------------------------------------------------- (2) centre the wind term
s = io.open(p, encoding="utf-8").read()
old_w = '''    f = fit_wind(verbose=False)
    if kmh is None:
        return 1.0
    return max(0.80, min(1.15, 1.0 + f["w"] * (kmh - WIND_REF)))'''
new_w = '''    f = fit_wind(verbose=False)
    if kmh is None:
        return 1.0
    # centre on the FITTED SAMPLE's own mean wind where we have it: the slope is estimated on
    # within-event deviations, so the factor is only mean-zero if it is centred on the same
    # mean. WIND_REF stays as the fallback for a cache with no recorded mean.
    ref = f.get("mean_wind")
    if not ref or ref <= 0:
        ref = WIND_REF
    return max(0.80, min(1.15, 1.0 + f["w"] * (kmh - ref)))'''
if 'ref = f.get("mean_wind")' in s:
    print("  = wind term already centred")
else:
    assert old_w in s
    s = s.replace(old_w, new_w, 1)
    # record the sample mean wind in the fit
    old_o = '''        if b < 0:
            out = {"w": b, "n": len(xs), "events": used, "assumed": False, "r": r,
                   "design": "within-event"}'''
    new_o = '''        if b < 0:
            out = {"w": b, "n": len(xs), "events": used, "assumed": False, "r": r,
                   "design": "within-event", "mean_wind": st.mean(raw_w) if raw_w else None}'''
    assert old_o in s, "fit_wind out-dict anchor missing"
    s = s.replace(old_o, new_o, 1)
    # collect the raw (un-demeaned) winds so the mean can be recorded
    old_x = '''        for w, rate in pairs:
            xs.append(w - mw)                 # within-event wind deviation'''
    new_x = '''        for w, rate in pairs:
            raw_w.append(w)                   # un-demeaned, to record the sample mean
            xs.append(w - mw)                 # within-event wind deviation'''
    assert old_x in s, "fit_wind pairs anchor missing"
    s = s.replace(old_x, new_x, 1)
    old_i = '''    xs, ys, used = [], [], 0'''
    new_i = '''    xs, ys, used = [], [], 0
    raw_w = []'''
    assert old_i in s, "fit_wind init anchor missing"
    s = s.replace(old_i, new_i, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + fit_wind records mean_wind; wind_factor centres on it")

# ------------------------------------------------ (3) MC reps at constant memory
p2 = "pga_ruler.py"
s2 = io.open(p2, encoding="utf-8").read()
old_sig = '''def simulate(R, field, n_sims=8000, seed=7, course_fit=None, wave=None,
             wave_shift=0.0, progress=None, partial=None):'''
new_sig = '''def simulate(R, field, n_sims=8000, seed=7, course_fit=None, wave=None,
             wave_shift=0.0, progress=None, partial=None, reps=1):
    """reps>1 averages independent runs to cut Monte Carlo noise at CONSTANT peak memory.
    Measured across five seeds at 8000 sims, worst-case seed-to-seed sd was 0.70 points on
    top-20 and 1.00 on make-cut — 14-20% of the 5-point edge threshold, so a flagged 5.0%
    edge could be 4.3% or 5.7% from sampling alone. Four reps halve that; raising n_sims
    instead would quadruple a (n_sims, k, 4) array, which this 956MB box cannot afford."""
    if reps and reps > 1:
        acc = {}
        for i in range(int(reps)):
            one = simulate(R, field, n_sims=n_sims, seed=seed + 1000 * i,
                           course_fit=course_fit, wave=wave, wave_shift=wave_shift,
                           progress=progress, partial=partial, reps=1)
            if not one:
                return {}
            for pl, v in one.items():
                a = acc.setdefault(pl, {})
                for k_, val in v.items():
                    a[k_] = a.get(k_, 0.0) + val / float(reps)
        return acc'''
if "reps=1):" in s2:
    print("  = simulate already supports reps")
else:
    assert old_sig in s2
    s2 = s2.replace(old_sig, new_sig, 1)
    ast.parse(s2)
    io.open(p2, "w", encoding="utf-8").write(s2)
    print("  + simulate(reps=) averages runs at constant memory")

# E3 should use it
p3 = "pga_e3.py"
s3 = io.open(p3, encoding="utf-8").read()
old_call = '''    sim = RU.simulate(R, field, course_fit=cfit, wave=wave,
                      wave_shift=wshift) if field else {}'''
new_call = '''    # reps=4 halves Monte Carlo noise (worst case 0.70pt on top-20, ~14% of the 5pt edge
    # threshold) without growing peak memory on this box
    sim = RU.simulate(R, field, course_fit=cfit, wave=wave,
                      wave_shift=wshift, reps=4) if field else {}'''
if "reps=4" in s3:
    print("  = e3 already uses reps")
else:
    assert old_call in s3, "e3 simulate call anchor missing"
    s3 = s3.replace(old_call, new_call, 1)
    ast.parse(s3)
    io.open(p3, "w", encoding="utf-8").write(s3)
    print("  + pga_e3 simulates with reps=4")
