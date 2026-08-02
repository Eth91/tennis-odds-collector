#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
git fetch -q "$URL" main 2>/dev/null
echo "=== is the round_scores fix ON ORIGIN? (the in-play-wrecking bug) ==="
git show FETCH_HEAD:pga_field.py 2>/dev/null | grep -c "COMPLETED ROUNDS ONLY" | sed 's/^/  round_scores guard: /'
git show FETCH_HEAD:pga_field.py 2>/dev/null | grep -c "def partial_rounds" | sed 's/^/  partial_rounds():   /'
git show FETCH_HEAD:pga_holes.py >/dev/null 2>&1 && echo "  pga_holes.py:       present" || echo "  pga_holes.py:       MISSING"
echo
echo "=== local vs origin ==="
echo "  local  $(git rev-parse --short HEAD)  $(git log -1 --format=%s | cut -c1-60)"
echo "  origin $(git rev-parse --short FETCH_HEAD)  $(git log -1 --format=%s FETCH_HEAD | cut -c1-60)"
echo "  commits local-not-on-origin: $(git rev-list --count FETCH_HEAD..HEAD 2>/dev/null)"
echo
for i in $(seq 1 15); do
  [ -f .git/index.lock ] && { sleep 2; continue; }
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && { echo "  already identical"; break; }
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "  PUSHED on attempt $i"; break; }
  sleep 2
done
git fetch -q "$URL" main 2>/dev/null
echo "  FINAL: origin has round_scores guard = $(git show FETCH_HEAD:pga_field.py | grep -c 'COMPLETED ROUNDS ONLY')"
