#!/bin/bash
# Refit wind so the sample's own mean is recorded (the geocode cache was wiped by the loop, so
# this re-resolves courses through the ESPN venue chain). Network-bound, so it coexists fine
# with the CPU-bound half-life grid. Log outside the repo.
cd ~/tennis-odds-collector || exit 1
setsid nohup nice -n 19 python3 -u -c "
import pga_context as C
w = C.fit_wind(verbose=True, refit=True)
print('RESULT w=%.5f r=%s n=%s events=%s mean_wind=%s' % (
    w['w'], w.get('r'), w.get('n'), w.get('events'), w.get('mean_wind')))
" > ~/windrefit.log 2>&1 < /dev/null &
disown
echo "wind refit started -> ~/windrefit.log"
