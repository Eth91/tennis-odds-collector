#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
for t in $(seq 1 40); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_birdies.py pga_e3.py fix_birdie_coursepar.py fix_rates_coursebase.py \
         calib_betabin.py test_coursepar.py; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA birdies: the blocker was COURSE-SPECIFIC par rates, not the beta-binomial. Gate opens.

The beta-binomial was the wrong suspect. Per-round over-dispersion IS real — measured PHI=0.0233
(theta sd 15.3%) over 39,722 player-rounds, and p_x_or_more now integrates it — but on its own it
only lifts the reliability slope 0.608 -> 0.644, and even 4x the measured value reaches 0.748.

The actual blocker was HOLE-MIX sensitivity. The model applied GLOBAL per-par rates when par-class
difficulty is strongly course-specific: across 56 courses, par-5 birdie rate ranges .325-.624 vs a
global .470, and par-4 .115-.315 vs .175. A universal .470 on the highest-rate class is a ~30%
error, so P(>=k) over-responded to any change in par mix. That also explains why collapsing every
player to the field rate still left slope 0.55 — the residual was never about players.

Leak-free, early-half rates -> late-half rounds, 19,942 rounds:
    GLOBAL per-par rates     slope 0.617   pred .5912 vs real .5746
    COURSE-SPECIFIC rates    slope 1.059   pred .5751 vs real .5746

rates(course_name=) now baselines on the venue's own par rates and applies player skill
MULTIPLICATIVELY, so the baseline carries the mix. Course rates are shrunk toward global on hole
count (CPAR_K=400) so a thin course, or one that was RECONFIGURED (Detroit 2026 moved courseId
876->947, par 72->70), is not trusted outright.

BIRDIE_RELIABILITY 0.61 -> 1.06, which clears the pre-registered 0.85 bar, so the birdie stream
is armable on measured grounds rather than by request. Live: LAM 0.989, flags 3 over / 1 under.
MSG
  echo "  committed $(git rev-parse --short HEAD)"
fi
for i in $(seq 1 20); do
  [ -f .git/index.lock ] && { sleep 2; continue; }
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && break
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "  PUSHED $i"; break; }
  sleep 2
done
git fetch -q "$URL" main 2>/dev/null
echo "  on origin: coursepar=$(git show FETCH_HEAD:pga_birdies.py | grep -c 'def course_par_rates') reliab=$(git show FETCH_HEAD:pga_birdies.py | grep -c 'BIRDIE_RELIABILITY = 1.06')"
python3 pga_freeze.py --freeze >/dev/null 2>&1; python3 pga_freeze.py 2>&1 | tail -2
