"""Two bugs in the birdie bridge, both costing it data and one pairing the wrong years.

The audit reports the bridge at n=53 while 114 events are harvested. Reasons:

  COLLAPSED EDITIONS  it groups by tname, so all three editions of an event become ONE data
                      point. That throws away the per-edition variation the bridge is
                      supposed to learn from, and it makes correct year alignment impossible.

  ARBITRARY YEAR      it takes cand[0] from a fuzzy name match, so a 2024 birdie harvest
                      could be paired with a 2019 scoring diff. The tid already carries the
                      year (R2024016), so the pairing can just be exact.

  PREFIX MATCH        the name test is a 14-character prefix substring, which misses any
                      event whose name differs early ("Sony Open" vs "Sony Open in Hawaii").

Fixed: group by tid (one point per edition), match the year from the tid exactly, and match
the name on tokens rather than a prefix.
"""
import ast
import io

p = "pga_context.py"
s = io.open(p, encoding="utf-8").read()

start = s.index("def _birdie_bridge():")
end = s.index("def course_factor(", start)
# direct_course_birdie_factor now sits between them; keep whatever is after the bridge body
mid = s.index("def direct_course_birdie_factor(", start)
old_body = s[start:mid]

NEW = '''def _ev_tokens(name):
    return [w for w in str(name or "").lower().replace("pga", "").split()
            if len(w) > 3 and not w.isdigit()]


def _ev_match(a, b):
    """True when two event names plausibly denote the same tournament. Token containment in
    either direction, so 'Sony Open' matches 'Sony Open in Hawaii' and 'Rocket Classic'
    matches 'Rocket Mortgage Classic' — both of which the old 14-char prefix test missed."""
    ta, tb = _ev_tokens(a), _ev_tokens(b)
    if not ta or not tb:
        return False
    return all(t in tb for t in ta) or all(t in ta for t in tb)


def _birdie_bridge():
    """Fit birdie_factor ~ a + b * (scoring_diff) so any course with mere SCORES can be
    priced for birdies.

    One point per EDITION (grouped by tid), with the edition's year taken from the tid and
    matched exactly against the scoring table. v1 grouped by name — collapsing three editions
    into one point — and then took the first fuzzy name match, which could pair a 2024 harvest
    with a 2019 scoring diff.
    """
    c = _cache()
    if "bridge" in c:
        return c["bridge"]
    con = sqlite3.connect(DB)
    hole = con.execute(
        "SELECT tid, tname, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
        "FROM birdie_rounds GROUP BY tid").fetchall()
    con.close()
    if not hole:
        return None
    tot = defaultdict(lambda: [0, 0])
    for _t, _n, a3, b3, a4, b4, a5, b5 in hole:
        for par, (h, b) in ((3, (a3, b3)), (4, (a4, b4)), (5, (a5, b5))):
            tot[par][0] += h or 0
            tot[par][1] += b or 0
    g = {p: (v[1] / v[0] if v[0] else 0.15) for p, v in tot.items()}
    ev_mean, base = event_scoring()
    xs, ys = [], []
    misses = 0
    for tid, tname, a3, b3, a4, b4, a5, b5 in hole:
        holes = (a3 or 0) + (a4 or 0) + (a5 or 0)
        if not holes:
            continue
        obs = ((b3 or 0) + (b4 or 0) + (b5 or 0)) / holes
        exp = ((a3 or 0) * g[3] + (a4 or 0) * g[4] + (a5 or 0) * g[5]) / holes
        if exp <= 0:
            continue
        yr_t = None
        d = "".join(ch for ch in str(tid or "") if ch.isdigit())[:4]
        if len(d) == 4:
            yr_t = int(d)
        cand = [(m, yr) for (ev, yr), (m, n) in ev_mean.items()
                if _ev_match(ev, tname) and (yr_t is None or int(yr) == yr_t)]
        if not cand:
            misses += 1
            continue
        m, yr = cand[0]
        xs.append(m - base.get(yr, m))
        ys.append(obs / exp)
    if len(xs) < 6:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    b = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0.0
    a = my - b * mx
    r = None
    try:
        sx, sy = st.pstdev(xs), st.pstdev(ys)
        if sx and sy:
            r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)) / (sx * sy)
    except Exception:                                              # noqa: BLE001
        pass
    out = {"a": a, "b": b, "n": len(xs), "r": r, "unmatched": misses}
    c["bridge"] = out
    _save(c)
    return out


'''
s = s[:start] + NEW + s[mid:]
ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + _birdie_bridge: per-edition points, exact year, token name match")
