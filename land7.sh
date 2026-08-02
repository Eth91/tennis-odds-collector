#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_course_match.py || exit 1
git add pga_context.py fix_course_match.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA: direct course birdie factor was pooling unrelated courses

It reported 12 editions / 4888 rounds for the Rocket Classic, an event that has existed
since 2019 and of which we hold three seasons. The token rule inherited from course_factor
accepts a match on half the tokens, so the word 'Classic' alone pulled in the Zurich,
John Deere and Cognizant Classics. Now every token must appear: 'Rocket Classic' still
matches its old name 'Rocket Mortgage Classic' but not the Zurich Classic. A renamed event
matches nothing and falls back to the bridge, which beats inventing course history."
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
nice -n 5 python3 -c "
import pga_context as C
for ev in ('Rocket Classic','Wyndham Championship','THE PLAYERS Championship'):
    f,e,n = C.direct_course_birdie_factor(ev)
    print('  %-26s direct=%s  editions=%d  rounds=%d' % (ev, ('%.3f'%f) if f else 'None', e, n))
    b,bn = C.course_factor(ev, verbose=True)
    print('     blended course_factor -> %.3f (bridge editions %d)' % (b, bn))
"
