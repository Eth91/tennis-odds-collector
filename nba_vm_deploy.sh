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
# NO ROLLBACKS (2026-10-24): a deploy from a branch cut before an unmerged-but-deployed PR silently
# reverted that PR on the VM for 67 min. The VM records the commit it runs; a deploy whose HEAD does
# not contain it is refused. Uncommitted changes are refused too. FORCE=1 overrides both, knowingly.
HEAD_C=$(git -C "$SRC" rev-parse HEAD)
if [ "${FORCE:-0}" != 1 ]; then
  if [ -n "$(git -C "$SRC" status --porcelain -- '*.py' nba_cycle.sh nba_watch.sh)" ]; then
    echo "REFUSED: uncommitted code changes; commit first (or FORCE=1)"; exit 1
  fi
  LAST=$(ssh -i "$KEY" -o ConnectTimeout=20 "$VM" 'cat nba-engine/.deployed_commit 2>/dev/null || true')
  if [ -n "$LAST" ] && ! git -C "$SRC" merge-base --is-ancestor "$LAST" HEAD 2>/dev/null; then
    echo "REFUSED: the VM runs ${LAST:0:10}, which this HEAD (${HEAD_C:0:10}) does not contain."
    echo "         Merge or rebase onto it first, or FORCE=1 to roll the VM back on purpose."; exit 1
  fi
fi
rsync -a --itemize-changes -e "ssh -i $KEY -o ConnectTimeout=20" \
  --include='*.py' --include='nba_cycle.sh' --include='nba_watch.sh' --exclude='*' \
  "$SRC" "$VM:nba-engine/" | grep -v '^\.' || true
ssh -i "$KEY" -o ConnectTimeout=20 "$VM" 'cd nba-engine && chmod +x nba_cycle.sh nba_watch.sh && set -a && . ~/.nba-engine.env && set +a && python3 -c "
import nba_watch, nba_flags, nba_lines, nba_injury_report, nba_news_watch, nba_clv, nba_morning_check
print(\"VM import check ok · books\", nba_lines.DEFAULT_BOOKS, \"· dk snapshot\", nba_lines.DK_SNAPSHOT)"'
ssh -i "$KEY" -o ConnectTimeout=20 "$VM" "echo $HEAD_C > nba-engine/.deployed_commit"
echo "deployed ${HEAD_C:0:10}"
