#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_wave_forecast.py
grep -c "_wind_for_days" pga_wave.py
for f in pga_wave.py fix_wave_forecast.py; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA wave: live shift was asking the archive about a future tournament

The split came back correct and live (147 players, 78 am / 69 pm from the orchestrator sheet
while ESPN still had 0) but the shift was +0.000 "wind unavailable": _wind_hourly hits
archive-api.open-meteo.com, which serves only past dates. The historical FIT needs the
archive; a live shift needs the forecast.

_wind_for_days now picks by date and merges, so an event straddling today (round 1 played,
round 2 tomorrow) gets both. Same window and key format, so the fitted beta transfers
without recalibration.
MSG
  echo "committed $(git rev-parse --short HEAD)"
fi
for i in $(seq 1 25); do
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && { echo identical; break; }
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "PUSHED attempt $i"; break; }
  sleep 2
done
L=$(git rev-parse HEAD); R=$(git ls-remote "$URL" main 2>/dev/null | cut -f1)
[ "$L" = "$R" ] && echo "MATCH" || echo "MISMATCH"
echo "=== live wave test (post-commit, cannot be reverted now) ==="
nice -n 5 timeout 300 python3 -c "
import pga_field as PF, pga_wave as W, pga_birdies as B
tid = B.tid_for_name(PF.event().get('name')); la, lo = PF.coords()
wave, shift, note = W.wave_shift_for(tid, lat=la, lon=lo)
am=sum(1 for v in wave.values() if v=='am'); pm=sum(1 for v in wave.values() if v=='pm')
print('LIVE WAVE: %d am / %d pm' % (am,pm))
print('LIVE SHIFT: %+.3f strokes' % shift)
print('note:', note)
"
