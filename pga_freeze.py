"""⛳ FREEZE the PGA model before the Rocket Classic tees off.

Why now: today's constants were measured on data that INCLUDES completed 2026 events, so the
already-settled events cannot give a clean read. The Rocket Classic has not been played — it is
in no fit and no calibration — so its G2 result is a genuine out-of-sample test of exactly this
model. That only holds if the model does not move underneath it.

Same pattern as the cards_v27 freeze: a manifest of every constant and every fitted term plus
the git SHA, and a verifier that fails loudly on drift. Written OUTSIDE the repo as well, since
the loop resets tracked files and a manifest that can be reverted is not a manifest.

    python3 pga_freeze.py --freeze    write the manifest
    python3 pga_freeze.py            verify live state against it (exit 1 on drift)
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = Path.home() / ".pga_freeze.json"          # authoritative, outside the repo
COPY = HERE / "pga_freeze.json"                      # in-repo copy, for the record


def _sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(HERE),
                                       text=True).strip()
    except Exception:                                               # noqa: BLE001
        return None


def snapshot():
    import pga_birdies as B
    import pga_context as C
    import pga_e1 as E1
    import pga_e3 as E3
    import pga_ruler as RU
    import pga_wave as W

    def _consts(mod):
        """Every module-level constant, discovered rather than listed.

        The first version enumerated a fixed list, so adding DISPERSION — a pricing parameter —
        left the verifier reporting "FREEZE INTACT" after prices had already moved. Anything
        upper-case and numeric (or a small numeric container) is a parameter and is captured.
        """
        out = {}
        for k in dir(mod):
            if not k.isupper() or k.startswith("_"):
                continue
            v = getattr(mod, k, None)
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                out[k] = v
            elif isinstance(v, dict) and v and len(v) <= 12 and all(
                    isinstance(x, (int, float)) or isinstance(x, dict) for x in v.values()):
                out[k] = {str(a): b for a, b in v.items()}
        return out

    wind = C.fit_wind(verbose=False) or {}
    wave = W.fit_wave(verbose=False) or {}
    bridge = C._birdie_bridge() or {}
    return {
        "git_sha": _sha(),
        "purpose": "frozen for the 2026 Rocket Classic G2 read (event unplayed at freeze time)",
        # discovered, not listed: a new pricing parameter must not be able to hide
        "ruler": _consts(RU),
        "context": _consts(C),
        "birdies": _consts(B),
        "wave": _consts(W),
        "e1": _consts(E1),
        "e3": _consts(E3),
        "fitted": {
            "wind": {k: wind.get(k) for k in ("w", "r", "n", "events", "mean_wind", "assumed")},
            "wave": {k: wave.get(k) for k in ("beta", "intercept", "r", "n_gaps", "events",
                                              "assumed")},
            "bridge": {k: bridge.get(k) for k in ("a", "b", "r", "n", "n_editions", "level")},
        },
        "thresholds": {"M_EDGE": getattr(E3, "M_EDGE", None),
                       "TN_EDGE": getattr(E3, "TN_EDGE", None),
                       "OUT_RATIO": getattr(E3, "OUT_RATIO", None),
                       "OUT_EV": getattr(E3, "OUT_EV", None),
                       "TN_MIN_ODDS": getattr(E3, "TN_MIN_ODDS", None),
                       "THRESH_KMH": getattr(E1, "THRESH_KMH", None)},
    }


def _flat(d, pre=""):
    out = {}
    for k, v in (d or {}).items():
        kk = pre + str(k)
        if isinstance(v, dict):
            out.update(_flat(v, kk + "."))
        else:
            out[kk] = v
    return out


def freeze(note=None):
    """Re-stamp. REQUIRES a note, and records what it is overwriting.

    A re-stamp restarts the counted out-of-sample record, so the manifest has to say what moved
    and why. Without `superseded` a later reader cannot tell a deliberate model change from
    constants that drifted unnoticed and were absorbed by the next freeze.
    """
    if not note:
        sys.exit("REFUSING to re-stamp without a note.\n"
                 "  A freeze re-stamp restarts the counted out-of-sample record. Say what "
                 "changed and why:\n"
                 "  python3 pga_freeze.py --freeze --note \"...\"")
    snap = snapshot()
    prior = None
    try:
        prior = json.loads(MANIFEST.read_text())
    except Exception:                                               # noqa: BLE001
        prior = None
    moved = []
    if prior:
        a, b = _flat(prior), _flat(snap)
        for k in sorted(set(a) | set(b)):
            # Skip freeze METADATA in the re-stamp diff too, not just in verify(),
            # or a re-stamp reports its own `superseded` block as a moved value and
            # buries the real change under a copy of the previous record.
            if k in ("git_sha", "purpose", "decision") or k.startswith("superseded"):
                continue
            x, y = a.get(k), b.get(k)
            same = (x == y)
            if not same and isinstance(x, (int, float)) and isinstance(y, (int, float)):
                same = abs(float(x) - float(y)) <= 1e-9 * max(1.0, abs(float(x)))
            if not same:
                moved.append({"key": k, "was": x, "now": y})
    snap["decision"] = note
    snap["superseded"] = {"frozen_at_git": (prior or {}).get("git_sha"),
                          "values_moved": moved}
    if moved:
        print("RE-STAMPING OVER %d MOVED VALUE(S) — recorded in `superseded`:" % len(moved))
        for m in moved:
            print("   %-34s was=%s  now=%s" % (m["key"], m["was"], m["now"]))
        print()
    MANIFEST.write_text(json.dumps(snap, indent=2, sort_keys=True))
    try:
        COPY.write_text(json.dumps(snap, indent=2, sort_keys=True))
    except OSError:
        pass
    print("FROZEN -> %s" % MANIFEST)
    for k, v in sorted(_flat(snap).items()):
        if k not in ("purpose",):
            print("   %-34s %s" % (k, v))
    return snap


def verify(verbose=True):
    try:
        want = json.loads(MANIFEST.read_text())
    except Exception:                                               # noqa: BLE001
        print("NO FREEZE MANIFEST at %s — run with --freeze first" % MANIFEST)
        return False
    got = snapshot()
    a, b = _flat(want), _flat(got)
    drift = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        # `decision`/`superseded` are freeze METADATA, not model values. They exist only
        # in the manifest, so counting them as drift makes every verify after a
        # documented re-stamp cry wolf -- and an alarm that always fires is ignored,
        # which is how 14 constants drifted unnoticed before this.
        if k in ("git_sha", "purpose", "decision") or k.startswith("superseded"):
            continue
        same = (x == y)
        if not same and isinstance(x, (int, float)) and isinstance(y, (int, float)):
            same = abs(float(x) - float(y)) <= 1e-9 * max(1.0, abs(float(x)))
        if not same:
            drift.append((k, x, y))
    if verbose:
        if drift:
            print("FREEZE VIOLATED — %d value(s) moved since the freeze:" % len(drift))
            for k, x, y in drift:
                print("   %-34s frozen=%s  now=%s" % (k, x, y))
            print("The Rocket Classic G2 read is NO LONGER a clean out-of-sample test of the")
            print("frozen model. Either revert, or record that the read applies to a new model.")
        else:
            print("FREEZE INTACT — every constant and fitted term matches the manifest")
            print("   frozen at git %s" % str(want.get("git_sha"))[:12])
            print("   now      at git %s" % str(got.get("git_sha"))[:12])
            if want.get("git_sha") != got.get("git_sha"):
                print("   (code HAS changed; the model VALUES have not — check the diff is")
                print("    confined to tooling, not pricing)")
    return not drift


if __name__ == "__main__":
    if "--freeze" in sys.argv:
        _n = None
        if "--note" in sys.argv:
            _i = sys.argv.index("--note")
            _n = sys.argv[_i + 1] if _i + 1 < len(sys.argv) else None
        freeze(_n)
    else:
        sys.exit(0 if verify() else 1)
