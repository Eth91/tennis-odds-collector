"""course_factor's own event matching had the same contamination as the direct factor.

Evidence: Wyndham Championship and THE PLAYERS Championship both reported "57 prior
edition(s)" with an identical scoring diff of -0.16. They are not the same course; they
merely share the word "Championship", and the half-token rule accepted that. So the bridge
component of the course factor was, for any event with a common word in its name, an average
over most of the PGA Tour — i.e. no course signal at all, which is a good part of why the
market anchor had to correct anything in the first place.

Same fix as the direct factor: every distinctive token must appear. An event whose name we
cannot match now yields 1.00 (neutral) rather than a confident average of the wrong courses.
"""
import ast, io
p = "pga_context.py"
s = io.open(p, encoding="utf-8").read()
marker = "def course_factor(event_name, verbose=False):"
i = s.index(marker)
head, tail = s[:i], s[i:]
old = '''    for (ev, yr), (m, n) in ev_mean.items():
        el = ev.lower()
        if toks and sum(1 for w in toks if w in el) >= max(1, len(toks) // 2):
            diffs.append(m - base.get(yr, m))'''
new = '''    for (ev, yr), (m, n) in ev_mean.items():
        el = ev.lower()
        # EVERY token must appear. Half-token matching made Wyndham Championship and THE
        # PLAYERS Championship both report 57 "prior editions" of themselves with the same
        # scoring diff, because both matched on the word "Championship" — an average over
        # most of the tour, dressed up as this course's history.
        if toks and all(w in el for w in toks):
            diffs.append(m - base.get(yr, m))'''
if "EVERY token must appear. Half-token matching made Wyndham" in tail:
    print("  = bridge match already strict")
else:
    assert old in tail, "course_factor match anchor missing"
    tail = tail.replace(old, new, 1)
    s = head + tail
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + course_factor now requires all tokens")
