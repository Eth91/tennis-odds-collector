#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_cache_mc.py || exit 1
python3 -c "
import pga_context as C, pga_ruler as RU, inspect
print('  cache path:', C.CACHE)
c = C._cache()
print('  seeded keys:', sorted(c.keys()))
print('  simulate reps param:', 'reps' in RU.simulate.__code__.co_varnames)
"
git add pga_context.py pga_ruler.py pga_e3.py fix_cache_mc.py test_sigma.py test_sigma_byn.py test_windref_mc.py 2>/dev/null
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: protect the fitted terms, centre the wind term, cut Monte Carlo noise

FITTED TERMS WERE IN A TRACKED FILE THE LOOP REVERTS. pga_context_cache.json holds the wind
coefficient, the wave beta and the bridge — everything measured today — and the loop does
`git add -A -f` then resets/replays. The geocode cache was already silently wiped (0 entries
where there had been 51). The fits survived this time, but a revert to an older copy would
reinstate OLD coefficients with no error raised anywhere: a silent model regression, the
failure mode hardest to notice. The authoritative cache now lives at
~/.pga_context_cache.json, seeded once from the in-repo copy.

WIND_REF = 15 was assumed. fit_wind's slope is estimated on within-event DEVIATIONS, so the
factor is only mean-zero if centred on the same sample mean; otherwise the term carries a
standing bias at average conditions that the course factor or the market anchor absorbs
invisibly. The fit now records its own mean wind and wind_factor centres on it.

n_sims = 8000 leaves real noise: across five seeds, worst case 0.70 points on top-20 and 1.00
on make-cut, i.e. 14-20% of the 5-point edge threshold — a flagged 5.0% edge could be 4.3% or
5.7% from sampling alone. simulate(reps=) averages independent runs to halve that at CONSTANT
peak memory; raising n_sims instead would quadruple a (n_sims, k, 4) array, which a 956MB box
cannot afford. E3 now runs reps=4.
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
echo "=== GRID ==="; cat ~/halflife2.log
