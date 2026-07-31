"""Write wnba_v1_freeze.json — the fingerprint the drift check compares against.

The original manifest was hand-made, which is fine once and a liability the second time: the hashes
must match EXACTLY what wnba_after_slate.sh recomputes, and that agreement should come from shared
code rather than from care. This mirrors the file list and the constants scope of the drift check
literally — FILES and MODULES below are the same values it uses, and MODULES really is wnba_slip
alone (the check does not fingerprint wnba_alert's constants, only its source).

Re-running this is the DELIBERATE ACT that starts a new record. It is not a way to silence a drift
warning: if the model changed, the evidence collected under the old fingerprint belongs to the old
version and must not be pooled with what follows.
"""
import hashlib
import io
import json
import sys

FILES = ["wnba_alert.py", "wnba_slip.py", "wnba_tonight.py", "wnba_wowy.py"]
MODULES = ("wnba_slip",)
VERSION = "v1.2"
FROZEN_ON = "2026-07-31"
DECISION = (
    "v1.2 (2026-07-31) — the sticky-incumbent swap test is now BAND-AWARE. It compared raw EV while "
    "the ranking uses (odds, band, EV), so an incumbent could hold a slot while ranking WORSE on "
    "the canonical key, and hold it on the one metric this ledger shows is ANTI-predictive. Live "
    "case: DiLeo (band 0, odds 1.9091, EV 0.213) could not displace Carleton (band 1, odds 1.9804, "
    "EV 0.462), so the card kept a TIER B play over a TIER A one — and Carleton only held the slot "
    "because she was carded at 04:08, before the v1.1 correlation-cap fix. Stickiness was "
    "protecting the output of the bug v1.1 corrected. "
    "A challenger now displaces when it is better ON THE BAND (structural, and band membership "
    "barely moves during a slate, so it cannot churn); within the same band the original "
    "SWAP_MARGIN EV rule is unchanged, preserving the anti-churn property that stickiness exists "
    "for (57% of pools once carded more than the two plays a card holds). "
    "Tier records behind the ordering: A 14-3 / 82.4% / +0.73u per bet vs B 17-11 / 60.7% / "
    "+0.20u. RESTATEMENT COST: the counted record moves 33-15 / +19.05u to 33-16 / +18.05u — one "
    "additional graded loss enters as a different incumbent yields. Reported, not hidden.")


def main():
    src = {}
    for f in FILES:
        try:
            src[f] = hashlib.sha256(io.open(f, "rb").read()).hexdigest()[:16]
        except OSError:
            print("  missing source file: %s — aborting" % f)
            sys.exit(1)
    mods = {}
    for m in MODULES:
        try:
            mod = __import__(m)
        except Exception as e:                                     # noqa: BLE001
            print("  cannot import %s (%s) — aborting; a partial fingerprint is worse than none"
                  % (m, e))
            sys.exit(1)
        mods[m] = {k: getattr(mod, k) for k in dir(mod)
                   if k.isupper() and isinstance(getattr(mod, k), (int, float, str))}
    man = {"version": VERSION,
           "frozen": FROZEN_ON,
           "sha256_16": hashlib.sha256(
               json.dumps(mods, sort_keys=True, default=str).encode()).hexdigest()[:16],
           "source_sha256_16": hashlib.sha256(
               json.dumps(src, sort_keys=True).encode()).hexdigest()[:16],
           "source_files": src,
           "decision": DECISION,
           "constants": mods}
    io.open("wnba_v1_freeze.json", "w", encoding="utf-8").write(
        json.dumps(man, indent=1, default=str))
    print("  frozen %s as %s" % (FROZEN_ON, VERSION))
    print("  constants %s" % man["sha256_16"])
    print("  source    %s" % man["source_sha256_16"])
    for f, h in src.items():
        print("    %-18s %s" % (f, h))


if __name__ == "__main__":
    main()
