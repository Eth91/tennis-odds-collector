#!/bin/bash
cd ~/tennis-odds-collector || exit 1
setsid nohup nice -n 15 python3 -u -c "import pga_calib as C; C.tune_half_life()" \
  > halflife.log 2>&1 < /dev/null &
disown
echo "grid started pid $!"
