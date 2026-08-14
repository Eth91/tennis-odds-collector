"""Verify everything the five-item queue changed. Adversarial: try to find the regression."""
import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import pga_ruler as RU

ok = True


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


print("1. IMPORTS")
for mod in ("pga_ruler", "pga_e3", "pga_sim", "golf_collect", "pga_wave", "pga_tee_gate"):
    try:
        __import__(mod)
        print("   ok   %s" % mod)
    except Exception as e:                                                 # noqa: BLE001
        ok = False
        print("   FAIL %s: %s" % (mod, str(e)[:60]))

print("\n2. PRE-TOURNAMENT MUST BE BIT-IDENTICAL (the change was in-play only)")
import shutil
shutil.copy(str(Path.home() / "pga_ruler.py.bak_queue"), "/tmp/pga_ruler_pre.py")
OLD = load("/tmp/pga_ruler_pre.py", "pga_ruler_pre")
R_raw, _ = RU.fit(asof="2026-08-13")
R = {RU.norm(k): v for k, v in R_raw.items()}
field = list(R_raw)[:130]
KEYS = ("win", "top5", "top10", "top20", "win_ties", "top5_ties", "top10_ties", "top20_ties")
a = OLD.simulate(R, field, n_sims=4000, seed=7, cut_n=65,
                 shape_slope=OLD.shape_slopes("PGA Wyndham Championship 2026"))
b = RU.simulate(R, field, n_sims=4000, seed=7, cut_n=65,
                shape_slope=RU.shape_slopes("PGA Wyndham Championship 2026"))
d = max(abs(a[p][k] - b[p][k]) for p in a for k in KEYS)
print("   max |old-new| pre-tournament = %.12f  %s" % (d, "ok" if d == 0.0 else "FAIL"))
ok &= (d == 0.0)

print("\n3. IN-PLAY MUST NOW STRETCH (it previously did nothing)")
prog = {p: [70.0] for p in field[:60]}
c = OLD.simulate(R, field, n_sims=4000, seed=7, cut_n=65, progress=prog)
e = RU.simulate(R, field, n_sims=4000, seed=7, cut_n=65, progress=prog)
di = max(abs(c[p][k] - e[p][k]) for p in c for k in KEYS)
print("   max |old-new| in-play = %.6f  %s (must be > 0)" % (di, "ok" if di > 0 else "FAIL"))
ok &= (di > 0)

print("\n4. FIELD TOTALS STILL EXACT")
for out, lbl in ((b, "pre-tournament"), (e, "in-play")):
    for k, want in (("win", 1.0), ("top5", 5.0), ("top10", 10.0), ("top20", 20.0)):
        got = sum(v[k] for v in out.values())
        good = abs(got - want) < 0.02
        ok &= good
        print("   %-15s %-7s %8.4f  %s" % (lbl, k, got, "ok" if good else "FAIL"))

print("\n5. G2 STILL RUNS AND STILL REPORTS THE PLACEBO")
try:
    p, n = RU.g2_gate(verbose=True)
    print("   verdict %s, n=%d" % ("PASS" if p else "FAIL", n))
except Exception as ex:                                                    # noqa: BLE001
    ok = False
    print("   FAIL g2_gate raised: %s" % str(ex)[:80])

print("\n6. FREEZE — what moved")
r = subprocess.run([sys.executable, "pga_freeze.py"], capture_output=True, text=True, timeout=300)
print("   " + "\n   ".join((r.stdout or r.stderr).strip().split("\n")[:12]))

print("\n%s" % ("ALL PASS" if ok else "REGRESSION FOUND"))
raise SystemExit(0 if ok else 1)
