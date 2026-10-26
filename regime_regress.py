"""Regression: the MAJORS path must be byte-identical to what shipped before the regime split.

A change that quietly moves majors would be indistinguishable from a change that only moves
non-majors, right up until a major is priced. So this compares the NEW module against the
pre-patch backup on the same field, same seed, and requires EXACTLY zero difference for a major.
"""
import importlib.util
import sys
from pathlib import Path

import pga_ruler as NEW


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


OLD = load("/tmp/pga_ruler_pre.py", "pga_ruler_pre")

R_raw, _ = NEW.fit(asof="2026-08-13")
R = {NEW.norm(k): v for k, v in R_raw.items()}
field = list(R_raw)[:140]
KEYS = ("win", "top5", "top10", "top20", "win_ties", "top5_ties", "top10_ties", "top20_ties")

# --- 1. MAJOR: must be identical ------------------------------------------------------------
maj = NEW.shape_slopes("Masters Tournament")
assert maj is None, "majors must resolve to None (=> SHAPE_SLOPE), got %r" % (maj,)
a = OLD.simulate(R, field, n_sims=4000, seed=7)
b = NEW.simulate(R, field, n_sims=4000, seed=7, shape_slope=maj)
d = max(abs(a[p][k] - b[p][k]) for p in a for k in KEYS)
print("MAJOR path   max |old-new| = %.12f   (MUST be exactly 0.0)" % d)
ok = (d == 0.0)

# --- 2. NON-MAJOR: must actually change, in the expected direction ---------------------------
std = NEW.shape_slopes("PGA FedEx St Jude Championship 2026")
c = NEW.simulate(R, field, n_sims=4000, seed=7, shape_slope=std)
d2 = max(abs(a[p][k] - c[p][k]) for p in a for k in KEYS)
print("NON-MAJOR    max |old-new| = %.6f   (must be > 0 — the fix has to do something)" % d2)
ok = ok and d2 > 0

# a smaller stretch => the favourite's top-N comes DOWN toward the field
fav = min(field, key=lambda p: (R.get(NEW.norm(p)) or R[p])[0])
print("\nfavourite %s:" % fav)
for k in ("win", "top5", "top10", "top20"):
    print("   %-6s 1.30 -> %.4f   fitted -> %.4f   (%+.4f)" % (k, a[fav][k], c[fav][k],
                                                               c[fav][k] - a[fav][k]))
# field totals must still be preserved by the recal
for k in ("win", "top10", "top20"):
    sa, sc = sum(a[p][k] for p in a), sum(c[p][k] for p in c)
    print("   sum(%-6s) 1.30 %.4f  fitted %.4f" % (k, sa, sc))
    ok = ok and abs(sa - sc) < 1e-6

print("\n%s" % ("PASS" if ok else "FAIL"))
raise SystemExit(0 if ok else 1)
