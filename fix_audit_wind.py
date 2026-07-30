"""Report the wind term's centring in the audit — an off-centre wind term is a standing bias
that nothing else would surface, because the course factor and the market anchor absorb it."""
import ast, io
p = "pga_audit.py"
s = io.open(p, encoding="utf-8").read()
old = '''print("    wind coefficient       : %+.5f/km/h  r=%+.3f  n=%d obs / %d events  %s"
      % (wf["w"], wf.get("r") or 0, wf.get("n") or 0, wf.get("events") or 0,
         "ASSUMED" if wf.get("assumed") else "FITTED (" + str(wf.get("design")) + ")"))'''
new = '''print("    wind coefficient       : %+.5f/km/h  r=%+.3f  n=%d obs / %d events  %s"
      % (wf["w"], wf.get("r") or 0, wf.get("n") or 0, wf.get("events") or 0,
         "ASSUMED" if wf.get("assumed") else "FITTED (" + str(wf.get("design")) + ")"))
_mw = wf.get("mean_wind")
print("       centred on %s km/h %s"
      % (("%.1f" % _mw) if _mw else ("%.1f" % C.WIND_REF),
         "(the fitted sample's own mean -> term is mean-zero)" if _mw
         else "(WIND_REF fallback: the fit has no recorded mean, so the term carries a "
              "standing bias at average conditions)"))'''
if "centred on" in s:
    print("  = already reports centring")
else:
    assert old in s
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + audit reports the wind term's centring")
