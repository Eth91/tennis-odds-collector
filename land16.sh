#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 apply_halflife.py || exit 1
python3 -c "import pga_ruler as RU; print('  HALF_LIFE_D now %.0f' % RU.HALF_LIFE_D)"
git add pga_ruler.py apply_halflife.py pga_audit.py fix_audit_wind.py run_grid3.sh 2>/dev/null
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: HALF_LIFE_D 120 -> 270 days (tuned on 2024-25, confirmed on held-out 2026)

The only tuned constant in the calibration pass. The tune-set curve is a clean interior peak
rather than a ramp, which is what a real optimum looks like:
  45d .5721 | 60d .5779 | 90d .5809 | 120d .5833 | 180d .5847 | 270d .5862 | 365d .5849
  no-decay .5811
"No decay" scoring worse than 120 matters: recency is real, it just acts over about nine
months, and 120 sat on the wrong side of the peak.

Held out 2026, never used to choose it: accuracy .5885 -> .5967 (+.0082). Against the measured
ordering ceiling of 0.604 that is 85% -> 93% of all obtainable signal, the largest single gain
of this pass — from a constant nobody had ever fitted.

RMSE prefers ~90-120 days and gives up 0.0003 here. Taken deliberately: matchups and top-N are
priced off ordering, and the ordering gain is roughly 15x the RMSE cost.

Also: the wind refit recorded mean_wind = 17.6 km/h against the assumed WIND_REF of 15, so the
wind term had been carrying a -1.35% standing bias at typical conditions. It is now centred on
its own sample mean.
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
