#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_ties.py || exit 1
git add pga_e3.py fix_ties.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: stop pricing a product the simulator cannot represent (bug #10)

Separating the devig pools made this visible. "Top 20 Finish (Incl. Ties)" implies 28.6
qualifiers not because the book is fat but because the product genuinely pays on more than 20
players — ties at the 20th position mean 22-26 winners. So N=20 is wrong, deflating every fair
probability by ~20/23 and inflating edge ~13%.

Worse, simulate() draws continuous normals: exact ties have probability zero and its top20 is
strictly rank<20, a ties-EXCLUSIVE quantity. There is no correct comparison between that and a
ties-inclusive price, and the error runs in the direction that manufactures edge.

Pricing these properly needs integer-score simulation with tied ranks (golf scores are
integers). Until that exists, price only the exact products, where N is unambiguous and the
simulator's rank probability is the right quantity. Skipping a market is free; mispricing it
is not.
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
echo
echo "=== E3 FINAL ==="
nice -n 8 timeout 1200 python3 -u pga_e3.py 2>&1 | grep -E "skip |E3 preview|birdies: flags|G2" | tail -10
