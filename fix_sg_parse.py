"""Two harvest bugs: a value parser that only understood "Avg", and a mislabeled statId.

DRIVE_ACC silently harvested ZERO rows. statId 102 works and returns 181 players, but Driving
Accuracy reports a PERCENTAGE, not an "Avg" — and the parser took only `Avg` then dropped the row
when both that and a "Total*" field were missing. Any percentage-style stat would have vanished the
same way, with no error.

Also 02420 was labeled GIR; it is actually "Distance from Edge of Fairway". Greens in Regulation is
103. A wrong label is worse than a missing one — it would have been analysed as if it were GIR.
"""
import ast, io
p = "pga_sg.py"
s = io.open(p).read()
old = '''                avg = _num(vals.get("Avg"))'''
new = '''                # percentage-style stats (Driving Accuracy, GIR, Scrambling) report under their
                # own header rather than "Avg"; take the first numeric value as the per-round
                # figure instead of silently dropping the row
                avg = _num(vals.get("Avg"))
                if avg is None:
                    for _k, _v in vals.items():
                        if _k and str(_k).lower().startswith("total"):
                            continue
                        _n = _num(_v)
                        if _n is not None:
                            avg = _n
                            break'''
if "percentage-style stats" in s:
    print("  = parser already robust")
else:
    assert old in s
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w").write(s)
    print("  + parser falls back to the first numeric value")
