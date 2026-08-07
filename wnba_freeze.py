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
# WIDENED 2026-08-06. The old four covered projection and selection but NOT what reaches
# the pricer. wnba_fd_search.py recovers main lines FanDuel serves only via search, and a
# player priced on a recovered 5.5 vs a milestone 4.5 is a different bet -- Puoch went
# "no edge" -> +11.8% EV on exactly that difference. A fingerprint that omits it does not
# describe what determines the bets, which is the whole point of the fingerprint.
FILES = ["wnba_alert.py", "wnba_slip.py", "wnba_tonight.py", "wnba_wowy.py",
         "wnba_fd_search.py", "wnba_ladder_guard.py",
         "wnba_premise_sweep.py"]
MODULES = ("wnba_slip",)
VERSION = "v1.5"
FROZEN_ON = "2026-08-06"
DECISION = (
    "v1.5 (2026-08-06) — adds wnba_premise_sweep.py: pull plays whose PREMISE has publicly "
    "returned, BEFORE tip. Live case: Wheeler reb_ast 8.5 and Makani points 7.5/9.5 were flagged "
    "and PINGED on 'Ariel Atkins is out'; RotoWire posted 'Will play Thursday' (class IN) at "
    "00:07:19Z, 1h53m before the 02:00Z tip; the news was LOGGED and never consumed. Atkins "
    "started and played 29 min. The rows voided post-game via _premise_really_broke(), which runs "
    "at GRADING time — a post-mortem, not a guard — so for two hours the plays sat live on the "
    "board, on the phone, and held TOP-2 slots on LA/MIN a real play could have used. A void is "
    "not free; 6 of the last 26 rows were premise-break voids. "
    "suppressed() is the one gate the board and slip share, but it only knows 'human vetoed' and "
    "'SUBJECT ruled out' — not 'the OUT player came back'. The sweep writes the durable veto that "
    "gate already honours (data, not code), so board+slip+alert drop together and the coherence "
    "rule holds. Ledger rows are left to grade normally: a wrong call must surface in the record "
    "rather than hide there. Conservative on multi-out — ANY returning member pulls the play, "
    "since the projection was priced on the full vacated pool. "
    "Validated by --replay 2026-08-06: matches all three real rows off the real RotoWire event, "
    "writing nothing. "
    "STILL UNVALIDATED FROM v1.4: the fd_search recovery path (wnba_twopass_test.py, cron "
    "2026-08-07 22:00Z). Record continuity unchanged — the last independently-validated line "
    "remains v1.2 at 33-16 / +18.05u.")


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
