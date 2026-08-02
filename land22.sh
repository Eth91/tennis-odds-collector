#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_sweep.py || exit 1
python3 -c "
import ast,io
[ast.parse(io.open(f).read()) for f in ('pga_birdies.py','pga_grade.py','pga_ruler.py')]
import pga_birdies as B
print('  tid_for_name(\"Rocket Classic\") ->', B.tid_for_name('Rocket Classic'))
print('  tid_for_name(\"Totally Fake Event\") ->', B.tid_for_name('Totally Fake Event'), '(None = refuses to guess)')
"
git add pga_birdies.py pga_grade.py pga_ruler.py fix_sweep.py gate_power.py gate_power2.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: adversarial sweep — tid resolution, and the E1 tripwire was firing on noise

S1 tid_for_name accepted a SINGLE token hit with no minimum match quality, so an event missing
from the schedule would silently resolve to any tournament sharing one word — and that tid
drives the par mix, the course factor AND the wave tee sheet. Same contamination class as the
course-name and LPGA bugs. Now requires a majority of tokens and returns None rather than
guessing; every caller already handles None with a documented fallback.

S2/S3 The E1 tripwire's code fired below 0.52*be*2 = 1.04*be while its docstring said "52% of
the breakeven pace" = 0.52*be — a 4x discrepancy. Worse, that threshold sits ABOVE breakeven,
so it was not testing "is this broken" but "is this comfortably profitable": measured false-bench
rate on an EXACTLY break-even stream was 58% at n=25, rising to 85% at n=600. It converges on
benching a fine stream with certainty. An alarm that fires on noise is worse than no alarm,
because it reads as evidence. Replaced with a one-sided test — bench only when break-even is
ruled out at 2 SE — which holds the false-bench rate near 2% at any n.

G2 POWER ANALYSIS CORRECTED ME. Against real out-of-sample matchup probabilities the gate fails
a book 4+ pts sharper 100% of the time even at n=15, and passes a book within 1 pt 100% of the
time. I had called n=15 "a smoke test"; it is adequate and the pre-registered threshold stands.
What the analysis did expose is that a PASS means "within 2 pts of the book" — equally consistent
with being 1.9 pts WORSE, which loses money before vig. G2 is a screen against a broken model,
never evidence of an edge, and it now says so in its own output.
MSG
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
