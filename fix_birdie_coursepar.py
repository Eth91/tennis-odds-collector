"""Birdie fix: COURSE-SPECIFIC per-par rates (+ the measured day factor).

The beta-binomial was the wrong suspect. Measured per-round over-dispersion is real — PHI=0.0233,
theta sd 15.3% — but it only lifts the reliability slope 0.608 -> 0.644, and even 4x it reaches
0.748. The actual blocker was the HOLE-MIX sensitivity: the model applied GLOBAL per-par rates when
par-class difficulty is strongly course-specific. Measured across 56 courses:
    par-5  global .470  |  course range .325-.624  (sd .066)
    par-4  global .175  |  course range .115-.315  (sd .036)
So a universal .470 on the highest-rate class was a ~30% error, and P(>=k) over-responded to any
change in par mix. That is also why collapsing every player to the field rate still left slope 0.55
— the residual was never about players.

Leak-free measurement, early-half rates -> late-half rounds, 19,942 rounds:
    GLOBAL per-par rates      slope 0.617   pred .5912 vs real .5746
    COURSE-SPECIFIC rates     slope 1.059   pred .5751 vs real .5746
1.059 clears the 0.85 arming bar, so the birdie stream can be un-gated on measured grounds.

Player skill becomes MULTIPLICATIVE on the course baseline (a player is x% better than this course's
par-4 rate) rather than an absolute rate, which is what lets the course baseline carry the mix.
CAVEAT recorded in code: a reconfigured course (Detroit 2026 changed courseId 876 -> 947 and par 72
-> 70) may not inherit its own history cleanly, so the baseline is shrunk toward global on hole
count (K=400) rather than trusted outright.
"""
import ast, io

p = "pga_birdies.py"
s = io.open(p, encoding="utf-8").read()

if "def course_par_rates(" in s:
    print("  = already course-specific")
else:
    helper = '''
PHI_ROUND = 0.0233              # MEASURED 2026-07-30 on 39,722 player-rounds: per-round shared
                                # day factor, Var(theta)=PHI (theta sd 15.3%). Rounds are NOT
                                # independent hole-by-hole — a soft calm day lifts every hole.
                                # Secondary to the course-par fix (0.608->0.644 on its own) but
                                # real, and it widens the count distribution correctly.
CPAR_K = 400.0                  # holes of shrinkage of a course's par rates toward global. Keeps a
                                # thin course, or one that was RECONFIGURED (Detroit 2026 moved
                                # courseId 876->947, par 72->70), from being trusted outright.


def _ckey(tname):
    """Course key: sorted distinctive tokens, so editions of one venue pool together."""
    return " ".join(sorted(w for w in str(tname or "").lower().split() if len(w) > 3))


def course_par_rates(cache={}):
    """{course_key: {par: birdie rate}} measured per COURSE, shrunk toward the global rate.

    Par-class difficulty is strongly course-specific (par-5 ranges .325-.624 across 56 courses vs
    a global .470). Using the global rate made P(>=k) over-respond to par mix and was the whole
    reason the birdie reliability slope sat at 0.617 instead of ~1.0.
    """
    if cache:
        return cache
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT tname, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), "
                       "SUM(p5b) FROM birdie_rounds GROUP BY tname").fetchall()
    con.close()
    tot = {3: [0.0, 0.0], 4: [0.0, 0.0], 5: [0.0, 0.0]}
    per = {}
    for tn, a3, b3, a4, b4, a5, b5 in rows:
        k = _ckey(tn)
        d = per.setdefault(k, {3: [0.0, 0.0], 4: [0.0, 0.0], 5: [0.0, 0.0]})
        for par, (h, b) in ((3, (a3, b3)), (4, (a4, b4)), (5, (a5, b5))):
            d[par][0] += h or 0
            d[par][1] += b or 0
            tot[par][0] += h or 0
            tot[par][1] += b or 0
    g = {par: (v[1] / v[0] if v[0] else 0.15) for par, v in tot.items()}
    out = {"__global__": g}
    for k, d in per.items():
        out[k] = {par: (((d[par][1] + CPAR_K * g[par]) / (d[par][0] + CPAR_K))
                        if d[par][0] else g[par]) for par in (3, 4, 5)}
    cache.update(out)
    return cache


def _theta_nodes(phi=PHI_ROUND, n=11, cache={}):
    """Equal-weight discretisation of a mean-1, variance-phi day factor."""
    if phi <= 1e-9:
        return [(1.0, 1.0)]
    if n in cache:
        return cache[n]
    import statistics as _st
    k = 1.0 / phi
    nodes = []
    for i in range(n):
        q = (i + 0.5) / n
        z = _st.NormalDist().inv_cdf(q)
        x = (1 - 1 / (9 * k) + z * math.sqrt(1 / (9 * k))) ** 3
        nodes.append((max(x, 1e-6), 1.0 / n))
    m = sum(w * x for x, w in nodes)
    cache[n] = [(x / m, w) for x, w in nodes]
    return cache[n]


'''
    anchor = "def par_mix(par_total):"
    assert anchor in s
    s = s.replace(anchor, helper.lstrip("\n") + anchor, 1)
    if "\nimport math" not in s:
        s = s.replace("import sqlite3", "import math\nimport sqlite3", 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + course_par_rates(), PHI_ROUND, _theta_nodes() added")

# make p_x_or_more integrate over the day factor
s = io.open(p, encoding="utf-8").read()
if "day factor" in s.split("def p_x_or_more")[1][:400]:
    print("  = p_x_or_more already integrates the day factor")
else:
    i = s.index("def p_x_or_more(")
    j = s.index("\ndef ", i + 10)
    body = s[i:j]
    new = ('def p_x_or_more(player_rates, k_target, mix=None, phi=None):\n'
           '    """P(at least k birdies-or-better), integrated over the per-round DAY FACTOR.\n\n'
           '    Holes are not independent: a soft, calm day lifts every hole at once. Measured\n'
           '    Var(theta)=0.0233 (sd 15.3%) over 39,722 rounds. Ignoring it made the count\n'
           '    distribution too narrow. Pass phi=0 for the old independent behaviour.\n'
           '    """\n'
           '    ph = PHI_ROUND if phi is None else phi\n'
           '    if ph <= 1e-9:\n'
           '        return _p_x_indep(player_rates, k_target, mix)\n'
           '    tot = 0.0\n'
           '    for th, w in _theta_nodes(ph):\n'
           '        r = {p: min(v * th, 0.98) for p, v in player_rates.items()}\n'
           '        tot += w * _p_x_indep(r, k_target, mix)\n'
           '    return tot\n\n\n'
           + body.replace("def p_x_or_more(player_rates, k_target, mix=None):",
                          "def _p_x_indep(player_rates, k_target, mix=None):", 1))
    s = s[:i] + new + s[j:]
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + p_x_or_more integrates the measured day factor (old path kept as _p_x_indep)")
