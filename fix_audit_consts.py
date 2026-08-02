"""Add a CONSTANTS section: every tunable, its value, and how that value was arrived at.

The point of the audit is that nothing in the model should be un-evidenced. Until now the
constants were invisible to it — which is exactly how seven of them stayed unfitted.
"""
import ast, io
p = "pga_audit.py"
s = io.open(p, encoding="utf-8").read()
anchor = '''print("\\n" + "=" * 72)
print("AUDIT COMPLETE")'''
new = '''# --------------------------------------------------------------- 9. constants
print("\\n[9] CONSTANTS — value and provenance (nothing here should be un-evidenced)")
try:
    import pga_birdies as _B
    import pga_context as _C
    rows = [
        ("RHO", RU.RHO, "0.25",
         "MEASURED: ANOVA 0.055 (44,580 dof) / round-pair r=+0.039 (n=57,015) / 36-hole "
         "spread +0.109"),
        ("K_SHRINK", RU.K_SHRINK, "12.0", "MEASURED: EB k=noise 7.786 / true 0.709"),
        ("SIG_SHRINK", RU.SIG_SHRINK, "20.0",
         "MEASURED: EB, true sd-spread 0.23 on mean sd 2.81"),
        ("MIN_ROUNDS", RU.MIN_ROUNDS, "20", "USER-SET (2026-07-29), deliberately not fitted"),
        ("K_FIT", _C.K_FIT, "8.0",
         "MEASURED: EB 104.8 over 8,257 cells; OOS early->late slope +0.0605 implies 80"),
        ("K_COURSE", _C.K_COURSE, "2.0",
         "UNCHANGED ON PURPOSE: EB measures the direct factor, not the bridge this shrinks"),
        ("K_H par3", _B.K_H_PAR.get(3), "60.0", "MEASURED: EB, true between-player var 0.0002"),
        ("K_H par4", _B.K_H_PAR.get(4), "60.0", "MEASURED: EB, true var 0.0014"),
        ("K_H par5", _B.K_H_PAR.get(5), "60.0", "MEASURED: EB, true var 0.0015"),
        ("HALF_LIFE_D", RU.HALF_LIFE_D, "120.0",
         "TUNED on 2024-25 with 2026 HELD OUT (the only tuned constant)"),
    ]
    for nm, val, was, why in rows:
        chg = "same" if ("%.4g" % float(val)) == ("%.4g" % float(was)) else ("was " + was)
        print("    %-12s %10s  %-9s %s" % (nm, "%.4g" % float(val), chg, why[:78]))
    br = _C._birdie_bridge() or {}
    print("    bridge fit level: %s, n=%s courses / %s editions, r=%s (per-edition %s)"
          % (br.get("level"), br.get("n"), br.get("n_editions"),
             ("%+.3f" % br["r"]) if br.get("r") is not None else "n/a",
             ("%+.3f" % br["edition_r"]) if br.get("edition_r") is not None else "n/a"))
    print("    par-mix rule: %s" % {k: tuple(v.values()) for k, v in
                                    sorted(_B.PAR_MIX_RULE.items())})
except Exception as _e:
    print("    unavailable (%s)" % str(_e)[:70])

''' + anchor
if "CONSTANTS — value and provenance" in s:
    print("  = already present")
else:
    assert anchor in s
    s = s.replace(anchor, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + audit section 9: constants and provenance")
