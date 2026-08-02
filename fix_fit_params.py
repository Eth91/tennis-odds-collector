"""Make the ruler's constants overridable so they can be MEASURED instead of assumed.

Seven numbers were never fitted: HALF_LIFE_D, K_SHRINK, RHO, SIG_SHRINK (ruler), K_H
(birdies), K_COURSE and K_FIT (context). Nothing could measure them because fit() hard-wired
the module globals, so this threads overrides through fit() and walk_forward().

Also adds an optional pre-loaded `rows` to fit(). Tuning a half-life means ~350 as-of fits,
and re-running the 65k-row query each time is most of the cost; loading once and filtering in
memory makes a grid search practical rather than an overnight job.
"""
import ast
import io

p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()

old_sig = '''def fit(asof=None):
    """{player: (rating, sigma, n_rounds)} using ONLY rounds strictly before `asof`."""
    asof = asof or "9999"
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT event_id, date, player, rnd, score FROM rounds "
                       "WHERE date < ? ORDER BY date", (asof,)).fetchall()
    con.close()'''
new_sig = '''def all_rows():
    """Every round, sorted by date — pass to fit(rows=...) to avoid re-querying per as-of
    fit. A half-life grid search is ~350 fits and the query dominates otherwise."""
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT event_id, date, player, rnd, score FROM rounds "
                       "ORDER BY date").fetchall()
    con.close()
    return rows


def fit(asof=None, rows=None, half_life=None, k_shrink=None, sig_shrink=None,
        min_rounds=None):
    """{player: (rating, sigma, n_rounds)} using ONLY rounds strictly before `asof`.

    The four constants are overridable so pga_calib can measure them; passing None keeps the
    module default, so every existing caller is unaffected.
    """
    asof = asof or "9999"
    HL = float(half_life if half_life is not None else HALF_LIFE_D)
    KS = float(k_shrink if k_shrink is not None else K_SHRINK)
    SS = float(sig_shrink if sig_shrink is not None else SIG_SHRINK)
    MR = int(min_rounds if min_rounds is not None else MIN_ROUNDS)
    if rows is None:
        con = sqlite3.connect(DB)
        rows = con.execute("SELECT event_id, date, player, rnd, score FROM rounds "
                           "WHERE date < ? ORDER BY date", (asof,)).fetchall()
        con.close()
    else:
        rows = [r for r in rows if r[1] < asof]'''
assert old_sig in s, "fit signature anchor missing"
if "def all_rows(" not in s:
    s = s.replace(old_sig, new_sig, 1)

# the body must use the locals, not the globals
s = s.replace('''        prov[nm] = st.mean(v) * len(v) / (len(v) + K_SHRINK)''',
              '''        prov[nm] = st.mean(v) * len(v) / (len(v) + KS)''', 1)
s = s.replace('''        w = 0.5 ** (max(age, 0) / HALF_LIFE_D)''',
              '''        w = 0.5 ** (max(age, 0) / HL)''', 1)
s = s.replace('''        rating = mu * sw / (sw + K_SHRINK)               # shrink to field average''',
              '''        rating = mu * sw / (sw + KS)                     # shrink to field average''', 1)
s = s.replace('''        sigma = (sd * n + g_sd * SIG_SHRINK) / (n + SIG_SHRINK)
        if n < MIN_ROUNDS:''',
              '''        sigma = (sd * n + g_sd * SS) / (n + SS)
        if n < MR:''', 1)

old_wf = '''def walk_forward(seasons=(2025, 2026), verbose=True):'''
new_wf = '''def walk_forward(seasons=(2025, 2026), verbose=True, season_max=None, rows=None,
                 **fitkw):'''
assert old_wf in s
if "season_max=None" not in s:
    s = s.replace(old_wf, new_wf, 1)

old_q = '''    con = sqlite3.connect(DB)
    evs = con.execute("SELECT event_id, MIN(date) d, event FROM rounds GROUP BY event_id "
                      "HAVING d >= ? ORDER BY d", ("%d-01-01" % min(seasons),)).fetchall()
    con.close()'''
new_q = '''    con = sqlite3.connect(DB)
    if season_max:
        evs = con.execute(
            "SELECT event_id, MIN(date) d, event FROM rounds GROUP BY event_id "
            "HAVING d >= ? AND d <= ? ORDER BY d",
            ("%d-01-01" % min(seasons), "%d-12-31" % int(season_max))).fetchall()
    else:
        evs = con.execute(
            "SELECT event_id, MIN(date) d, event FROM rounds GROUP BY event_id "
            "HAVING d >= ? ORDER BY d", ("%d-01-01" % min(seasons),)).fetchall()
    con.close()
    if rows is None and fitkw:
        rows = all_rows()          # only worth pre-loading when a grid is being searched'''
assert old_q in s
if "season_max:" not in s:
    s = s.replace(old_q, new_q, 1)

s = s.replace('''        R, _ = fit(asof=d0)
        Rn = {norm(k): v for k, v in R.items()}''',
              '''        R, _ = fit(asof=d0, rows=rows, **fitkw)
        Rn = {norm(k): v for k, v in R.items()}''', 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_ruler.fit/walk_forward now accept measured overrides + preloaded rows")

# sanity: the globals must still be the defaults
import re as _re
for name in ("HALF_LIFE_D", "K_SHRINK", "SIG_SHRINK", "MIN_ROUNDS"):
    assert _re.search(r"^%s\s*=" % name, s, _re.M), "%s global lost" % name
print("  all four globals intact as defaults")
