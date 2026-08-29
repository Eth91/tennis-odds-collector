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
VERSION = "v1.10"
FROZEN_ON = "2026-08-29"
DECISION = (
    "v1.10 (2026-08-29) — THE FORWARD RECORD IS BASE-RUNG ONLY. BASE_RUNG_EPOCH moved from "
    "2026-08-26 back to the 7/31 freeze, so the ENTIRE forward window is counted on one "
    "rule instead of being split. This SUPERSEDES the 2026-08-26 'new epoch, pooled "
    "history kept' decision — the forward window is now RESTATED. "
    "EFFECT: forward 25-21 / +2.60u / +5.6% becomes 22-12 / 64.7% / +8.11u / +23.8%. "
    "13 ladder rungs leave the forward record; they still exist in `predictions` and still "
    "grade, so the excluded arm stays measurable. "
    "⚠️ PRE-FREEZE HISTORY IS UNTOUCHED (37-20 / +18.47u, verified identical). Only rows "
    "on or after 2026-07-31 are affected. "
    "⚠️ PLAYED BETS STILL COUNT. The filter runs before the `forced` re-add, so a ladder "
    "rung with real money on it is never removed from the record (4 such rows). "
    "⚠️ THIS IS STILL PR-005, WHICH REMAINS OPEN AND UNVALIDATED at n=34. Quoting the "
    "restated number is an operator reporting decision, NOT evidence that the filter works. "
    "— prior v1.9 / v1.8 decisions follow —"
    "\n\n"
    "v1.9 (2026-08-26) — BASE-RUNG EPOCH. Operator-authorised 1-week trial. Within a "
    "(date, player, stat) group the selection now keeps ONLY the rung nearest even money; "
    "the extra ladder rungs come off the BOARD, the ALERT and the RECORD together, because "
    "all three read wnba_slip.current_selection (dashboard.py:310, wnba_alert.py:1172). "
    "EVIDENCE: forward base rungs 20-11 / +26.3% ROI vs ladder rungs 8-14 / -28.3%; the "
    "base-rung hit rate barely moved across the 7/31 freeze (64.7% -> 64.5%) while the "
    "headline halved. This is PR-005, promoted early by operator decision at n=31 — it is "
    "NOT a validated result and PR-005 stays open. "
    "⚠️ RECORD CONTINUITY — THIS IS A NEW EPOCH, NOT A RESTATEMENT. The filter is gated on "
    "pred_date >= 2026-08-26, so every historical row still counts exactly as before "
    "(all-time 60-40 / +20.39u and forward 23-20 / +1.92u are unchanged, verified). Rows "
    "from 2026-08-26 on are selected under a DIFFERENT rule and must never be silently "
    "averaged with earlier ones. Quote the two epochs separately. "
    "⚠️ THE LADDER IS STILL TRACKED. Excluded rungs remain in `predictions` and keep "
    "grading — only the SELECTION drops them — so the counterfactual is measurable for the "
    "1-week trial. REVIEW DUE 2026-09-02. "
    "⚠️ MIN-GAP IS UNCHANGED by operator decision, so the base rung is the best-priced rung "
    "that SURVIVED min-gap, not the best-priced overall. On 2026-08-26 min-gap suppressed "
    "Burke 10.5 @ 2.04 and the selection took 9.5 @ 1.87 instead. "
    "User-played rows still bypass every gate (the filter runs before the `forced` re-add). "
    "— prior v1.8 decision follows —"
    "\n\n"
    "v1.8 (2026-08-13) — ESPN HOST SWAP ONLY. site.api.espn.com began returning 403 to this "
    "VM's IP; it is NOT a User-Agent problem (a full Chrome UA still 403s) and NOT transient "
    "(every path 403s while site.web.api.espn.com and cdn.espn.com both return 200 from the "
    "same box). site.web.api serves the IDENTICAL path and payload, so the change in the two "
    "frozen files is one constant each: ESPN=/SITE= rewritten to the working host. No logic, "
    "no gate, no threshold moved. "
    "RECORD CONTINUITY: bet selection is unchanged, so v1.8 POOLS WITH v1.5/v1.7 — the counted "
    "record does NOT restart and the forward window stays 7/31-based. "
    "⚠️ SCOPE OF THE OUTAGE, MEASURED NOT ASSUMED. 27 URLs across 24 files pointed at the "
    "blocked host, 10 of them reachable from live code. But every call site has try/except "
    "plus a cache, so almost nothing actually broke: tip_times, players, matchup_context and "
    "the board all kept returning correct, per-game values (total 187.5/184.5/167.5, pace "
    "177.3/175.2/169.6 on 08-12/13). The real damage was confined to box_actuals, which is "
    "only invoked as a FALLBACK when the game-log path fails — and there it caused TWO REAL "
    "LOSSES to be recorded as voids (Nelson-Ododa 07-28 rebounds o6.5, actual 6; Ogunbowale "
    "08-09 points o14.5, actual 5). Those rows are re-graded; the corrected forward record is "
    "13-10 / 56.5% / +11.1% ROI, down from the 13-9 / 59.1% / +16.2% previously reported. "
    "THE BUG WAS NOT THE 403. A total failure was always safe: box_actuals returned an empty "
    "dict, which is falsy, and the DNP guard voids nothing. A PARTIAL parse is the danger — a "
    "dict holding 2 of 4 games is truthy, and every player from the other two looks like a "
    "DNP. box_actuals now tracks completeness separately from content (box_complete(), "
    "defaulting False so an unattempted date fails closed), marks a date incomplete when any "
    "single game's summary fails, never caches an incomplete read, and the DNP-void path "
    "requires a complete box. Same discipline _premise_really_broke already used: refuse to "
    "conclude rather than guess. "
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
