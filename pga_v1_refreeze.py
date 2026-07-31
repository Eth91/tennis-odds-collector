"""Regenerate pga_v1_freeze.json — the manifest pga_after_event.sh's drift check compares against.

Mirrors that check's algorithm EXACTLY (same four modules, same constant predicate including dict
and tuple, same source-file list, same digest construction). The manifest was hand-made; a second
hand-made one would eventually disagree with the checker, which is the whole class of bug this
session kept finding. Deriving it from the same recipe is the point.

Re-running this is the DELIBERATE act that starts a new record. It is not a way to silence a drift
warning: if the model changed, evidence collected under the old fingerprint belongs to the old
version and must not be pooled with what follows.
"""
import hashlib
import io
import json
import sys

FILES = ("pga_ruler.py", "pga_e3.py", "pga_birdies.py", "pga_context.py")
VERSION = "v1.1"
FROZEN_ON = "2026-07-31"
DECISION = (
    "v1.1 (2026-07-31) — pga_e3 refuses to flag a market once THAT PLAYER has teed off, using the "
    "shared resolver in pga_tee_gate (imported by the validator too, so the model and the capture "
    "rule cannot answer 'is this still open?' differently). Golf waves span ~7 hours, so a round "
    "being under way is not the deadline; the player's own tee is. Before this, the */30 cron "
    "flagged Round 1 birdies 150-750 minutes after those players teed off (median +257). Those "
    "flags could never be scored (the pre-registered capture rule needs a pre-tee snapshot, and 26 "
    "of 37 flags this week were discarded by it), they appeared on the board as bets the "
    "validation would never count, and they were wagers into a better-informed price: on the 7 "
    "that settled, market p_fair was 0.620 for eventual winners vs 0.538 for losers, and the model "
    "disagreed hardest where it was wrong (Hojgaard 0.853 vs market 0.561, 224 min in, lost). "
    "Record 3-4, -2.10u. CONSEQUENCE: 72-hole matchbets and outrights are now flaggable only "
    "before the tournament's first ball, which matches the model's own thesis (tee-wave and wind "
    "edges are pre-round, and the ruler skips its shape recalibration in-play). AFFORDABLE BECAUSE "
    "THE MODEL HAD ZERO SCORED BETS: nothing accrued under the old behaviour, so no outcome "
    "informed this decision. v1.0's record was 0-0.")


def main():
    import pga_birdies as B
    import pga_context as C
    import pga_e3 as E
    import pga_ruler as R

    def consts(m):
        return {k: getattr(m, k) for k in dir(m)
                if k.isupper() and isinstance(getattr(m, k), (int, float, str, dict, tuple))}

    snap = {"pga_ruler": consts(R), "pga_e3": consts(E),
            "pga_birdies": consts(B), "pga_context": consts(C)}
    try:
        src = {f: hashlib.sha256(io.open(f, "rb").read()).hexdigest()[:16] for f in FILES}
    except OSError as e:
        print("  missing source file (%s) — aborting" % e)
        sys.exit(1)
    man = {"version": VERSION,
           "frozen": FROZEN_ON,
           "sha256_16": hashlib.sha256(
               json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()[:16],
           "source_sha256_16": hashlib.sha256(
               json.dumps(src, sort_keys=True).encode()).hexdigest()[:16],
           "source_files": src,
           "decision": DECISION}
    io.open("pga_v1_freeze.json", "w", encoding="utf-8").write(json.dumps(man, indent=1, default=str))
    print("  frozen %s as %s" % (FROZEN_ON, VERSION))
    print("  constants %s" % man["sha256_16"])
    print("  source    %s" % man["source_sha256_16"])
    for f, h in src.items():
        print("    %-18s %s" % (f, h))


if __name__ == "__main__":
    main()
