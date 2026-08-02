"""SPREAD = 1.30 — widen rating deviations before any rank/matchup calculation.

WHY, and why it is not sigma: sigma tested clean at every skill level (elite assigned 2.730 vs
realized 2.711; z-sd 0.97-1.01 across six rating bins; assigned skill-spread 0.232 vs reality
0.223). So the "too timid" slopes on EVERY tournament market were not a volatility problem.

They are a shrinkage problem. K_SHRINK compresses each rating toward the field, which minimises
squared error of a POINT estimate — but a rank simulation and a matchup probability are NON-LINEAR
functions of the rating spread, so feeding them shrunk point estimates makes the field look more
homogeneous than it is and pulls every probability toward its base rate. This is the exact mirror
of the birdie fix: a threshold-of-independent-events model came out too WIDE (DISPERSION=0.552),
a rank model comes out too NARROW.

TUNED on 2025 events only, mean |slope-1| across make-cut/top20/top10/win/matchup72:
    S=1.00 .2162 | S=1.15 .1355 | S=1.30 .1190 (best) | S=1.45 .1478 | S=1.60 .2191 | S=1.80 .3062
HELD-OUT 2026, never used to choose it:
    S=1.00 -> .4464    S=1.30 -> .1602   (64% less calibration error)
    match72 1.298->0.916 | cut 1.370->1.124 | top20 1.550->1.209 | top10 1.474->1.178
    win 1.539->1.206

Residual slopes are still ~1.1-1.2, so a little more stretch would likely help — but that would
mean tuning on the holdout, so S stays at the value 2025 chose.
"""
import ast, io

p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()

m = "MIN_ROUNDS = 20"
i = s.index(m)
if "SPREAD = 1.30" in s:
    print("  = SPREAD already present")
else:
    decl = ('''SPREAD = 1.30           # TUNED 2026-07-30 on 2025, HELD-OUT confirmed on 2026 (mean
                        # |slope-1| .4464 -> .1602, a 64% cut). Widens rating DEVIATIONS from the
                        # field before any rank/matchup calc. K_SHRINK is right for a point
                        # estimate but a rank sim is non-linear, so shrunk inputs made the field
                        # look homogeneous and compressed every tournament probability toward its
                        # base rate. Sigma was ruled out first: it tests clean in every rating bin.
''')
    s = s[:i] + decl + s[i:]

    # apply in simulate()
    old_sim = '''    cf = course_fit or {}
    mus = np.array([(R.get(norm(p)) or R[p])[0] + cf.get(p, cf.get(norm(p), 0.0))
                    for p in names])'''
    new_sim = '''    cf = course_fit or {}
    _r = [(R.get(norm(p)) or R[p])[0] for p in names]
    _rm = float(np.mean(_r)) if _r else 0.0
    # SPREAD: widen deviations from the field mean (see the constant's note above)
    mus = np.array([_rm + SPREAD * (v - _rm) + cf.get(p, cf.get(norm(p), 0.0))
                    for p, v in zip(names, _r)])'''
    assert old_sim in s, "simulate mus anchor missing"
    s = s.replace(old_sim, new_sim, 1)

    # apply in matchup_prob() — same stretch, so matchups and the sim agree
    old_mp = '''    (ma, sa, _), (mb, sb, _) = ra, rb
    cf = course_fit or {}
    ma = ma + cf.get(a, cf.get(norm(a), 0.0))
    mb = mb + cf.get(b, cf.get(norm(b), 0.0))'''
    new_mp = '''    (ma, sa, _), (mb, sb, _) = ra, rb
    cf = course_fit or {}
    # SPREAD must be applied here too, or matchup prices and the tournament sim would disagree
    # about the same two players. The field mean of a shrunk rating set is ~0 by construction.
    _all = [v[0] for v in R.values()]
    _rm = (sum(_all) / len(_all)) if _all else 0.0
    ma = _rm + SPREAD * (ma - _rm) + cf.get(a, cf.get(norm(a), 0.0))
    mb = _rm + SPREAD * (mb - _rm) + cf.get(b, cf.get(norm(b), 0.0))'''
    assert old_mp in s, "matchup_prob anchor missing"
    s = s.replace(old_mp, new_mp, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + SPREAD=1.30 applied in simulate() and matchup_prob()")
