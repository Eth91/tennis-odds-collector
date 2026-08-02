#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_bridge.py || exit 1
python3 -c "
import json, io
c = json.load(io.open('pga_context_cache.json')); c.pop('bridge', None)
json.dump(c, io.open('pga_context_cache.json','w')); print('bridge cache cleared')
"
python3 -c "
import pga_context as C
b = C._birdie_bridge()
print('BRIDGE: n=%d editions matched, r=%+.3f, unmatched=%s' % (b['n'], b['r'] or 0, b.get('unmatched')))
print('   was: n=53, r=-0.777 (grouped by name, arbitrary year, prefix match)')
for ev in ('Rocket Classic','THE PLAYERS Championship','Travelers Championship'):
    f, n = C.course_factor(ev)
    print('   %-26s factor %.3f (%d prior editions)' % (ev, f, n))
"
git add pga_context.py fix_bridge.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA: birdie bridge lost data and mispaired years

The audit showed the bridge at n=53 with 114 events harvested. Three causes: it grouped by
event NAME so all editions of an event collapsed to one point; it then took the first fuzzy
name match, so a 2024 harvest could be paired with a 2019 scoring diff; and the name test was
a 14-character prefix substring, missing anything that differs early ('Sony Open' vs 'Sony
Open in Hawaii').

Now one point per EDITION keyed by tid, with the year read off the tid and matched exactly,
and names matched on token containment in either direction."
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
