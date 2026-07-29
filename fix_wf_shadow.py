"""walk_forward's inner per-event query shadowed the preloaded `rows` parameter.

First iteration passed the full 5-column history correctly; the loop body then rebound `rows`
to a 3-column (player, rnd, score) list for that event, so every later iteration handed fit()
the wrong shape and it died comparing an int round number to a date string. Rename the inner
variable — the outer one is a parameter now and must survive the loop.
"""
import ast, io
p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()
old = '''        con = sqlite3.connect(DB)
        rows = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?",
                           (eid,)).fetchall()
        con.close()
        by_r = defaultdict(list)
        for pl, rnd, sc in rows:'''
new = '''        con = sqlite3.connect(DB)
        erows = con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?",
                            (eid,)).fetchall()
        con.close()
        by_r = defaultdict(list)
        for pl, rnd, sc in erows:'''
if "erows = con.execute" in s:
    print("  = already fixed")
else:
    assert old in s, "walk_forward inner-query anchor missing"
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + walk_forward inner query no longer shadows the rows parameter")
