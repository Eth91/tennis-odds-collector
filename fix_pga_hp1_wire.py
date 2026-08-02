"""Wire live_tid into pga_e3's rates() call so H-P1 actually fires in the pricing path."""
import ast, io, shutil
P="pga_e3.py"; s=io.open(P,encoding="utf-8").read()
if "live_tid=" in s:
    print("  = already wired"); raise SystemExit(0)
old = "            BR, _fr = B.rates(course_factor=_cf, wind_kmh=_wind, course_name=evn)"
new = ('''            # H-P1 (2026-07-31): pass the live event so rates() can shift each player by the
            # form they have shown THIS week. rates() drops live_tid from its own baseline, so the
            # residual it measures is not computed against a number containing itself. Resolving
            # the tid is best-effort — on failure live_tid stays None and H-P1 simply does not
            # fire, leaving prices exactly as v1.1 produced them.
            try:
                _live_tid = B.tid_for_name(evn)
            except Exception:                                       # noqa: BLE001
                _live_tid = None
            BR, _fr = B.rates(course_factor=_cf, wind_kmh=_wind, course_name=evn,
                              live_tid=_live_tid, live_tname=evn)''')
assert old in s, "rates call anchor missing"
s=s.replace(old,new,1)
ast.parse(s)
shutil.copyfile(P,"/tmp/pga_e3.prewire.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + pga_e3 passes live_tid/live_tname to rates()")
