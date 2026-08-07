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

MANIFEST = "wnba_v1_freeze.json"
FILES = ["wnba_alert.py", "wnba_slip.py", "wnba_tonight.py", "wnba_wowy.py"]
MODULES = ("wnba_slip",)
VERSION = "v1.3"
FROZEN_ON = "2026-08-06"
DECISION = (
    "v1.3 (2026-08-06) — RE-PIN, not a model change. The v1.2 fingerprint was taken 2026-07-31 "
    "and then never updated while NINE deliberate commits landed on the frozen files, so the "
    "SPRT has been validating a moving target since. Nothing here alters selection; this records "
    "what has actually been running. Folded in: d0080478 (an empty with-set must fail CLOSED — "
    "it was worth a +26.7 min FAKE minutes boost), bab18b59 (a traded-in player's split was "
    "measured against games she played AGAINST the team), 1fa916d2 (_drop_inverted was destroying "
    "the real main line — anchor on the two-sided rung), aa9ff17c (drop rungs violating the "
    "ladder's own arithmetic; 17% of ladders did), 7d7462cf (the out-check was rewriting HISTORY), "
    "4cc6d2f0 (the board never shared the slip's gate), 0f3601bf (ladder rung stake scales with "
    "implied probability), 3e9dec7a (capture the full posted rung ladder per flag), fcf68e06 "
    "(ESPN 403s / spoofed UAs). Plus working-tree changes: the stint code path DELETED (its rate "
    "signal measured rho~0 on 30k+ observations, so admitting a spot on it was admitting noise) "
    "and the Q-tier fold fix of 2026-08-05. "
    "ALSO CARRIED, INERT: USAGE_RATE_ADJ=False. Usage-conditioning was built and REJECTED — on "
    "1,083 walk-forward beneficiary-games with real lines the flat-minutes/usage-up class hit "
    "27.8% (z=-2.07) with a MONOTONE INVERTED dose-response (d_FGA/36 >=1.0 -> -13.0, >=1.5 -> "
    "-17.1, >=2.0 -> -23.8, z=-3.30). _usage_mult() returns 1.0 while the flag is False, so it "
    "cannot touch a price. Kept as documentation of a tested negative, not as a live path. "
    "RECORD CONTINUITY: evidence gathered under v1.2 is NOT pooled with v1.3 — the nine commits "
    "include real selection-affecting fixes, so the counted record restarts from this fingerprint. "
    "The v1.2 line stood at 33-16 / +18.05u.")


def _fingerprint():
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
    return src, mods, man


def verify():
    """Compare the working tree to the RECORDED manifest. Writes nothing. Exit 1 on drift.

    This is the default action precisely because the old script had no such mode: the natural
    way to ask 'has the model drifted?' was to run it, and running it ANSWERED THE QUESTION BY
    DESTROYING IT — re-stamping current hashes under the old version label, after which the
    drift check reads clean forever. A check must never be able to launder what it checks."""
    try:
        rec = json.load(io.open(MANIFEST, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("  no readable manifest (%s) — nothing to verify against" % e)
        return 1
    src, _mods, man = _fingerprint()
    print("  recorded %s frozen %s" % (rec.get("version"), rec.get("frozen")))
    drift = []
    for f in FILES:
        want, got = rec.get("source_files", {}).get(f), src.get(f)
        ok = want == got
        print("    %-18s recorded=%s current=%s  %s"
              % (f, want, got, "ok" if ok else "DRIFT"))
        if not ok:
            drift.append(f)
    cw, cg = rec.get("sha256_16"), man["sha256_16"]
    if cw != cg:
        print("    %-18s recorded=%s current=%s  DRIFT" % ("<constants>", cw, cg))
        drift.append("<constants>")
    if drift:
        print("  DRIFT in %d: %s" % (len(drift), ", ".join(drift)))
        print("  Evidence gathered under the recorded fingerprint does NOT belong to this code.")
        print("  Re-freeze deliberately with:  python3 wnba_freeze.py --write")
        return 1
    print("  clean — the working tree matches the recorded fingerprint")
    return 0


def write():
    src, _mods, man = _fingerprint()
    io.open(MANIFEST, "w", encoding="utf-8").write(json.dumps(man, indent=1, default=str))
    print("  frozen %s as %s" % (FROZEN_ON, VERSION))
    print("  constants %s" % man["sha256_16"])
    print("  source    %s" % man["source_sha256_16"])
    for f, h in src.items():
        print("    %-18s %s" % (f, h))
    return 0


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("verify", "check", "-v", "--verify"):
        sys.exit(verify())            # DEFAULT is read-only. Rewriting must be asked for.
    if a[0] in ("--write", "write", "freeze"):
        sys.exit(write())
    print(__doc__)
    print("usage: wnba_freeze.py [verify|--write]")
    sys.exit(2)


if __name__ == "__main__":
    main()
