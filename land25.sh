#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
for t in $(seq 1 60); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_freeze.py pga_freeze.json pga_birdies.py pga_e3.py fix_freeze_and_gate.py calib_dispersion.py; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: the freeze gave false assurance, and the birdie stream is structurally miscalibrated

THE FREEZE COULD NOT SEE NEW PARAMETERS. It snapshotted a hard-coded list, so after I added
DISPERSION — a pricing parameter — the verifier still reported "FREEZE INTACT" while prices had
already moved. A freeze that cannot see a new parameter is not a freeze. It now enumerates every
module-level constant dynamically across all six modules, so an added or removed parameter
surfaces as drift.

THE BIRDIE STREAM CANNOT BE FIXED BY A CONSTANT. Solving DISPERSION on the probability scale
shows the out-of-sample reliability slope peaks near 0.608 at D~0.55 and NEVER approaches 1.0 —
at D=0.01, where every player is collapsed to the field rate, it is still 0.551. So the residual
is not player over-dispersion: p_x_or_more assumes 18 INDEPENDENT holes while real birdie counts
are correlated within a round (a hot day, or soft conditions, lifts every hole at once). No
scalar repairs a wrong dependence structure — that needs a per-round random effect
(beta-binomial).

Since every birdie edge sits in exactly the tails this miscalibrates, the stream now has its own
PRE-REGISTERED gate: it may not arm until the measured reliability slope reaches 0.85. Today it
is 0.61. Deliberately independent of G2, which tests the ruler against the book on matchups and
says nothing about birdie tail calibration. Enforced in code and surfaced on the board rows, not
left to memory.
MSG
  echo "committed $(git rev-parse --short HEAD)"
fi
for i in $(seq 1 25); do
  [ -f .git/index.lock ] && { sleep 2; continue; }
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && break
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "PUSHED attempt $i"; break; }
  sleep 2
done
git fetch -q "$URL" main 2>/dev/null
echo "on origin: dyn-freeze=$(git show FETCH_HEAD:pga_freeze.py | grep -c '_consts(mod)') birdie-gate=$(git show FETCH_HEAD:pga_birdies.py | grep -c 'BIRDIE_RELIABILITY_MIN')"
echo
echo "=== E3 with the birdie gate live ==="
nice -n 8 timeout 1200 python3 -u pga_e3.py 2>&1 | grep -E "NOT ARMABLE|birdies: flags|E3 preview|skip " | tail -8
