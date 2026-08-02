#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 apply_calib.py || exit 1
echo "--- values now in force ---"
python3 -c "
import pga_ruler as RU, pga_context as C, pga_birdies as B
print('  RHO        %.3f  (was 0.25)' % RU.RHO)
print('  K_SHRINK   %.1f   (was 12.0)' % RU.K_SHRINK)
print('  SIG_SHRINK %.1f  (was 20.0)' % RU.SIG_SHRINK)
print('  K_FIT      %.1f (was 8.0)' % C.K_FIT)
print('  K_COURSE   %.1f   (unchanged, deliberately)' % C.K_COURSE)
print('  K_H_PAR    %s (was flat 60)' % B.K_H_PAR)
print('  par73 mix  %s' % B.PAR_MIX_RULE[73])
"
git add pga_ruler.py pga_context.py pga_birdies.py apply_calib.py pga_calib.py \
        test_kfit.py test_rho.py test_rho2.py fix_bridge3.py 2>/dev/null
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: apply the measured constants (six of seven; half-life still tuning)

  RHO        0.25 -> 0.05   five times too high. Nested ANOVA 0.055 (44,580 dof, needs no
                            ratings), round-pair correlation +0.039 on 57,015 pairs,
                            selection-free 36-hole spread +0.109. At 0.25 the model inflated
                            72-hole variance ~14%, pushing matchups toward 50/50.
  K_SHRINK   12.0 -> 11.0   the one hand-set value that was already about right.
  SIG_SHRINK 20.0 -> 78.0   true spread of player volatility is 8% of the mean sd, so
                            "streaky players" is mostly an illusion.
  K_FIT      8.0  -> 105.0  a 13x error. Empirical Bayes says 104.8; an out-of-sample
                            early->late split over 2,979 player-course cells says 80
                            (slope +0.0605). Course fit was injecting up to 1.2 strokes of
                            noise while the true affinity spread is 0.27.
  K_H        60   -> per-par 593/106/162. Par-3 birdie ability is almost all luck.
  par 73 mix (4,9,5) -> (3,11,4), observed 2/2 on the expanded harvest.

K_COURSE is deliberately unchanged: the empirical-Bayes number measures the DIRECT
birdie-count factor, not the bridge-derived factor K_COURSE shrinks. Applying it would repeat
exactly the mistake this pass exists to fix. The direct factor's own shrinkage does move,
300 -> 100 pseudo-rounds, which IS the measured quantity.
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
