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
VERSION = "v1.1"
FROZEN_ON = "2026-07-31"
DECISION = (
    "v1.1 (2026-07-31) — correlation cap ranks on the A-BAND (3-8) before odds, not only the "
    "shadow band (<0 or >8). The cap keeps ONE player per team-game prop-family, so the survivor "
    "is automatically the cascade favourite; with both legs inside 0-8 the old band term was "
    "identical for both and a coin-flip price gap decided. POR 2026-07-31: Carleton d_min +0.3 at "
    "1.9804 beat DiLeo d_min +4.2 at 2.04 — 1.5 pts of implied probability — which meant the cap "
    "was choosing a TIER B over a TIER A (counted ledger: A 14-3 / 82.4% / +0.73u per bet vs "
    "B 17-11 / 60.7% / +0.20u). This is what the cap's own 2026-07-19 comment already intended; it "
    "was implemented with the shadow band so it only fired when a leg fell outside 0-8. "
    "Reconstructed over all 32 logged cap contests it changes ZERO past bets — no contest in the "
    "record has the split-band shape — so it is a correction of an internal contradiction, not a "
    "tune fitted to results. v1.0's prospective window (2026-07-30) held 2 graded bets; they "
    "belong to v1.0 and are not pooled forward.")


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
