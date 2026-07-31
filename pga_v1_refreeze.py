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
VERSION = "v1.2"
FROZEN_ON = "2026-07-31"
DECISION = (
    "v1.2 (2026-07-31) — H-P1 ADOPTED: pga_birdies.rates() shifts each player by the form they "
    "have shown THIS tournament. Previously R2+ was priced with zero knowledge of the current "
    "event (the harvest runs weekly), so a player who shot 65 and one who shot 77 were priced "
    "identically while the book had fully absorbed the difference. rates() now takes live_tid, "
    "EXCLUDES that event from its own historical baseline, fetches the completed rounds live, and "
    "adds FORM_R * (actual - expected) to every par rate, where expected uses the FIELD's actual "
    "rate this week so conditions (wind, pins, setup) are carried by the field rather than "
    "mistaken for form. "
    "MEASURED: r=+0.152 on 42,557 player-rounds / 114 events after removing round-level "
    "conditions, with leave-one-event-out baselines — R1->R2 +0.150 (n=12,593), R2->R3 +0.156 "
    "(n=7,757), R3->R4 +0.156 (n=7,406) — against a cross-event null of -0.005. Worth ~0.27 "
    "birdies per 18 (residual sd 1.79). "
    "VERIFIED on the live event: 139-140 players shifted; hot players mean +0.0094/hole, cold "
    "-0.0127/hole (Malnati 9 birdies -> +0.041, Dunlap 1 birdie -> -0.027), so the sign is right. "
    "Flag mix moved 3over/6under -> 6over/4under. "
    "*** ADOPTED AGAINST THE STANDING RULE, at the user's direction. H-P1 was registered as "
    "requiring a paired SPRT over >=100 PROSPECTIVE bets and has not had one. Mitigating: it is "
    "not a threshold fitted to our betting record but an information source measured on 27,756 "
    "independent round-pairs with a clean null, and the model had ZERO scored bets so no outcome "
    "could have informed it. It remains a departure from the adoption rule and is recorded as one. "
    "v1.1's record was 0-0; the 11 R2 flags logged under v1.1 belong to v1.1 and must not be "
    "pooled with what v1.2 produces. ***")


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
