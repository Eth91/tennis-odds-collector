"""Fit the bridge at the level it is USED, not one level below.

Per-edition fitting (n=106) gave r=-0.540 where name-collapsed fitting gave -0.777. The drop
is not new honesty about the relationship — it is errors-in-variables. A single edition's
scoring diff is a noisy measure of the course's difficulty, and noise in x attenuates a
regression slope toward zero. course_factor() then feeds the fitted slope a course-AVERAGED
diff, which is much less noisy, so a slope fitted on single editions systematically
under-predicts.

So: pair every edition to its OWN year's scoring diff (keeping that fix, which was a genuine
bug), then average within course before regressing — matching the application exactly. Both
fits are reported so the attenuation stays visible rather than being hidden in a constant.
"""
import ast, io
p = "pga_context.py"
s = io.open(p, encoding="utf-8").read()

old = '''        cand = [(m, yr) for (ev, yr), (m, n) in ev_mean.items()
                if _ev_match(ev, tname) and (yr_t is None or int(yr) == yr_t)]
        if not cand:
            misses += 1
            continue
        m, yr = cand[0]
        xs.append(m - base.get(yr, m))
        ys.append(obs / exp)
    if len(xs) < 6:
        return None
    mx, my = st.mean(xs), st.mean(ys)'''
new = '''        cand = [(m, yr) for (ev, yr), (m, n) in ev_mean.items()
                if _ev_match(ev, tname) and (yr_t is None or int(yr) == yr_t)]
        if not cand:
            misses += 1
            continue
        m, yr = cand[0]
        xs.append(m - base.get(yr, m))
        ys.append(obs / exp)
        ckey = " ".join(sorted(_ev_tokens(tname)))
        percourse.setdefault(ckey, []).append((m - base.get(yr, m), obs / exp))
    if len(xs) < 6:
        return None
    # per-edition slope, kept only for the diagnostic below
    def _lin(pts):
        ax = [q[0] for q in pts]
        ay = [q[1] for q in pts]
        m1, m2 = st.mean(ax), st.mean(ay)
        d = sum((x - m1) ** 2 for x in ax)
        sl = (sum((x - m1) * (y - m2) for x, y in pts) / d) if d else 0.0
        s1, s2 = st.pstdev(ax), st.pstdev(ay)
        rr = ((sum((x - m1) * (y - m2) for x, y in pts) / len(pts)) / (s1 * s2)
              if s1 and s2 else None)
        return sl, m2 - sl * m1, rr
    ed_slope, _ed_a, ed_r = _lin(list(zip(xs, ys)))
    # AVERAGE WITHIN COURSE, then fit: this is the level course_factor() applies the bridge at
    agg = [(st.mean([q[0] for q in v]), st.mean([q[1] for q in v]))
           for v in percourse.values() if v]
    if len(agg) >= 6:
        xs = [q[0] for q in agg]
        ys = [q[1] for q in agg]
    mx, my = st.mean(xs), st.mean(ys)'''
assert old in s
if "percourse.setdefault" in s:
    print("  = already course-level")
else:
    s = s.replace(old, new, 1)
    s = s.replace('''    xs, ys = [], []
    misses = 0''', '''    xs, ys = [], []
    percourse = {}
    misses = 0''', 1)
    s = s.replace('''    out = {"a": a, "b": b, "n": len(xs), "r": r, "unmatched": misses}''',
                  '''    out = {"a": a, "b": b, "n": len(xs), "r": r, "unmatched": misses,
           "n_editions": len(percourse), "edition_slope": ed_slope, "edition_r": ed_r,
           "level": "per-course-mean"}''', 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + bridge fit at course level, per-edition slope kept as a diagnostic")
