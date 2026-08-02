"""The direct course birdie factor was pooling unrelated courses.

It reported "12 edition(s), 4888 rounds" for the Rocket Classic — an event that has only
existed since 2019, and which we hold three seasons of. Cause: the token rule inherited from
course_factor accepts a match on HALF the tokens, so the word "Classic" alone pulled in the
Zurich Classic, John Deere Classic, Cognizant Classic and others. A course factor built from
six different golf courses is not a course factor.

Fix: require EVERY distinctive token. "Rocket Classic" then still matches its old name
"Rocket Mortgage Classic" (both tokens present) but no longer matches the Zurich Classic. A
renamed event matches nothing and returns None, which is correct — the bridge handles it,
and inventing course history is worse than admitting we lack it.
"""
import ast, io
p = "pga_context.py"
s = io.open(p, encoding="utf-8").read()
old = '''    for _tid, tname, nr, a3, b3, a4, b4, a5, b5 in rows:
        el = str(tname or "").lower()
        if sum(1 for w in toks if w in el) < max(1, len(toks) // 2):
            continue'''
new = '''    for _tid, tname, nr, a3, b3, a4, b4, a5, b5 in rows:
        el = str(tname or "").lower()
        # EVERY token must appear. Half-token matching made "Classic" pool six unrelated
        # courses into what is supposed to be this course's own birdie history.
        if not all(w in el for w in toks):
            continue'''
if "EVERY token must appear" in s:
    print("  = already strict")
else:
    assert old in s
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + direct_course_birdie_factor now requires all tokens")
