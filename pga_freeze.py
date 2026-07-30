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

    wind = C.fit_wind(verbose=False) or {}
    wave = W.fit_wave(verbose=False) or {}
    bridge = C._birdie_bridge() or {}
    return {
        "git_sha": _sha(),
        "purpose": "frozen for the 2026 Rocket Classic G2 read (event unplayed at freeze time)",
        "ruler": {"RHO": RU.RHO, "K_SHRINK": RU.K_SHRINK, "SIG_SHRINK": RU.SIG_SHRINK,
                  "MIN_ROUNDS": RU.MIN_ROUNDS, "HALF_LIFE_D": RU.HALF_LIFE_D},
        "context": {"K_COURSE": C.K_COURSE, "K_FIT": C.K_FIT, "WIND_REF": C.WIND_REF},
        "birdies": {"K_H": B.K_H, "K_H_PAR": B.K_H_PAR,
                    "PAR_MIX_RULE": {str(k): v for k, v in B.PAR_MIX_RULE.items()}},
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


def freeze():
    snap = snapshot()
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
        if k in ("git_sha", "purpose"):
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
        freeze()
    else:
        sys.exit(0 if verify() else 1)
