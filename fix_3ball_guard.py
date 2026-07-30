"""threeball() proceeded with empty arrays when the trio did not resolve.

It returns {} if a NAMED player is unrated, but never checked that it received three players at
all — so an empty or short trio fell through to numpy with shape-(0,) scales and raised a
confusing broadcast error instead of saying what was wrong. (My own test triggered it by looking
players up with norm() against a dict keyed on raw display names.)
"""
import ast, io
p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()
old = '''    keys = []
    for p in trio:
        v = R.get(norm(p)) or R.get(p)
        if not v:
            return {}
        keys.append(v)'''
new = '''    trio = [p for p in (trio or []) if p]
    if len(trio) != 3:
        return {}                      # a 3-ball needs exactly three named players
    keys = []
    for p in trio:
        v = R.get(norm(p)) or R.get(p)
        if not v:
            return {}                  # unrated player: refuse rather than guess
        keys.append(v)'''
if "a 3-ball needs exactly three named players" in s:
    print("  = already guarded")
else:
    assert old in s
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + threeball() validates the trio")
