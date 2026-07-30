#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
echo "=== FREEZING ==="
nice -n 8 timeout 900 python3 -u pga_freeze.py --freeze
echo
echo "=== VERIFY (should be intact immediately) ==="
nice -n 8 timeout 900 python3 -u pga_freeze.py && echo "verify exit 0" || echo "verify exit NONZERO"
for t in $(seq 1 60); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_freeze.py pga_freeze.json; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA: freeze the model before the Rocket Classic tees off

Today's constants were measured on data INCLUDING completed 2026 events, so already-settled
events cannot give a clean read. The Rocket Classic is unplayed — in no fit, no calibration — so
its G2 result is a genuine out-of-sample test of exactly this model, but only if the model does
not move underneath it.

Manifest of every constant and every fitted term plus the git SHA, in the cards_v27 mold, with a
verifier that fails loudly on drift. Authoritative copy lives OUTSIDE the repo: the loop resets
tracked files, and a manifest that can be reverted is not a manifest."
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
echo "freeze on origin: $(git show FETCH_HEAD:pga_freeze.py >/dev/null 2>&1 && echo yes || echo NO)"
