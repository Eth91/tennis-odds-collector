#!/bin/bash
# Land the PGA blind-spot fixes on origin/main from the VM.
#
# Why this is fiddly: the wnba-loop pushes data commits constantly and recovers from a
# failed rebase by REPLAYING onto origin, which silently discards any local commit of mine
# it finds in the way (that is how the first attempt vanished). It also left a stale
# .git/rebase-merge behind, which makes every later `git rebase` refuse to start.
#
# So: clear stale rebase state, re-apply (idempotent) so we commit whatever the loop just
# reverted, then retry fetch->rebase->push until we win a gap between the loop's pushes.
# Verified at the end with ls-remote, because a lost push here reverts code silently.
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
GHREPO=github.com/fgf9p6ks2f-ux/tennis-odds-collector.git
URL="https://x-access-token:${GIT_PAT}@${GHREPO}"

rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_blind.py 2>&1 | grep -E "^\s+\+" || true
echo "state: ctx=$(grep -c 'PREFER DIRECT HOLE HISTORY' pga_context.py) ruler=$(grep -c 'IN-PLAY CONDITIONING' pga_ruler.py) wave=$(test -f pga_wave.py && echo 1 || echo 0) noise=$(grep -c 'def noise_floor' pga_ruler.py)"

for f in pga_wave.py pga_birdies.py pga_context.py pga_ruler.py fix_blind.py pga_audit.py; do
  [ -f "$f" ] && git add "$f"
done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: close the five audited blind spots

pga_wave.py (new): orchestrator tee sheets, which are posted days before ESPN stamps a
competitor (294 entries vs 0), plus a WITHIN-EVENT-ROUND fit of the AM/PM stroke gap so
wave_shift is measured rather than the 0.5-1.5 stroke guess a comment admitted to.

birdies: schedule(year:) unlocks 2024-25, and course birdie factors are now measured from
counted holes and blended over the scoring bridge instead of always inferred through it.

ruler: noise_floor() splits round variance into skill vs irreducible noise, to settle
whether RMSE 2.82 is model error or the information ceiling; simulate() takes
progress=/partial= for in-play conditioning, with the pre-tournament path left
byte-identical so its memory profile on the capped cgroup is unchanged; g2_gate now grades
18-hole round matchbets, which settle daily, instead of 72-hole markets only.
MSG
  echo "committed $(git rev-parse --short HEAD)"
else
  echo "nothing staged (already committed or already on origin)"
fi

for i in $(seq 1 25); do
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  L=$(git rev-parse HEAD); R=$(git rev-parse FETCH_HEAD)
  if [ "$L" = "$R" ]; then echo "already identical to origin"; break; fi
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply
    echo "  attempt $i: rebase conflicted, retrying"; sleep 2; continue
  fi
  if git push -q "$URL" HEAD:main 2>/dev/null; then echo "PUSHED on attempt $i"; break; fi
  sleep 2
done

L=$(git rev-parse HEAD)
R=$(git ls-remote "$URL" main 2>/dev/null | cut -f1)
echo "local  $L"
echo "remote $R"
if [ "$L" = "$R" ]; then
  echo "MATCH - the loop's reset --hard is now a no-op for these files"
else
  echo "MISMATCH - remote does NOT have the fixes; they will be reverted"
  git log --oneline -1 "$R" 2>/dev/null || true
fi
echo "--- do the fixes exist on ORIGIN? ---"
git fetch -q "$URL" main 2>/dev/null
for f in pga_wave.py pga_ruler.py pga_context.py; do
  if git cat-file -e FETCH_HEAD:$f 2>/dev/null; then
    echo "  $f on origin: $(git show FETCH_HEAD:$f | grep -cE 'IN-PLAY CONDITIONING|PREFER DIRECT HOLE HISTORY|def fit_wave') marker(s)"
  else
    echo "  $f MISSING on origin"
  fi
done
