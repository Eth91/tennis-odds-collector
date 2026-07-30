#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_bridge2.py || exit 1
python3 -c "
import json, io
c = json.load(io.open('pga_context_cache.json')); c.pop('bridge', None)
json.dump(c, io.open('pga_context_cache.json','w'))
"
python3 -c "
import pga_context as C
b = C._birdie_bridge()
print('BRIDGE (course level): n=%d courses, r=%+.3f, slope %+.4f' % (b['n'], b['r'] or 0, b['b']))
print('   per-edition diagnostic: slope %+.4f, r=%+.3f over %d editions (attenuated by x-noise)'
      % (b['edition_slope'], b['edition_r'] or 0, b['n_editions']))
print('   unmatched editions: %s' % b.get('unmatched'))
for ev in ('Rocket Classic','THE PLAYERS Championship','Travelers Championship'):
    f, n = C.course_factor(ev); print('   %-26s factor %.3f (%d editions)' % (ev, f, n))
"
git add pga_context.py fix_bridge2.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA: fit the birdie bridge at the level it is used

Per-edition fitting gave r=-0.540 where name-collapsed fitting gave -0.777, and that drop is
errors-in-variables rather than new honesty: one edition's scoring diff is a noisy measure of
course difficulty, noise in x attenuates the slope toward zero, and course_factor() then feeds
that slope a course-AVERAGED diff which is far less noisy — so a per-edition slope
systematically under-predicts.

Editions are still paired to their OWN year (that was a real bug: a 2024 harvest could be
matched to a 2019 scoring diff), then averaged within course before fitting. The per-edition
slope is retained as a reported diagnostic so the attenuation stays visible."
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
