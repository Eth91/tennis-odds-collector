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
VERSION = "v1.7"
FROZEN_ON = "2026-08-12"
DECISION = (
    "v1.7 (2026-08-12) — v1.6 REVERTED AFTER BACKTEST. The rotation-aware weighting shipped "
    "hours earlier was replayed against all 182 graded ledger rows on REAL lines and REAL "
    "results, walk-forward, and it LOSES: "
    "v1.5 baseline 75 bets 61.3% +15.54u | wowy-weighting only 68 bets 57.4% +8.80u | full "
    "(wowy+elevated) 44 bets 63.6% +10.09u. v1.5 wins on TOTAL UNITS, the optimisation target. "
    "v1.6's better hit rate is an ARTIFACT of dropping 41% of the bets: the dropped rows went "
    "19-18 (+3.9% ROI) — marginal winners, not losers — while the full arm ADDED 6 rows that "
    "went 1-5. Isolating the components is worse still: wowy-weighting alone drops 7 bets that "
    "went 7-0 (+6.74u, +96.3% ROI). Lowering the weighted EV threshold does not rescue it "
    "(0.07 and 0.05 both land at +8.76u, below the 0.10 arm). "
    "EVERY DIAGNOSIS BEHIND v1.6 HELD UP — Carrington/Sheldon corr -0.60, eight players above "
    "12 mpg invisible to the injury report, Sheldon's elevated sample 12 of 14 pre-Carrington. "
    "The thesis got more accurate and the betting got worse. That is the standing lesson "
    "restated: the edge comes from PRICE, not from refining the thesis. "
    "WHAT v1.7 IS: bet selection is byte-identical to v1.5. REGIME_WEIGHTS_LIVE=False gates the "
    "wiring, so game_weights is None at every call site, and the None path was regression-proven "
    "identical on wowy (20 pairs) and prop_edges (24 combos, 4 producing real edges). Verified "
    "live after the revert: Sheldon's o6.5/o9.5 edges reappear exactly as under v1.5. "
    "RECORD CONTINUITY: v1.6 was live only after the 8/12 slate had finished and placed ZERO "
    "bets, so no evidence is orphaned and v1.7 POOLS WITH v1.5 — the counted record does NOT "
    "restart. The v1.6 epoch is a documented no-op. "
    "KEPT ON PURPOSE: wnba_availability.py and the optional game_weights parameters stay. The "
    "DIAGNOSIS is genuinely valuable — it is how the Sheldon, Puoch and Juskaite confounds were "
    "identified — and it remains available for confidence/diagnostics. It simply must not "
    "silently delete bets. Re-arm only with a backtest that beats +15.54u. "
    "The last independently-validated line remains v1.2 at 33-16 / +18.05u.")


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
