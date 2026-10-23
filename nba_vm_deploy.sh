#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Deploy the NBA engine's CODE to the VM (NBA_SPEED_PREREG.md amendment 4). Run from the Mac after a
# merge: the VM cannot pull from GitHub (its stored PAT is suspended), so code goes over rsync.
# CODE ONLY — *.py and the two cron scripts. The VM OWNS its live data (nba_lines / nba_shadow /
# nba_news .sqlite, nba_injuries.json, the caches): this never copies a .sqlite or .json, so a
# deploy cannot roll the forward record back to the Mac's stale copy.
#     ./nba_vm_deploy.sh        # rsync, then import-check the live modules on the VM
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
VM=ubuntu@155.248.217.149
KEY="$HOME/.ssh/oracle_vm"
SRC="$HOME/nba-engine/"
rsync -a --itemize-changes -e "ssh -i $KEY -o ConnectTimeout=20" \
  --include='*.py' --include='nba_cycle.sh' --include='nba_watch.sh' --exclude='*' \
  "$SRC" "$VM:nba-engine/" | grep -v '^\.' || true
ssh -i "$KEY" -o ConnectTimeout=20 "$VM" 'cd nba-engine && chmod +x nba_cycle.sh nba_watch.sh && set -a && . ~/.nba-engine.env && set +a && python3 -c "
import nba_watch, nba_flags, nba_lines, nba_injury_report, nba_news_watch, nba_clv, nba_morning_check
print(\"VM import check ok · books\", nba_lines.DEFAULT_BOOKS, \"· dk snapshot\", nba_lines.DK_SNAPSHOT)"'
