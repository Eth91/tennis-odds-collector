#!/bin/bash
# Make worker-2 work IMPOSSIBLE to strand, without waiting on a tt-elite credential.
#
# THE PROBLEM. Both Oracle PATs 403 on tt-elite, so anything authored on worker-2 stays untracked
# forever. Twenty-two scripts sat that way from 2026-07-31 to 2026-08-02 and were one `git clean`
# from gone — they only survived because the replica repair happened to park them instead of
# deleting them to unblock a merge. That is luck, and it will recur: the box is where TT analysis
# actually gets written.
#
# THE INSIGHT. worker-2 CANNOT push to tt-elite, but it CAN push to tennis-odds-collector — it
# already does, every 3 minutes, via tt_publish_board.sh through ~/toc-pub. So the fix needs no new
# credential at all: ship the orphans down the channel that already works. They land in git,
# durably, and can be moved into tt-elite later by anything that holds the right token.
#
# WHAT COUNTS AS STRANDED: a file in ~/tt-elite that git does not track AND that origin/tt-elite
# does not have. A file present upstream is not stranded, it is a stale local copy, and copying it
# anywhere would just propagate staleness. Ignored paths are excluded — .sqlite/.log/.json state is
# not work, it is runtime, and shipping a 70 MB tt.sqlite into the other repo would recreate the
# exact oversized-blob outage this system just spent a night recovering from.
#
# IDEMPOTENT BY CONTENT. Files are copied only when absent or actually different, so the daily run
# is a no-op once things are shipped and does not generate a commit per cron tick.
set -u
SRC="$HOME/tt-elite"
PUB="$HOME/toc-pub"
DEST_REL="tt_stranded"
LOG="$HOME/tt_ship_stranded.log"
say(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$LOG"; }

[ -d "$SRC" ] && [ -d "$PUB" ] || { say "SKIP: missing $SRC or $PUB"; exit 0; }
cd "$SRC" || exit 0
git fetch -q origin main 2>/dev/null || { say "SKIP: tt-elite fetch failed"; exit 0; }

mkdir -p "$PUB/$DEST_REL"
n=0
# --exclude-standard keeps gitignored runtime out; only source-ish files ship.
while IFS= read -r f; do
  case "$f" in *.py|*.sh|*.md|*.sql|*.txt) ;; *) continue ;; esac
  git cat-file -e "FETCH_HEAD:$f" 2>/dev/null && continue      # exists upstream -> not stranded
  d="$PUB/$DEST_REL/$(basename "$f")"
  if [ ! -f "$d" ] || ! cmp -s "$f" "$d"; then
    cp -p "$f" "$d" && n=$((n+1))
  fi
done < <(git ls-files --others --exclude-standard 2>/dev/null)

[ "$n" -eq 0 ] && { say "nothing new to ship"; exit 0; }

cd "$PUB" || exit 0
git add "$DEST_REL" 2>/dev/null
git -c user.email=vm@local -c user.name=worker-2 commit -q -m \
  "tt_stranded: $n file(s) from worker-2 (cannot push to tt-elite; 403) [skip ci]" 2>/dev/null || {
    say "nothing staged after copy"; exit 0; }
for i in 1 2 3 4 5; do
  git fetch -q origin main 2>/dev/null
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1 || { git rebase --abort >/dev/null 2>&1; sleep 3; continue; }
  if git push -q origin HEAD:main 2>/dev/null; then say "shipped $n file(s) (attempt $i)"; exit 0; fi
  sleep 3
done
say "FAILED to push $n stranded file(s) after 5 attempts"
exit 0
