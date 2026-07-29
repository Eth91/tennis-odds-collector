#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_ruler.py test_inplay.py fix_inplay2.py fix_test4.py; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA in-play: eliminated players were free-rolling a whole tournament

Caught by validating the conditional sim on the 2025 Rocket Classic. Aldrich Potgieter LED
after 54 holes (197, rank 1 of 86) and the model gave him a 1.5% win probability — below
his own 4.7% after 36 holes, which cannot happen.

Cause: any player without a posted score for a round kept that round as a simulated draw,
so 70 already-missed-cut players ran a full four-round free roll and diluted every real
contender. Fix: if the FIELD has completed round j and a player has no score for it, they
are out of the event and cannot win. Inferred from the data, so a caller cannot forget it.

Potgieter now reads 1.0% -> 4.7% -> 25.1% as his rounds land, and the field still sums to
1/5/10/20 at every stage. Eliminated players show cut probability 0.000, players with a
third round show 1.000.
MSG
  echo "committed $(git rev-parse --short HEAD)"
fi
for i in $(seq 1 25); do
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && { echo identical; break; }
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "PUSHED attempt $i"; break; }
  sleep 2
done
L=$(git rev-parse HEAD); R=$(git ls-remote "$URL" main 2>/dev/null | cut -f1)
[ "$L" = "$R" ] && echo "MATCH" || echo "MISMATCH local=$L remote=$R"
echo "=== harvest progress ==="
tail -2 tee_harvest.log; tail -3 birdie_backfill.log
python3 - <<'PY'
import sqlite3
try:
    c = sqlite3.connect("pga_tees.sqlite")
    print("tee_sheet: %d rows / %d events" % c.execute(
        "SELECT COUNT(*), COUNT(DISTINCT tid) FROM tee_sheet").fetchone())
except Exception as e:
    print("tee_sheet:", e)
c2 = sqlite3.connect("pga_model.sqlite")
print("birdie_rounds: %d rows / %d events / %d players" % c2.execute(
    "SELECT COUNT(*), COUNT(DISTINCT tid), COUNT(DISTINCT player) FROM birdie_rounds").fetchone())
PY
pgrep -af "pga_wave|pga_birdies" | grep -v pgrep | wc -l
