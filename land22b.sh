#!/bin/bash
# The loop commits every cycle, so a bare `git add` can lose an index.lock race — that just
# ate a commit and left "MATCH" reading as success while the changes were still uncommitted.
# Wait for the lock, and verify the commit actually contains the files.
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
python3 fix_sweep.py >/dev/null 2>&1
for t in $(seq 1 60); do
  [ -f .git/index.lock ] || break
  sleep 2
done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_birdies.py pga_grade.py pga_ruler.py fix_sweep.py gate_power.py gate_power2.py; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: adversarial sweep — tid resolution, and the E1 tripwire was firing on noise

S1 tid_for_name accepted a SINGLE token hit with no minimum match quality, so an event missing
from the schedule would silently resolve to any tournament sharing one word — and that tid drives
the par mix, the course factor AND the wave tee sheet. Same contamination class as the course-name
and LPGA bugs. Now requires a majority of tokens and returns None rather than guessing.

S2/S3 The E1 tripwire fired below 0.52*be*2 = 1.04*be while its docstring said "52% of the
breakeven pace" = 0.52*be — a 4x discrepancy. Worse, that threshold sits ABOVE breakeven, so it
tested "is this comfortably profitable" rather than "is this broken": measured false-bench rate on
an EXACTLY break-even stream was 58% at n=25 rising to 85% at n=600, converging on benching a fine
stream with certainty. An alarm that fires on noise is worse than none because it reads as
evidence. Now a one-sided test — bench only when break-even is ruled out at 2 SE — holding the
false-bench rate near 2% at any n.

G2 POWER ANALYSIS CORRECTED ME. Against real out-of-sample matchup probabilities the gate fails a
book 4+ pts sharper 100% of the time even at n=15 and passes one within 1 pt 100% of the time. I
had called n=15 a smoke test; it is adequate and the pre-registered threshold stands. What the
analysis exposed instead is that a PASS means "within 2 pts of the book" — equally consistent with
being 1.9 pts WORSE, which loses money before vig. G2 is a screen against a broken model, never
evidence of an edge, and now says so in its own output.
MSG
  echo "committed $(git rev-parse --short HEAD)"
else
  echo "nothing staged"
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
# VERIFY the content is on origin, not just that the SHAs match
git fetch -q "$URL" main 2>/dev/null
echo "on origin: tid-guard=$(git show FETCH_HEAD:pga_birdies.py | grep -c 'REQUIRE A MAJORITY') tripwire=$(git show FETCH_HEAD:pga_grade.py | grep -c 'PROPER ONE-SIDED TEST') g2-note=$(git show FETCH_HEAD:pga_ruler.py | grep -c 'SCREEN AGAINST A BROKEN MODEL')"
