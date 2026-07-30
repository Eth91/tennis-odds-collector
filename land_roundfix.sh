#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
echo "state before: pga_field guard=$(grep -c 'COMPLETED ROUNDS ONLY' pga_field.py) holes=$(test -f pga_holes.py && echo 1 || echo 0)"
python3 fix_round_scores.py
echo "after re-apply: guard=$(grep -c 'COMPLETED ROUNDS ONLY' pga_field.py) partial=$(grep -c 'def partial_rounds' pga_field.py)"
for t in $(seq 1 40); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_field.py pga_holes.py fix_round_scores.py test_greenpenalty.py \
         scan_interactions.py build_interaction_table.py fix_scan_centering.py; do
  [ -f "$f" ] && git add "$f"
done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: round_scores returned PARTIAL stroke totals as completed rounds (re-landed)

This commit was lost once already — the loop's rebase recovery discarded it, which is the known
failure mode on this box, so it is being re-applied and verified by CONTENT on origin rather than
by a matching SHA.

ESPN's linescores[i].value is a RUNNING stroke total, not a finished round, and the filter accepted
anything > 0. Caught live during Rocket Classic round 1:
    Wyndham Clark  71.0 -> 18 holes, real
    Ben Griffin    11.0 -> THREE holes (3+4+4)
    Max Greyserman  3.0 -> ONE hole
The "R1 leaderboard" therefore read 3, 4, 7, 11. Worse, simulate(progress=) — the in-play
conditioning — would have treated a player three holes in as having shot 11 for the round and given
him a near-certain win probability. It would have produced absurd live prices on day one.

Fix: require 18 nested per-hole entries (status.thru is None for every competitor in this event, so
hole count is the only exact signal). partial_rounds() exposes in-progress rounds separately so
simulate()'s partial= argument receives them deliberately rather than by accident. Verified live:
66 completed rounds all within 61..77, 54 in progress, true leader Malnati 61.

Also carries pga_holes.py (measured green-penalty index; U.S. Open .783 penal, American Express
.272 benign across 56 courses) and the interaction-scan centering fix. NOTE both are deliberately
UNWIRED: the index describes the course correctly but does not predict the residual (SG_PUTT x
green_penalty r=-0.005 over 33,556 rows), and no skill x condition interaction reached |r|>=0.03.
MSG
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
sleep 3
git fetch -q "$URL" main 2>/dev/null
echo "=== VERIFY BY CONTENT ON ORIGIN ==="
echo "  round_scores guard: $(git show FETCH_HEAD:pga_field.py | grep -c 'COMPLETED ROUNDS ONLY')"
echo "  partial_rounds():   $(git show FETCH_HEAD:pga_field.py | grep -c 'def partial_rounds')"
echo "  pga_holes.py:       $(git show FETCH_HEAD:pga_holes.py >/dev/null 2>&1 && echo present || echo MISSING)"
