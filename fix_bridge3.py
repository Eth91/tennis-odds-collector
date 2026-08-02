"""Correct a mislabeled diagnostic and record what the two fit levels actually mean.

`n_editions` was set to len(percourse), i.e. the COURSE count, while the per-edition slope was
computed over all 106 editions. Also: averaging within course LOWERED r (-0.540 -> -0.433)
rather than raising it, so the per-edition correlation was not merely attenuated x-noise as
first assumed — part of it is WITHIN-course year-to-year conditions (a windy edition scores
worse and yields fewer birdies). That component belongs to the wind term, not to a permanent
course factor, so the course-level fit remains the right one for course_factor, and the
between-course relationship is genuinely weaker than the old -0.777 suggested.
"""
import ast, io
p = "pga_context.py"
s = io.open(p, encoding="utf-8").read()
old = '''    out = {"a": a, "b": b, "n": len(xs), "r": r, "unmatched": misses,
           "n_editions": len(percourse), "edition_slope": ed_slope, "edition_r": ed_r,
           "level": "per-course-mean"}'''
new = '''    out = {"a": a, "b": b, "n": len(xs), "r": r, "unmatched": misses,
           "n_courses": len(percourse), "n_editions": len(ys_ed),
           "edition_slope": ed_slope, "edition_r": ed_r, "level": "per-course-mean"}'''
if '"n_courses"' in s:
    print("  = already labelled")
else:
    assert old in s
    s = s.replace(old, new, 1)
    s = s.replace('''    ed_slope, _ed_a, ed_r = _lin(list(zip(xs, ys)))''',
                  '''    ys_ed = list(ys)
    ed_slope, _ed_a, ed_r = _lin(list(zip(xs, ys)))''', 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + bridge diagnostic labels corrected")
