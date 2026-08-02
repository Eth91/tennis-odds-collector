#!/bin/bash
cd ~/tennis-odds-collector || exit 1
pgrep -af '^python3' | grep -F 'test_reliability' | awk '{print $1}' | xargs -r kill 2>/dev/null
sleep 1
nice -n 8 timeout 900 python3 -u test_reliability.py 2>&1 | tail -26
