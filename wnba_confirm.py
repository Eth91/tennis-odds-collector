"""Confirm the drop reason straight from current_selection, rather than from my reading of gkey."""
import wnba_slip as WS

DATE = "2026-07-31"
kept, dropped = None, None
try:
    res = WS.current_selection(DATE, with_dropped=True)
    kept, dropped = res if isinstance(res, tuple) else (res, [])
except TypeError:
    kept = WS.current_selection(DATE)
    dropped = []

print("=== SELECTED for %s ===" % DATE)
for r in kept or []:
    print("  %-20s %-5s %-9s o%-6s dec=%-7s ev=%+.3f d_min=%s"
          % (r.get("player"), r.get("team"), r.get("stat"), r.get("line"),
             r.get("odds"), r.get("ev") or 0, r.get("d_min")))

print("\n=== DROPPED, with the reason the code itself gives ===")
for r, why in dropped or []:
    print("  %-20s %-5s %-9s o%-6s dec=%-7s ev=%+.3f d_min=%-5s  <- %s"
          % (r.get("player"), r.get("team"), r.get("stat"), r.get("line"),
             r.get("odds"), r.get("ev") or 0, r.get("d_min"), why))

print("\n=== the ranking key, evaluated by hand on tonight's POR pool ===")
print("  gkey = (min odds, 0 if d_min in [3,8] else 1, -max ev)   sorted ASCENDING")
for nm, odds, dm, ev in (("Bridget Carleton", 1.9804, 0.3, 0.462),
                         ("Megan DiLeo", 2.04, 4.2, 0.267)):
    band = 0 if (3 <= dm <= 8) else 1
    print("    %-20s -> (%.4f, %d, %+.3f)" % (nm, odds, band, -ev))
print("  Carleton wins on term 1 by %.4f of decimal odds (%.1f%% vs %.1f%% implied)."
      % (2.04 - 1.9804, 100 / 1.9804, 100 / 2.04))
print("  Term 2 — the twice-validated 3-8 band, where ONLY DiLeo qualifies — is never reached,")
print("  because term 1 requires EXACT equality to fall through.")
