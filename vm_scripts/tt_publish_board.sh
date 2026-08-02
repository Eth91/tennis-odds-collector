#!/bin/bash
# Publish the TT tracker board from worker-2's LIVE database.
#
# THE BUG THIS FIXES: TT collection moved to worker-2 on 2026-07-29, but the tracker's PUBLISHER
# was left pointed at the Mac's ~/Desktop/Projects/tt-elite/tt.sqlite, which froze at Jul 28
# 01:04 when the loop moved off. So the dashboard kept rendering a 2.5-day-old snapshot:
# published tracker 22-6 with recent=[2026-07-28] only, while worker-2's live DB graded a bet at
# 04:09 today and reads 24-6 with recent=[07-30, 07-29, 07-28]. Grading was never broken —
# worker-2 settles within ~20 min of a match ending — the numbers just never reached the board.
#
# WHY WORKER-2 CAN DO THIS despite being a read-only replica for tt-elite: the dashboard reads
# tt_board.json out of the tennis-odds-collector repo, which is a DIFFERENT repo, and worker-2's
# PAT has write access there (verified: a dry-run push got a ref-level "fetch first" rejection,
# not an auth failure). tt-elite stays read-only; nothing about that invariant changes.
#
# Publishes only ONE file, and always onto origin's current tip, so it cannot clobber the main
# VM's constant pushes to the same repo.
set -u
cd /home/ubuntu/tt-elite || exit 1
for f in /home/ubuntu/*.env; do [ -f "$f" ] && . "$f" 2>/dev/null; done
: "${GIT_PAT:?no GIT_PAT}"
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
PUB=/home/ubuntu/toc-pub

# 1. regenerate from the live DB
timeout 240 python3 tt_board.py >/dev/null 2>&1 || { echo "tt_board.py failed"; exit 1; }
[ -s tt_board.json ] || { echo "no tt_board.json produced"; exit 1; }

# 2. a thin clone that exists only to carry this one file
if [ ! -d "$PUB/.git" ]; then
  rm -rf "$PUB"
  git clone -q --depth 1 "$URL" "$PUB" || { echo "clone failed"; exit 1; }
fi

cp -f tt_board.json "$PUB/tt_board.json"
# heal a broken clone rather than failing every 3 minutes forever
if ! git -C "$PUB" rev-parse --git-dir >/dev/null 2>&1; then
  rm -rf "$PUB"; git clone -q --depth 1 "$URL" "$PUB" || exit 1
  cp -f /home/ubuntu/tt-elite/tt_board.json "$PUB/tt_board.json"
fi
cd "$PUB" || exit 1
git config user.email "worker2@local"
git config user.name "tt-worker2"

# 3. land it on origin's CURRENT tip. The main VM pushes this repo constantly, so always rebase
#    onto the freshest origin and retry rather than assuming our base is current.
for i in 1 2 3 4 5 6 7 8; do
  git fetch -q "$URL" main 2>/dev/null || { sleep 3; continue; }
  # keep our file, take origin for everything else
  cp -f /home/ubuntu/tt-elite/tt_board.json /tmp/_ttb.json
  git reset -q --hard FETCH_HEAD
  cp -f /tmp/_ttb.json tt_board.json
  if git diff --quiet -- tt_board.json; then
    echo "$(date -u +%FT%TZ) board unchanged, nothing to publish"
    exit 0
  fi
  git add tt_board.json
  git commit -q -m "tt board: live tracker from worker-2 [skip ci]" || exit 0
  if git push -q "$URL" HEAD:main 2>/dev/null; then
    T=$(python3 -c "
import json,io
d=json.load(io.open('tt_board.json')); t=d.get('tracker') or {}
print('%s-%s %+.2fu  recent=%s' % (t.get('w'), t.get('l'), t.get('u') or 0,
      [r.get('date') for r in (t.get('recent') or [])][:3]))")
    echo "$(date -u +%FT%TZ) PUBLISHED $T (attempt $i)"
    exit 0
  fi
  sleep 3
done
echo "$(date -u +%FT%TZ) push failed after retries"
exit 1

# self-trim: this log gains a line every 3 minutes and nothing else rotates it
if [ -f /home/ubuntu/tt_publish.log ] && \
   [ "$(wc -l < /home/ubuntu/tt_publish.log)" -gt 5000 ]; then
  tail -1000 /home/ubuntu/tt_publish.log > /home/ubuntu/tt_publish.log.tmp && \
    mv /home/ubuntu/tt_publish.log.tmp /home/ubuntu/tt_publish.log
fi
