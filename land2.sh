#!/bin/bash
# Commit + push whatever the PGA patch scripts have produced, then start the backfills.
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"

rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_blind.py  >/dev/null 2>&1
python3 fix_dbsafe.py >/dev/null 2>&1

for f in pga_wave.py pga_birdies.py pga_context.py pga_ruler.py fix_blind.py fix_dbsafe.py \
         pga_audit.py .gitignore; do
  [ -f "$f" ] && git add "$f"
done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: keep the new harvests out of the binary-DB blob war

pga_model.sqlite is tracked, and the loop's recovery does `git reset --hard FETCH_HEAD`
then replays *.sqlite from its own pre-reset commit. During that window an open handle
sees origin's older copy and sqlite raises "attempt to write a readonly database" — which
is exactly what killed the first tee/birdie backfill run.

So the new tee sheet gets its own gitignored pga_tees.sqlite (sole writer, so it can never
lose a race), and both harvests reconnect-and-retry through the reset window instead of
dying in it. birdie_rounds stays where it already lives and is idempotent by tid.
MSG
  echo "committed $(git rev-parse --short HEAD)"
fi

for i in $(seq 1 25); do
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && { echo "identical"; break; }
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply
    sleep 2; continue
  fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "PUSHED attempt $i"; break; }
  sleep 2
done
L=$(git rev-parse HEAD); R=$(git ls-remote "$URL" main 2>/dev/null | cut -f1)
[ "$L" = "$R" ] && echo "MATCH $L" || echo "MISMATCH local=$L remote=$R"

# --- restart both backfills, now interruption-tolerant ---
nohup nice -n 15 python3 -c "import pga_wave as W; W.harvest_tees(years=(2024,2025,2026))" \
  > tee_harvest.log 2>&1 &
echo "tee harvest pid $!"
nohup nice -n 15 python3 -c "import pga_birdies as B; B.harvest(years=(2025,2024))" \
  > birdie_backfill.log 2>&1 &
echo "birdie backfill pid $!"
