#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Deploy the NBA engine's CODE to the VM (NBA_SPEED_PREREG.md amendment 4). Run from the Mac after a
# merge: the VM cannot pull from GitHub (its stored PAT is suspended), so code goes over rsync.
# CODE ONLY — *.py and the two cron scripts. The VM OWNS its live data (nba_lines / nba_shadow /
# nba_news .sqlite, nba_injuries.json, the caches): this never copies a .sqlite or .json, so a
# deploy cannot roll the forward record back to the Mac's stale copy.
#     ./nba_vm_deploy.sh        # rsync, then import-check the live modules on the VM
#     NBA_SRC=~/nba-engine-x ./nba_vm_deploy.sh   # deploy a worktree's HEAD (same guards) without
#                                                 # switching the branch of the shared ~/nba-engine checkout
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
VM=ubuntu@155.248.217.149
KEY="$HOME/.ssh/oracle_vm"
SRC="${NBA_SRC:-$HOME/nba-engine}"; SRC="${SRC%/}/"
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
    # A squash merge makes a new commit, so ancestry fails although the code is all there. The test
    # that matters: do the VM's code changes since the common base already sit in this tree? (They
    # reverse-apply cleanly onto it.) If not, deploying would roll them back.
    CODE=('*.py' nba_cycle.sh nba_watch.sh)
    MB=$(git -C "$SRC" merge-base "$LAST" HEAD 2>/dev/null || true)
    PATCH=$( [ -n "$MB" ] && git -C "$SRC" diff "$MB" "$LAST" -- "${CODE[@]}" 2>/dev/null || echo MISSING)
    # ...or they sit in origin/main (a squash merge) and this HEAD is built on origin/main: later commits
    # may have edited the same lines, so the reverse-apply is checked against main's tree, in a temp index.
    in_main() {
      git -C "$SRC" fetch -q origin 2>/dev/null || true
      git -C "$SRC" merge-base --is-ancestor origin/main HEAD 2>/dev/null || return 1
      local idx; idx=$(mktemp); rm -f "$idx"
      GIT_INDEX_FILE="$idx" git -C "$SRC" read-tree origin/main || return 1
      printf '%s\n' "$PATCH" | GIT_INDEX_FILE="$idx" git -C "$SRC" apply --cached --check -R - 2>/dev/null
      local rc=$?; rm -f "$idx"; return $rc
    }
    if [ "$PATCH" = MISSING ] || { [ -n "$PATCH" ] && ! printf '%s\n' "$PATCH" | git -C "$SRC" apply --check -R - 2>/dev/null && ! in_main; }; then
      echo "REFUSED: the VM runs ${LAST:0:10}, whose code is not in this HEAD (${HEAD_C:0:10})."
      echo "         Merge or rebase onto it first, or FORCE=1 to roll the VM back on purpose."; exit 1
    fi
  fi
fi
rsync -a --itemize-changes -e "ssh -i $KEY -o ConnectTimeout=20" \
  --include='*.py' --include='nba_cycle.sh' --include='nba_watch.sh' --exclude='*' \
  "$SRC" "$VM:nba-engine/" | grep -v '^\.' || true
ssh -i "$KEY" -o ConnectTimeout=20 "$VM" 'cd nba-engine && chmod +x nba_cycle.sh nba_watch.sh && set -a && . ~/.nba-engine.env && set +a && python3 -c "
import nba_watch, nba_flags, nba_lines, nba_injury_report, nba_news_watch, nba_clv, nba_morning_check, nba_backup
print(\"VM import check ok · books\", nba_lines.DEFAULT_BOOKS, \"· dk snapshot\", nba_lines.DK_SNAPSHOT)"'
ssh -i "$KEY" -o ConnectTimeout=20 "$VM" "echo $HEAD_C > nba-engine/.deployed_commit"
echo "deployed ${HEAD_C:0:10}"
