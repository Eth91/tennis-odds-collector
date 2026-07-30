#!/usr/bin/env bash
# Run after each WNBA slate settles. Drift check -> grade -> regenerate the evidence report.
#
# Like the PGA runner, this deliberately does nothing else. It cannot retune, refit or adjust
# anything. The whole point of the freeze is that the only thing changing between slates is the
# EVIDENCE. If a future version of this file starts fitting something, the record it produces
# is void.
set -uo pipefail
cd "$(dirname "$0")"

echo "=== 1/3  drift check — the frozen model must be untouched ==="
python3 - <<'PY'
import hashlib, io, json, sys
FILES = ["wnba_alert.py", "wnba_slip.py", "wnba_tonight.py", "wnba_wowy.py"]
try:
    fz = json.load(open("wnba_v1_freeze.json"))
except Exception as e:                                          # noqa: BLE001
    print("  cannot read wnba_v1_freeze.json (%s) — treating as DRIFT" % e)
    sys.exit(1)
src = {f: hashlib.sha256(io.open(f, "rb").read()).hexdigest()[:16] for f in FILES}
now_src = hashlib.sha256(json.dumps(src, sort_keys=True).encode()).hexdigest()[:16]
mods = {}
for m in ("wnba_slip",):
    try:
        mod = __import__(m)
        mods[m] = {k: getattr(mod, k) for k in dir(mod)
                   if k.isupper() and isinstance(getattr(mod, k), (int, float, str))}
    except Exception:                                           # noqa: BLE001
        pass
now_c = hashlib.sha256(json.dumps(mods, sort_keys=True, default=str).encode()).hexdigest()[:16]
ok = True
if now_c != fz["sha256_16"]:
    print("  constants drifted: %s != %s" % (now_c, fz["sha256_16"])); ok = False
if now_src != fz["source_sha256_16"]:
    print("  SOURCE drifted: %s != %s" % (now_src, fz["source_sha256_16"]))
    for f, h in src.items():
        if fz["source_files"].get(f) != h:
            print("    changed: %s" % f)
    ok = False
if ok:
    print("  OK  v1.0 constants %s + source %s intact" % (now_c, now_src))
else:
    print("  *** MODEL DRIFT ***")
    print("  Evidence collected after this point belongs to a DIFFERENT model and cannot be")
    print("  pooled with the v1.0 record. Either revert, or start a new record — do not append.")
    sys.exit(1)
PY
[ $? -ne 0 ] && { echo "halting: model drift"; exit 1; }

echo
echo "=== 2/3  grade settled bets ==="
nice -n 8 python3 -u wnba_ledger.py --grade 2>&1 | tail -8

echo
echo "=== 3/3  cumulative evidence report ==="
nice -n 8 python3 -u wnba_validate.py 2>&1 | tail -50

echo
echo "report written to WNBA_EVIDENCE.md (state in wnba_evidence.json)"
