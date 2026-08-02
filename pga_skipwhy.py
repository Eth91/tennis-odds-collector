"""Which markets did the tee gate skip, and was it 'already away' or 'could not resolve the name'?

is_open() treats UNRESOLVED as closed on purpose, but that is only safe if unresolved is rare. If
these are name-match failures the gate is silently dropping perfectly good pre-tee bets, which
would be a worse bug than the one it fixes.
"""
import datetime as dt
import pga_e3 as E3
import pga_tee_gate as G

evn, rows, snap = E3.latest_event_rows()
print("  event:", evn, "| snapshot:", snap, "| now:", dt.datetime.utcnow().replace(microsecond=0))
mkts = sorted({r[1] if not isinstance(r, dict) else r.get("market") for r in rows}
              if rows and not isinstance(rows[0], dict) else {r.get("market") for r in rows})
print("  distinct markets in the snapshot: %d" % len(mkts))
open_n = away = unres = 0
for m in mkts:
    if not m:
        continue
    dl, why = G.deadline(evn, m)
    if dl is None:
        unres += 1
        print("  UNRESOLVED  %-52s %s" % (str(m)[:52], why))
    elif dt.datetime.utcnow() < dl:
        open_n += 1
    else:
        away += 1
        print("  AWAY        %-52s tee %s" % (str(m)[:52], dl))
print("\n  open %d | already away %d | unresolved %d" % (open_n, away, unres))
print("  -> unresolved rows are SKIPPED by the gate; if that count is not ~0 the name matching")
print("     needs work before this gate can be trusted.")
