#!/bin/zsh
# FanDuel WNBA prop collector. Added to cron 2026-08-13.
# ⚠️ WAS SILENTLY DEAD ON THIS MAC: fd_collect.py used urllib, which has no cert
# bundle here, so every call died with SSL CERTIFICATE_VERIFY_FAILED while the
# script printed "FanDuel 0 lines" as if the board were empty. Fixed by making
# get() prefer requests. Rows land in fd_lines(book='fd'); the WNBA board was
# 99.93% DraftKings until now.
cd /Users/ethandown/tennis-odds-collector
/usr/bin/env python3 fd_collect.py --wnba >> fd_wnba.log 2>&1
