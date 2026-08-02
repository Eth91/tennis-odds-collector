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
VERSION = "v1.3"
FROZEN_ON = "2026-07-31"
DECISION = (
    "v1.3 (2026-07-31) — H-P1 REVERTED, hours after v1.2 adopted it. FORM_R 0.152 -> 0.0. "
    "The +0.152 that justified it was de-conditioned at the ROUND level only. Event factors span "
    "0.81-1.24, so a week that plays easy against a player's history lifts EVERY one of their "
    "residuals that week, and R1 'predicts' R2 for reasons unrelated to form. Removing the EVENT "
    "level too: r=+0.152 -> +0.012 (0.019 birdies per 18), within-event null +0.145 -> +0.006. "
    "The original cross-event null (-0.005) could not catch it, because pairing residuals across "
    "DIFFERENT events destroys the shared week level as well as player identity and therefore "
    "tests a weaker claim than it appears to. The correct null shuffles WITHIN an event: player "
    "identity dies, the week survives. That null was what exposed it. "
    "The machinery is left in place at FORM_R=0.0 rather than deleted, because the idea is "
    "intuitive enough to be proposed again and the refutation belongs where the next person will "
    "look. Behaviour is identical to v1.1: flags back to 3 over / 6 under. "
    "LESSON RECORDED: de-condition at EVERY level that varies. Round-level alone was not enough, "
    "and a null that also breaks the confound cannot detect the confound.")


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
