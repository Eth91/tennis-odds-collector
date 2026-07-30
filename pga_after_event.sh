#!/usr/bin/env bash
# Run once after every tournament settles. Grades the open paper flags, then regenerates the
# cumulative evidence report for the FROZEN v1.0 model.
#
# This script deliberately does nothing else. It cannot retune, refit or adjust anything — the
# whole point of the freeze is that the only thing that changes between tournaments is the
# EVIDENCE, never the model. If a future version of this file starts fitting something, the
# validation record it produces is void.
set -uo pipefail
# note: no `timeout` — it is GNU coreutils and absent on macOS, where this runs
cd "$(dirname "$0")"

echo "=== 1/3  drift check — the frozen constant set must be untouched ==="
python3 - <<'PY'
import hashlib, json, sys
import pga_ruler as R, pga_e3 as E, pga_birdies as B, pga_context as C
def consts(m):
    return {k: getattr(m, k) for k in dir(m)
            if k.isupper() and isinstance(getattr(m, k), (int, float, str, dict, tuple))}
snap = {"pga_ruler": consts(R), "pga_e3": consts(E),
        "pga_birdies": consts(B), "pga_context": consts(C)}
now = hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()[:16]
import io as _io
src = {f: hashlib.sha256(_io.open(f, "rb").read()).hexdigest()[:16]
       for f in ("pga_ruler.py", "pga_e3.py", "pga_birdies.py", "pga_context.py")}
now_src = hashlib.sha256(json.dumps(src, sort_keys=True).encode()).hexdigest()[:16]
try:
    _fz = json.load(open("pga_v1_freeze.json"))
    want, want_src = _fz["sha256_16"], _fz["source_sha256_16"]
except Exception as e:
    print("  cannot read pga_v1_freeze.json (%s) — treating as DRIFT" % e); sys.exit(1)
# SOURCE hash matters as much as the constants: a drift check that only reads uppercase
# module attributes passed while a whole dedupe block was missing from pga_e3.py.
if now == want and now_src == want_src:
    print("  OK  v1.0 constants %s + source %s intact" % (now, now_src))
else:
    if now != want:
        print("  constants drifted: %s != %s" % (now, want))
    if now_src != want_src:
        print("  SOURCE drifted: %s != %s" % (now_src, want_src))
        for f, h in src.items():
            if _fz["source_files"].get(f) != h:
                print("    changed: %s" % f)
    print("  *** DRIFT: fingerprint %s != frozen %s ***" % (now, want))
    print("  The model has changed. Any evidence collected after this point belongs to a")
    print("  DIFFERENT model and cannot be pooled with the v1.0 record. Either revert, or")
    print("  start a new record — do not append.")
    sys.exit(1)
PY
[ $? -ne 0 ] && { echo "halting: model drift"; exit 1; }

echo
echo "=== 2/3  grade settled flags ==="
nice -n 8 python3 -u pga_grade.py 2>&1 | tail -12

echo
echo "=== 3/3  cumulative evidence report ==="
nice -n 8 python3 -u pga_validate.py 2>&1 | tail -60

echo
echo "report written to pga_evidence.md (state in pga_evidence.json)"
