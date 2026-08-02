#!/bin/bash
# Keep .git BOUNDED, not merely small-for-now. Daily, from git-maint's capped cgroup.
#
# THE PROBLEM THIS SOLVES. The re-clone took .git from 32 GB to 21 MB, but that is a one-off, not a
# steady state: the loop commits roughly once a minute, ~1440/day at ~160 KB of loose objects each,
# i.e. ~230 MB/day. `git gc` packs that down, but gc only discards UNREACHABLE objects — every
# commit the loop makes is reachable from main and is kept forever. So the repo grows without bound
# and the 32 GB outage recurs, on a 2-4 year clock instead of a 3-day one. Nobody would connect the
# two by then.
#
# THE FIX IS TO RE-SHALLOW. `git fetch --depth=1` rewrites .git/shallow to the new tip, which makes
# every older commit unreachable; the reflog expiry and `gc --prune=now` then actually drop them.
# The result is a repo that returns to ~21 MB every night regardless of how many commits were made,
# because this box does not need history: it commits on the tip and fast-forward pushes, and its
# recovery path is `fetch + reset --hard FETCH_HEAD`.
#
# THE GUARD IS THE WHOLE SAFETY ARGUMENT. Re-shallowing discards history, so it must never run while
# this box holds work that only exists here. It refuses unless:
#   - the repo is genuinely shallow already (never convert a full clone behind someone's back),
#   - HEAD == origin/main, i.e. ZERO unpushed commits — the loop pushes every ~60s, so ahead>0 means
#     a push is failing and truncating history is the last thing that should happen,
#   - no rebase/merge is in flight.
# Any of those failing is a skip with a reason, not a best-effort attempt. A silent partial run here
# is how you lose the only copy of something.
set -u
cd "$HOME/tennis-odds-collector" || exit 0
LOG="$HOME/git_reshallow.log"
say(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$LOG"; }

[ -f .git/shallow ] || { say "SKIP: not a shallow clone — refusing to truncate a full one"; exit 0; }
# Explicit `if`, NOT `A || B && C`. Bash parses that as `(A || B) && C`, which happens to behave
# correctly here by accident — the kind of line that silently inverts the day someone edits it.
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
  say "SKIP: rebase in flight"; exit 0
fi

before=$(du -sm .git | cut -f1)
git fetch -q origin main 2>/dev/null || { say "SKIP: fetch failed"; exit 0; }
ahead=$(git rev-list --count FETCH_HEAD..HEAD 2>/dev/null || echo 99)
if [ "$ahead" != "0" ]; then
  say "SKIP: $ahead unpushed commit(s) — pushing is broken, do not discard history"
  exit 0
fi

# Re-shallow to the tip, then make the orphaned history actually collectable.
git fetch -q --depth=1 origin main 2>/dev/null || { say "SKIP: depth-1 fetch failed"; exit 0; }
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
say "re-shallowed: .git ${before}MB -> ${after}MB, disk $(df -h / | tail -1 | awk '{print $4}') free"
tail -n 400 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" 2>/dev/null
exit 0
