#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_calib_rest.py || exit 1
python3 -c "
import pga_birdies as B, inspect
print('  par73 mix now %s' % B.PAR_MIX_RULE[73])
print('  rates() per-par:', 'K_H_PAR.get' in inspect.getsource(B.rates))
"
git add pga_birdies.py fix_calib_rest.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA: apply the two calibration changes the patcher silently skipped

apply_calib.py detected prior application by matching the FIRST LINE of each replacement, and
for these two that line already existed in the file ('out = {}' and the unchanged first line
of PAR_MIX_RULE), so both were reported as already-applied and never landed: rates() kept the
flat K_H=60 instead of the measured per-par 593/106/162, and the par-73 mix stayed at the
invented (4,9,5) rather than the observed (3,11,4)."
  echo "committed $(git rev-parse --short HEAD)"
fi
for i in $(seq 1 25); do
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && break
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "PUSHED attempt $i"; break; }
  sleep 2
done
L=$(git rev-parse HEAD); R=$(git ls-remote "$URL" main 2>/dev/null | cut -f1)
[ "$L" = "$R" ] && echo MATCH || echo MISMATCH
echo "=== GRID ==="; cat ~/halflife.log
