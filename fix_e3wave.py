"""Wire the live wave path to the orchestrator sheet + the FITTED coefficient.

Two separate defects in the block this replaces:
  SOURCE  it read pga_field.tee_times(), i.e. ESPN's per-competitor teeTime stamp, which is
          empty until the round is basically underway. That is why the audit found "0 tee
          times known -> dormant". The PGA orchestrator publishes the whole sheet days
          earlier — 294 entries for the Rocket Classic while ESPN still showed 0.
  NUMBER  the shift was `0.04 * wind_gap`, with a comment conceding the plan's thesis was
          "0.5-1.5 strokes for a real wave split, which this reproduces". Reproducing an
          assumption is not measuring one. pga_wave.fit_wave regresses the AM/PM stroke gap
          on the wave wind-exposure gap WITHIN each event-round, so course, field and par
          mix cancel, and it refuses a non-positive slope.

ESPN stays as a fallback, but now with the fitted beta rather than the placeholder, so the
degraded path is no worse than the number we can defend.
"""
import ast
import io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

old = '''        import pga_field as _PF, pga_e1 as _E1, statistics as _st
        tt = _PF.tee_times()
        if tt:
            hrs = sorted(tt.values())
            med = hrs[len(hrs) // 2]
            for p_, t_ in tt.items():
                wave[p_] = "am" if t_ <= med else "pm"
            la, lo = _PF.coords()
            if la is not None:
                w_ = _E1.wind_hours(la, lo, days=3)
                am = [_E1.exposure(w_, t_) for p_, t_ in tt.items() if wave.get(p_) == "am"]
                pm = [_E1.exposure(w_, t_) for p_, t_ in tt.items() if wave.get(p_) == "pm"]
                am = [x for x in am if x is not None]
                pm = [x for x in pm if x is not None]
                if am and pm:
                    # ~0.04 strokes per km/h of wind gap (conservative; the plan's E1 thesis
                    # is 0.5-1.5 strokes for a real wave split, which this reproduces)
                    wshift = 0.04 * (_st.mean(pm) - _st.mean(am))
        print(f"  ruler: course-fit players {len(cfit)}, wave split {len(wave)}, "
              f"wave shift {wshift:+.2f} strokes")'''

new = '''        import pga_field as _PF, pga_e1 as _E1, statistics as _st
        import pga_wave as _W, pga_birdies as _B
        la, lo = _PF.coords()
        wnote = "no orchestrator id"
        tid_ = None
        try:
            tid_ = _B.tid_for_name(evn)
        except Exception:                                          # noqa: BLE001
            tid_ = None
        if tid_:
            # refresh THIS event's sheet every run: tee times post Tue/Wed and the whole
            # point of reading the orchestrator is to see them the moment they land
            try:
                _W.harvest_tees(tids=[(tid_, evn)], verbose=False)
            except Exception:                                      # noqa: BLE001
                pass
            wave, wshift, wnote = _W.wave_shift_for(tid_, lat=la, lon=lo)
        if not wave:
            # FALLBACK: ESPN's competitor stamp, which only fills in late. Uses the fitted
            # beta, not the old 0.04 placeholder, so the degraded path is still defensible.
            tt = _PF.tee_times()
            if tt:
                hrs = sorted(tt.values())
                med = hrs[len(hrs) // 2]
                for p_, t_ in tt.items():
                    wave[p_] = "am" if t_ <= med else "pm"
                if la is not None:
                    w_ = _E1.wind_hours(la, lo, days=3)
                    am = [_E1.exposure(w_, t_) for p_, t_ in tt.items()
                          if wave.get(p_) == "am"]
                    pm = [_E1.exposure(w_, t_) for p_, t_ in tt.items()
                          if wave.get(p_) == "pm"]
                    am = [x for x in am if x is not None]
                    pm = [x for x in pm if x is not None]
                    if am and pm:
                        _f = _W.fit_wave(verbose=False)
                        wshift = (_f.get("beta", 0.02) * (_st.mean(pm) - _st.mean(am))
                                  + _f.get("intercept", 0.0))
                        wnote = "ESPN fallback sheet"
        print(f"  ruler: course-fit players {len(cfit)}, wave split {len(wave)}, "
              f"wave shift {wshift:+.2f} strokes [{wnote}]")'''

if "orchestrator id" in s:
    print("  = pga_e3.py already on pga_wave")
else:
    assert old in s, "e3 wave anchor missing"
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_e3.py wave now orchestrator-sourced with a fitted coefficient")

# the audit should report the wave the same way it reports every other term
p2 = "pga_audit.py"
a = io.open(p2, encoding="utf-8").read()
old_a = '''tt = F.tee_times()
print("    wave terms              : %d tee times known -> %s"
      % (len(tt), "ACTIVE" if tt else "dormant until Tue/Wed release"))'''
new_a = '''tt = F.tee_times()
try:
    import pga_wave as W
    import pga_birdies as _B
    wf = W.fit_wave(verbose=False)
    tid_now = _B.tid_for_name(ev)
    sheet = W.tees_for(tid_now) if tid_now else {}
    print("    wave gap (fitted)       : beta %+.4f str per km/h  r=%s  n=%d event-rounds "
          "over %d events  %s"
          % (wf.get("beta") or 0,
             ("%+.3f" % wf["r"]) if wf.get("r") is not None else "n/a",
             wf.get("n_gaps") or 0, wf.get("events") or 0,
             "ASSUMED" if wf.get("assumed") else "FITTED"))
    if wf.get("mean_abs_gap"):
        print("       mean |AM-PM| gap %.3f str, sd %.3f -> a real wave split is worth "
              "about %.2f strokes" % (wf["mean_abs_gap"], wf.get("sd_gap") or 0,
                                      wf["mean_abs_gap"]))
    print("    tee sheet               : orchestrator %d players, ESPN %d -> %s"
          % (len(sheet), len(tt), "ACTIVE" if sheet or tt else "not posted yet"))
except Exception as _e:
    print("    wave terms              : unavailable (%s)" % str(_e)[:60])'''
if "wave gap (fitted)" in a:
    print("  = pga_audit.py already reports the fitted wave")
else:
    assert old_a in a, "audit wave anchor missing"
    a = a.replace(old_a, new_a, 1)
    ast.parse(a)
    io.open(p2, "w", encoding="utf-8").write(a)
    print("  + pga_audit.py reports the fitted wave")
