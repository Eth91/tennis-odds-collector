#!/bin/bash
# Bound a bot repo's .git. Generalised from the main VM's git_reshallow.sh.
#
#   git_reshallow_any.sh <repo-path> [branch] [--allow-convert]
#
# `git gc` only discards UNREACHABLE objects, so every commit a loop makes is reachable from the
# branch and is kept forever. That is not a slow leak, it is the mechanism behind the 32 GB outage:
# a repo that is small today grows without bound and nobody connects the eventual disk-full to the
# commit rate that caused it. `git fetch --depth=1` rewrites .git/shallow to the tip, orphaning the
# old history so the gc can actually drop it — the repo returns to its clone size every night no
# matter how many commits were made.
#
# Safe here because none of these repos reads its own history: each commits on the tip and
# fast-forward pushes, and every recovery path is `fetch + reset --hard FETCH_HEAD`.
#
# GUARDS, which are the entire safety argument. It refuses unless:
#   - HEAD == origin/<branch>, i.e. ZERO unpushed commits. These boxes push every 1-3 minutes, so
#     ahead>0 means pushing is broken and discarding history is the worst possible response.
#   - no rebase or merge is in flight.
#   - the repo is ALREADY shallow — unless --allow-convert is passed explicitly. Silently
#     converting someone's full clone is not a maintenance task, it is a surprise.
set -u
REPO="${1:?usage: git_reshallow_any.sh <repo-path> [branch] [--allow-convert]}"
BRANCH="${2:-main}"
ALLOW_CONVERT="${3:-}"
LOG="$HOME/git_reshallow.log"
say(){ printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$(basename "$REPO")" "$1" >> "$LOG"; }

cd "$REPO" 2>/dev/null || { say "SKIP: no such repo"; exit 0; }

if [ ! -f .git/shallow ] && [ "$ALLOW_CONVERT" != "--allow-convert" ]; then
  say "SKIP: full clone and --allow-convert not given"; exit 0
fi
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
  say "SKIP: rebase in flight"; exit 0
fi

before=$(du -sm .git | cut -f1)
git fetch -q origin "$BRANCH" 2>/dev/null || { say "SKIP: fetch failed"; exit 0; }
ahead=$(git rev-list --count FETCH_HEAD..HEAD 2>/dev/null || echo 99)
if [ "$ahead" != "0" ]; then
  say "SKIP: $ahead unpushed commit(s) — pushing is broken, do not discard history"; exit 0
fi

git fetch -q --depth=1 origin "$BRANCH" 2>/dev/null || { say "SKIP: depth-1 fetch failed"; exit 0; }
git reflog expire --expire=now --expire-unreachable=now --all 2>/dev/null
git prune --expire=now 2>/dev/null
git gc --prune=now --quiet 2>/dev/null
# DROP THE STALE COMMIT-GRAPH. It is a performance cache that indexes commits by oid, and after a
# re-shallow it still names the hundreds of commits the prune just removed — `git fsck` then reports
# "failed to parse commit ... for commit-graph" once per orphan (517 pairs = 1034 errors on the
# first tt-elite run). The repo is fine underneath, but a permanently-broken fsck is exactly the
# kind of noise that trains you to ignore fsck, so regenerate it instead of leaving wreckage.
rm -f .git/objects/info/commit-graph .git/objects/info/commit-graphs/* 2>/dev/null
git commit-graph write --reachable --no-progress 2>/dev/null || true

after=$(du -sm .git | cut -f1)
head=$(git rev-parse --short HEAD 2>/dev/null)
bad=$(git fsck --connectivity-only --no-progress 2>&1 | grep -vc dangling)
say "re-shallowed: .git ${before}MB -> ${after}MB, HEAD $head, fsck $bad, disk $(df -h / | tail -1 | awk '{print $4}') free"
tail -n 400 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" 2>/dev/null
exit 0
