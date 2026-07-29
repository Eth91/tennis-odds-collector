#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_bridge_match.py || exit 1
git add pga_context.py fix_bridge_match.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA: course_factor's bridge was averaging over most of the tour

Wyndham Championship and THE PLAYERS Championship both reported 57 'prior editions' with an
identical scoring diff of -0.16. They share only the word 'Championship', which the
half-token match accepted, so for any event with a common word in its name the bridge
component carried no course signal at all. Every token must now appear; an unmatchable name
yields a neutral 1.00 instead of a confident average of the wrong courses."
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
python3 -c "
import json, io
c = json.load(io.open('pga_context_cache.json')); c.pop('bridge', None)
json.dump(c, io.open('pga_context_cache.json','w'))
print('bridge cache cleared for a clean refit')
"
nice -n 5 python3 -c "
import pga_context as C
for ev in ('Rocket Classic','Wyndham Championship','THE PLAYERS Championship','Travelers Championship'):
    f,e,n = C.direct_course_birdie_factor(ev)
    b,bn = C.course_factor(ev)
    print('  %-27s direct=%-6s (%d ed) | bridge editions=%-3d | FINAL %.3f' % (ev, ('%.3f'%f) if f else 'None', e, bn, b))
"
