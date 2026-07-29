#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_fit_params.py || exit 1
python3 -c "import pga_ruler as RU, pga_calib as C; print('imports OK; fit params:', [p for p in RU.fit.__code__.co_varnames[:6]])" || exit 1
git add pga_ruler.py pga_calib.py fix_fit_params.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -m "PGA: measure the seven constants that were never fitted

The wind refit showed a small-n fit reading 32% hot. These seven were never fitted at all,
so they have no n to be small: HALF_LIFE_D, K_SHRINK, RHO, SIG_SHRINK, K_H, K_COURSE, K_FIT.

Six are shrinkage strengths, and shrinkage has a closed form — the empirical-Bayes optimum
k = noise variance / true between-unit variance, both measurable. So those six need no
tuning and cannot leak. RHO is a nested ANOVA on a player's rounds within vs across events.
Only HALF_LIFE_D is a real predictive hyperparameter, so it alone is tuned, on 2024-25 with
2026 held out.

A negative estimated between-unit variance is reported as 'indistinguishable from zero' and
switches the term OFF rather than being silently floored — which matters most for personal
course fit, the most over-claimed edge in golf.

fit() gains overrides and an optional preloaded rows (a half-life grid is ~350 as-of fits
and the query dominated); module globals stay the defaults so all callers are unaffected."
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
