"""A FALSE POSITIVE here silently applies the majors 1.30 stretch to an ordinary event -- the
exact defect being fixed. So classification is checked by name, not assumed."""
import pga_ruler as RU

CASES = [
    ("Masters Tournament", True), ("PGA Championship", True), ("The Open", True),
    ("U.S. Open", True), ("US Open", True),
    ("BMW PGA Championship", False), ("BMW Australian PGA Championship", False),
    ("Genesis Scottish Open", False), ("Omega European Masters", False),
    ("Betfred British Masters", False), ("Commercial Bank Qatar Masters", False),
    ("PGA FedEx St Jude Championship 2026", False), ("PGA Wyndham Championship 2026", False),
    ("LPGA AIG Women's Open 2026", False), ("The Genesis Invitational", False),
    ("Puerto Rico Open", False), ("Valero Texas Open", False),
]
bad = 0
for name, want in CASES:
    got = RU.is_major(name)
    sl = RU.shape_slopes(name)
    tag = "1.30 (unchanged)" if sl is None else "fitted std"
    ok = "ok " if got == want else "FAIL"
    if got != want:
        bad += 1
    print("   %s %-40s major=%-6s -> %s" % (ok, name[:40], got, tag))
print("\n%d misclassified" % bad)
raise SystemExit(1 if bad else 0)
