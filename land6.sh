#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_wave_callsite.py || exit 1
git add pga_wave.py fix_wave_callsite.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA wave: actually call the forecast path in wave_shift_for

_wind_for_days was added but never called: the guard tested for a string that the new
function's own def line contains, so the edit was skipped as already-applied. fit_wave
stays on the archive (history); only the live shift moves to the forecast."
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
[ "$L" = "$R" ] && echo "MATCH" || echo "MISMATCH"
echo "=== live wave (committed, revert-proof) ==="
nice -n 5 timeout 300 python3 -c "
import pga_field as PF, pga_wave as W, pga_birdies as B
tid = B.tid_for_name(PF.event().get('name')); la, lo = PF.coords()
wave, shift, note = W.wave_shift_for(tid, lat=la, lon=lo)
print('LIVE WAVE: %d am / %d pm' % (sum(1 for v in wave.values() if v=='am'), sum(1 for v in wave.values() if v=='pm')))
print('LIVE SHIFT: %+.3f strokes' % shift); print('note:', note)
"
