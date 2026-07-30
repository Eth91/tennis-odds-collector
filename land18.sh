#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_wind_stat.py || exit 1
python3 -c "import ast,io; [ast.parse(io.open(f).read()) for f in ('pga_context.py','pga_e3.py','pga_audit.py')]; print('  all parse')"
git add pga_context.py pga_e3.py pga_audit.py fix_wind_stat.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: the wind term was fit on one statistic and fed another

fit_wind regresses birdie rate on `daily=wind_speed_10m_max`, so its slope and its sample mean
(17.62 km/h) both live on the DAILY MAXIMUM scale. pga_e3 fed wind_factor the mean of every
hourly forecast value, nights included. For the current event those are 16.98 and 9.42 km/h
for the SAME forecast.

So the wind factor read 1.0422 where it should read 1.0033 — every birdie rate inflated by
3.88% in all weather, calm or windy. That is essentially the entire +4.0 point level bias the
devigged audit exposed, and the model was leaning on the market anchor to undo it.

The mismatch was invisible until the term was centred on its own fitted mean: WIND_REF=15 sat
between the two scales and split the error in half.

pga_context.live_wind_stat now owns the definition of "the wind number" so the fit and the live
call cannot drift apart, and the audit asserts the two scales agree.
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
echo "=== E3 after the wind-scale fix ==="
nice -n 8 timeout 1200 python3 -u pga_e3.py 2>&1 | grep -E "birdies|E3 preview" | tail -8
