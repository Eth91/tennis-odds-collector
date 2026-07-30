"""Apply the two changes apply_calib.py silently skipped.

Its `sub()` probe used the FIRST LINE of the replacement to detect prior application, and for
these two the replacement begins with text that already exists in the file ("out = {}" and the
unchanged first line of PAR_MIX_RULE), so both were reported as already-applied. Third time
this pattern has bitten in this session: probe on a string unique to the NEW content only.
"""
import ast, io

# --- 1. rates() must use the per-par K_H ---
p = "pga_birdies.py"
s = io.open(p, encoding="utf-8").read()
old = '''        out[pl] = {par: min(((b + K_H * frate[par]) / (h + K_H)) * ctx, 0.95)
                   for par, (h, b) in agg.items()}'''
new = '''        out[pl] = {par: min(((b + K_H_PAR.get(par, K_H) * frate[par])
                             / (h + K_H_PAR.get(par, K_H))) * ctx, 0.95)
                   for par, (h, b) in agg.items()}'''
if "K_H_PAR.get(par, K_H)" in s:
    print("  = rates() already per-par")
else:
    assert old in s, "rates() K_H anchor missing"
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + rates() now uses per-par K_H")

# --- 2. par-73 mix ---
s = io.open(p, encoding="utf-8").read()
old2 = "                72: {3: 4, 4: 10, 5: 4}, 73: {3: 4, 4: 9, 5: 5}}"
new2 = '''                72: {3: 4, 4: 10, 5: 4}, 73: {3: 3, 4: 11, 5: 4}}
# RE-VALIDATED 2026-07-29 on 114 harvested events (the rule was set on 8 and 5):
#   par 70 -> (4,12,2) in 21/27 events (78%)
#   par 71 -> (4,11,3) in 35/41 (85%)
#   par 72 -> (4,10,4) in 42/44 (95%)
#   par 73 -> (3,11,4) in 2/2  <- CORRECTED from the assumed (4,9,5). n=2 is thin, but an
#             observed mix beats an invented one, and this is only the fallback for a course
#             with no hole data at all — rare now that 114 events are harvested.'''
if "73: {3: 3, 4: 11, 5: 4}" in s:
    print("  = par-73 already corrected")
else:
    assert old2 in s, "PAR_MIX anchor missing"
    s = s.replace(old2, new2, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + par-73 mix corrected to (3,11,4)")
