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
         "wnba_premise_sweep.py", "wnba_availability.py"]
MODULES = ("wnba_slip",)
VERSION = "v1.6"
FROZEN_ON = "2026-08-12"
DECISION = (
    "v1.6 (2026-08-12) — ROTATION-AWARE PROJECTIONS. Three linked corrections; the record "
    "restarts because the PROJECTION changed, not because a gate moved. "
    "(1) AVAILABILITY IS DERIVED FROM APPEARANCES, not just the injury report. A season-ending "
    "injury drops off the daily report, so the model went blind to it: EIGHT players above 12 "
    "mpg had missed 2+ straight games with NO report entry — Fiebich (NY, 29.3mpg, 14 games), "
    "Nogic (PHX, 18), Satou Sabally (NY, 17), Barker (POR, 5). Portland alone hid 54 mpg, New "
    "York 46. Two sets, deliberately NOT nested: baseline_out cleans comparison samples however "
    "stale; flag_out fires only while an absence is still news. Barker cleans every POR baseline "
    "but can never generate a flag. "
    "(2) ARRIVALS ARE THE MIRROR CASE and are corrected too. Carrington first played for CHI on "
    "07-31 (corr with Sheldon PTS = -0.60) and Morrow for TOR on 08-05 (Juskaite went 35 -> 30 "
    "-> 25 -> 26 -> 14 min). Absence-only weighting gave pre-arrival games FULL credit so long "
    "as tonight's injured players were also out. Team membership uses the wowy_multi "
    "discriminator (same game_id AND same matchup) because ESPN's game_log is per PLAYER — "
    "keying on 'earliest game in the log' MISSED Morrow entirely while flagging Ionescu and "
    "Cotie McMahon, who had merely missed two or three early games. "
    "(3) THE ELEVATED SAMPLE IS WEIGHTED and `n` is now the Kish EFFECTIVE size. This is the "
    "one that moves bets: n feeds the credibility shrink toward the book, so a weighted mean "
    "with a raw count trusts a 3-game-equivalent sample as though it were 14. Sheldon's o6.5 "
    "(ev +0.104 on 13 elevated games) becomes NO EDGE once those 13 collapse to n_eff 5.1 — 12 "
    "of them predate Carrington. League-wide: 11 raw edges -> 6, two players reduced, three "
    "unchanged; Wheeler's stable rotation untouched at n_eff 29.0 of 29. EXPECT LOWER VOLUME — "
    "that is the intended effect, not a regression. "
    "UNWEIGHTED PATHS ARE BYTE-IDENTICAL: game_weights=None regression-tested on wowy (20 pairs) "
    "and prop_edges (24 combos, 4 producing real edges). An earlier prop_edges run passed "
    "VACUOUSLY on 45 combos that produced none, proving only [] == [] — the silent-zero class. "
    "wnba_availability.py is now a tracked source file; it drives every projection. "
    "v1.5 evidence does NOT pool with v1.6: v1.5 counted a model projecting from rotations that "
    "no longer existed. The last independently-validated line remains v1.2 at 33-16 / +18.05u.")


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
