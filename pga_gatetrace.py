"""Trace the gate on the REAL preview markets, by wrapping is_open before running the scan."""
import datetime as dt
import pga_tee_gate as G

_orig = G.is_open
calls = []
def traced(event, market, when=None):
    dl, why = G.deadline(event, market)
    ok = _orig(event, market, when)
    calls.append((market, dl, why, ok))
    return ok
G.is_open = traced

import pga_e3 as E3
E3._TEEGATE = G          # the module aliases it at import time
E3.main() if hasattr(E3, "main") else None

print("\n  === gate decisions on the ACTUAL previews ===")
print("  %-52s %-21s %-34s %s" % ("market", "deadline", "reason", "open?"))
for m, dl, why, ok in calls:
    print("  %-52s %-21s %-34s %s"
          % (str(m)[:52], dl.isoformat() if dl else "UNRESOLVED", why[:34], "OPEN" if ok else "skip"))
n_un = sum(1 for _, dl, _, _ in calls if dl is None)
print("\n  previews gated: %d | open %d | skipped %d | of which UNRESOLVED %d"
      % (len(calls), sum(1 for c in calls if c[3]), sum(1 for c in calls if not c[3]), n_un))
if n_un:
    print("  ⚠ unresolved names are dropped — these need a matcher fix before the gate is safe")
