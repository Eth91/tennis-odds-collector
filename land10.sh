#!/bin/bash
# NOTE: run as `bash land10.sh` so the kill pattern lives in this FILE, not in an ssh command
# line that pkill would match against itself (that self-kill silently ate the last attempt).
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"

pgrep -af '^python3' | grep -F 'tune_half_life' | awk '{print $1}' | xargs -r kill 2>/dev/null
sleep 1
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_wf_shadow.py || exit 1
echo "erows present: $(grep -c erows pga_ruler.py)"
git add pga_ruler.py fix_wf_shadow.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA: walk_forward inner query shadowed the preloaded rows parameter

The first iteration passed the full 5-column history correctly, then the loop body rebound
rows to a 3-column per-event list, so every later iteration handed fit() the wrong shape and
it died comparing an int round number to a date string."
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
# quick smoke test that a parameterised fit actually works before the long grid
python3 -c "
import pga_ruler as RU
rows = RU.all_rows()
a1, r1, n1 = RU.walk_forward(seasons=(2025,), season_max=2025, verbose=False, rows=rows, half_life=120.0)
a2, r2, n2 = RU.walk_forward(seasons=(2025,), season_max=2025, verbose=False, rows=rows, half_life=45.0)
print('smoke: hl=120 acc %.4f | hl=45 acc %.4f  (differ => override works)' % (a1, a2))
"
