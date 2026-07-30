#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
for t in $(seq 1 40); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_e3.py fix_e3_ties.py oa_backtest.py; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: price the ties-inclusive top-N products instead of skipping them

simulate() gained tie-aware probabilities but E3 still skipped these markets with "simulator has
no ties" — capability added, never connected. Now each ties-inclusive product prices on its *_ties
key AND devigs against the model's OWN expected qualifier count instead of the nominal N: live it
reads 22.4 for top-20, 11.6 for top-10, 5.9 for top-5. Devigging a product that pays 22-26 players
against N=20 is precisely what inflated edge before, and the count now moves with the field rather
than being hard-coded.

Also re-ran the real-price outright backtest with SPREAD=1.30 + integer scores: log-loss gap vs the
devigged close fell from +0.26 pts (z=1.33) to +0.06 pts (z=0.40) — the model is now statistically
indistinguishable from the close — and the favourite quintile moved from 0.0240 to 0.0292 against a
realized 0.0366. But the SELECTION RULE is still broken: 415 of 955 runners flagged at mean odds
1155, one winner, -81.7% ROI. At long odds "EV >= +15%" is near-vacuous (a 1000-1 shot needs only
p >= 0.00115, below Monte Carlo noise), so outrights stay GATED on the threshold, not on calibration.
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
echo "  on origin: e3-ties=$(git show FETCH_HEAD:pga_e3.py | grep -c 'TIES-INCLUSIVE PRODUCTS ARE NOW PRICEABLE')"
python3 pga_freeze.py --freeze >/dev/null 2>&1; python3 pga_freeze.py 2>&1 | tail -2
