#!/usr/bin/env bash
cd "$HOME/tennis-odds-collector" || exit 1
export FD_DB="$(pwd)/wnba_lines.sqlite"
GHREPO="github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
git config user.name "odds-bot" 2>/dev/null; git config user.email "odds-bot@users.noreply.github.com" 2>/dev/null
URL="https://x-access-token:${GIT_PAT}@${GHREPO}"

# SIZE GUARD (2026-07-28): unstage ANY blob >90MB before commit. GitHub hard-rejects >100MB,
# and a rejected push is not a no-op here -- the rebase-recovery restores code from origin,
# so a blocked push silently reverts deploys. Name-based `git rm --cached` lists only catch
# what someone remembered; this catches whatever actually grew.
unstage_big(){
  git diff --cached --name-only 2>/dev/null | while read -r f; do
    [ -f "$f" ] || continue
    sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if [ "$sz" -gt 94371840 ]; then
      git rm --cached -q "$f" 2>/dev/null && echo "size-guard: unstaged $f ($((sz/1048576))MB)"
    fi
  done
}

# THE ONLY PLACE ANYTHING GETS STAGED (2026-08-02). There used to be two copies of this — one in
# push(), one in the rebase-recovery — and they had already drifted: the recovery copy was missing
# pga_model.sqlite, so a DB the normal path refuses to commit was committed by the recovery. Worse,
# unstage_big was called ONLY from the normal path, so the recovery's `git checkout "$C" -- *.sqlite`
# happily re-staged the 114MB golf_lines.sqlite the guard had just removed -> push rejected by
# GitHub's 100MB hard limit -> recovery -> repeat, for 19 hours, with the heartbeat green.
# -f is kept because several tracked-and-gitignored caches are what the digests read; that is also
# why .gitignore alone cannot protect a file here and the :(exclude) pathspec must carry it.
stage_all(){
  git add -A -f -- . \
    ':(exclude)fanduel_props.sqlite' ':(exclude)fanduel_props.bak.sqlite' \
    ':(exclude)wnba_lines.sqlite' ':(exclude)golf_lines.sqlite' 2>/dev/null
  git rm --cached -q wnba_lines.sqlite golf_lines.sqlite wnba_glog_cache.json \
    fanduel_props.sqlite fanduel_props.bak.sqlite tt.sqlite tt.sqlite-wal tt.sqlite-shm \
    wnba_ledger.sqlite wnba_proj_log.sqlite wnba_clv.sqlite pga_model.sqlite 2>/dev/null || true
  unstage_big
}

# DB SYMLINK GUARD (2026-07-29): the live databases live in ~/wnba_data and the repo holds
# symlinks, so a git checkout/reset can only overwrite a POINTER. If that happens, re-link.
# A real file found in the link's place is an old tracked blob -- park it, never delete it.
# SLOW BLOCK (ported from Actions 2026-07-29): model fits and recalibration. Expensive and
# slow-moving, so ~every 4h rather than on the hot path. Marker file keeps it honest across
# restarts so a bouncing service cannot refit every boot.
# CROSS-SPORT COLLECTORS (ported from collect-odds.yml 2026-07-29). ~30 min, the cadence
# Actions ran them at. All five verified from Oracle before the cron was cut.
cross_sport_block(){
  local m="$HOME/.wnba_xsport_last" now; now=$(date -u +%s)
  local last; last=$(cat "$m" 2>/dev/null || echo 0)
  [ $(( now - last )) -lt 1800 ] && return 0
  echo "$now" > "$m"
  python3 collect.py       >/dev/null 2>&1 || true   # tennis (Pinnacle)
  python3 nba_injuries.py  >/dev/null 2>&1 || true
  python3 nba_flags.py     >/dev/null 2>&1 || true
  python3 nfl_totals.py    >/dev/null 2>&1 || true
  python3 bet_ledger.py    >/dev/null 2>&1 || true
}

# NIGHTLY DIGEST (ported from nightly-digest.yml). Actions needed five crons because its
# scheduler silently drops runs; a systemd loop does not, so one firing + a date marker is
# both simpler and more reliable. 05:40 UTC == 11:40pm MT.
nightly_block(){
  local h; h=$(date -u +%H%M)
  case "$h" in 054*) ;; *) return 0 ;; esac
  local m="$HOME/.wnba_nightly_last" key; key="$(date -u +%F)"
  [ "$(cat "$m" 2>/dev/null)" = "$key" ] && return 0
  echo "$key" > "$m"
  echo "[$(date -u +%H:%M)] nightly digest"
  python3 db_sync.py --build  >/dev/null 2>&1 || true
  python3 bet_ledger.py       >/dev/null 2>&1 || true
  python3 daily_digest.py     >/dev/null 2>&1 || true
  python3 dashboard.py        >/dev/null 2>&1 || true
  python3 db_sync.py --export >/dev/null 2>&1 || true
}

# PINNACLE + EDGE SCAN (ported from collect-odds.yml 2026-07-29). Verified reachable from
# Oracle first: guest.api.arcadia HTTP 200 / 63 sports, so an empty result is a real empty
# slate, not a silent datacenter-IP block.
pin_block(){
  local m="$HOME/.wnba_pin_last" now; now=$(date -u +%s)
  local last; last=$(cat "$m" 2>/dev/null || echo 0)
  [ $(( now - last )) -lt 600 ] && return 0
  echo "$now" > "$m"
  python3 wnba_collect.py   >/dev/null 2>&1 || true
  python3 wnba_edge_scan.py >/dev/null 2>&1 || true
}

slow_block(){
  local m="$HOME/.wnba_slow_last" now; now=$(date -u +%s)
  local last; last=$(cat "$m" 2>/dev/null || echo 0)
  [ $(( now - last )) -lt 14400 ] && return 0
  echo "$now" > "$m"
  echo "[$(date -u +%H:%M)] slow block: clv report + model fits"
  python3 wnba_clv.py --report >/dev/null 2>&1 || true
  python3 wnba_question_log.py --resolve --recalibrate >/dev/null 2>&1 || true
  python3 wnba_ledger.py --learn >/dev/null 2>&1 || true
  python3 learn.py     >/dev/null 2>&1 || true   # benches negative-CLV markets
  python3 gg_timing.py >/dev/null 2>&1 || true   # NBA line-timing (name is legacy)
  python3 wnba_lineup_model.py >/dev/null 2>&1 || true
  python3 wnba_redist.py --fit --teams ATL,CHI,CON,DAL,GS,IND,LA,LV,MIN,NY,PHX,POR,SEA,TOR,WSH >/dev/null 2>&1 || true
}

# WATCHLIST DIGEST (ported): fires once per target UTC hour. TIME-based, not tick-based, and
# marker-guarded so a restart inside the hour cannot double-push to the phone.
digest_block(){
  local h; h=$(date -u +%H)
  case "$h" in 16|20) ;; *) return 0 ;; esac
  local m="$HOME/.wnba_digest_last" key; key="$(date -u +%F)-$h"
  [ "$(cat "$m" 2>/dev/null)" = "$key" ] && return 0
  echo "$key" > "$m"
  echo "[$(date -u +%H:%M)] watchlist digest -> ntfy"
  python3 show_watchlist.py --push >/dev/null 2>&1 || true
}

db_guard(){
  for f in wnba_ledger.sqlite wnba_clv.sqlite wnba_proj_log.sqlite fanduel_props.sqlite wnba_lines.sqlite; do
    [ -L "$f" ] && continue
    if [ -e "$HOME/wnba_data/$f" ]; then
      if [ -f "$f" ]; then
        mkdir -p .git-clobbered
        mv "$f" ".git-clobbered/$f.$(date -u +%H%M%S)" 2>/dev/null
        echo "db-guard: git clobbered $f — parked the stale copy, re-linking"
      fi
      ln -sfn "$HOME/wnba_data/$f" "$f" 2>/dev/null
    fi
  done
}

push(){
  # disk guard (same postmortem): if the root FS dips under 2GB free, repack immediately —
  # bounded by pack.threads=1 / windowMemory=32m so it can't swap-storm the 956MB box.
  if [ "$(df --output=avail / | tail -1 | tr -d ' ')" -lt 2000000 ]; then
    echo "[$(date +%H:%M)] low disk -> git gc"; git gc --prune=now -q 2>/dev/null || true
  fi
  python3 db_sync.py --export >/dev/null 2>&1 || true   # WNBA DBs -> data/*/
  stage_all
  # NEVER commit wnba_lines.sqlite: it's the VM-local WNBA lines DB, gitignored, and was
  # ballooning to 100MB (the 2-day prune lived in the now-disabled wnba-watch.yml and was
  # dropped on the VM migration). `git add -A -f` force-re-adds it every cycle despite the
  # ignore -> committing/hashing 100MB every 75s + git auto-gc repacking those blobs = the
  # swap-thrash. Unstage it here each cycle (keeps -f for the small caches the digests need).
  # NOTE: use `|| true`, NOT `|| return 0`. Since wnba_lines.sqlite (the file that changed every
  # cycle) is now excluded, many cycles have "nothing to commit" — returning early there SKIPS the
  # push, so any already-committed-but-unpushed commits (e.g. a fresh dashboard from fullscan, or a
  # push that failed during a thrash) pile up and origin/Pages/Actions all lag the VM. Always fall
  # through to pull+push so pending commits flush even on a no-change cycle.
  git commit -m "vm loop data [skip ci]" -q 2>/dev/null || true
  git pull --rebase --autostash -X theirs -q "$URL" main 2>/dev/null || {
    # Rebase wedged (usually an OOM kill mid-rebase on this 956MB box). Unwedge WITHOUT losing
    # data: a bare `reset --hard origin/main` rolled tracked DBs back to origin's older copies —
    # wnba_ledger.sqlite (live bets!), wnba_notified.txt (SEEN -> duplicate-ping storm), CLV.
    # Proven live 2026-07-17 04:00 (ate a dashboard-bake commit). So: reset to origin's tip to
    # unwedge, then REPLAY this VM's data files from the pre-reset tip and recommit. Code
    # (.py/.sh/.yml) is deliberately NOT replayed — fresh deploys from origin must win.
    # SELF-HEAL A CORRUPT REBASE DIR (2026-07-30). `git rebase --abort` FAILS with exit 1 when
    # the rebase was killed mid-flight (OOM on this 956MB box) and .git/rebase-merge is left
    # holding only `autostash` with no `head-name`. It then cannot self-clean, every subsequent
    # `git pull --rebase` dies on the directory's mere EXISTENCE, and the loop is pinned in this
    # recovery path forever -- silently reverting code from origin every couple of minutes.
    # Observed live: 25+ minutes of "rebase failed -> data replayed onto origin tip", which ate a
    # deployed wnba_alert patch twice. Preserve any autostash as a ref (it is a real commit
    # object and would otherwise be gc'd), then remove the directory so the next pull is clean.
    git rebase --abort 2>/dev/null || {
      for _d in rebase-merge rebase-apply; do
        if [ -f ".git/$_d/autostash" ]; then
          git update-ref "refs/wedged/$_d-$(date +%Y%m%d%H%M%S)" \
            "$(cat ".git/$_d/autostash")" 2>/dev/null || true
        fi
        rm -rf ".git/$_d"
      done
      echo "[$(date +%H:%M)] cleared a corrupt rebase dir (abort could not)"
    }
    C=$(git rev-parse HEAD)
    git fetch -q "$URL" main 2>/dev/null && git reset --hard FETCH_HEAD -q 2>/dev/null
    git checkout "$C" -- "*.sqlite" 2>/dev/null || true
    git checkout "$C" -- "*.json"   2>/dev/null || true
    # *.jsonl is NOT matched by *.json (2026-07-28): the recovery reset
    # underdog_log.jsonl to origin and destroyed two breaking rulings whose tweet ids
    # were already in the replayed underdog_seen.txt, so they could never re-arrive.
    git checkout "$C" -- "*.jsonl"  2>/dev/null || true
    git checkout "$C" -- "*.txt"    2>/dev/null || true
    git checkout "$C" -- "*.md"     2>/dev/null || true
    git checkout "$C" -- docs/     2>/dev/null || true
    # NEVER replay Actions-owned snapshots backwards (2026-07-17 disk-full postmortem: replaying
    # the 45MB fanduel_props over origin every cycle ping-ponged with Actions' fresh commits ->
    # a new 45MB blob per cycle with gc off -> 39GB of loose objects -> disk 100% -> loop dead).
    # (2026-07-27) fanduel_props.sqlite is VM-LOCAL now (untracked, 100MB vs
    # GitHub hard limit); never replay it from origin.
    python3 db_sync.py --export >/dev/null 2>&1 || true   # WNBA DBs -> data/*/
  stage_all
    git commit -qm "vm loop data (replayed after failed rebase) [skip ci]" 2>/dev/null || true
    echo "[$(date +%H:%M)] rebase failed -> data replayed onto origin tip"
  }
  # STAMP ONLY ON A REAL SUCCESS. This file is what beat() reads to decide whether the loop has
  # earned a heartbeat, so it must record that git push exited 0 -- not that push() was reached.
  if git push -q "$URL" HEAD:main 2>/dev/null; then
    date -u +%s > "$HOME/.wnba_push_ok"
  else
    echo "[$(date +%H:%M)] push deferred"
  fi; }

collectors(){
  # Absorb Actions'/Mac's fresh line rows. lines_ingest.py reads the small per-source delta
  # JSONs (the ONLY way line rows travel now — the 100MB DB hit GitHub's hard file limit
  # 2026-07-25 and blob pushes are rejected outright); fd_merge stays as legacy-blob belt.
  python3 lines_ingest.py 2>&1 | grep -v "^$" || true
  python3 fd_merge.py 2>&1 | grep -v "^$" || true
  python3 fd_collect.py --wnba >/dev/null 2>&1 || true
  # NOTE (2026-07-23): MLB FD collection is NOT run here. Tried it for board responsiveness but the
  # loop git-commits the 81MB fanduel_props.sqlite every cycle and its conflict-fallback (reset --hard)
  # reverts the loop's fresh MLB writes back to Actions' version — so per-cycle MLB never persisted, and
  # the extra fetch only added load to the memory-tight box during WNBA game windows (where speed IS the
  # edge). MLB outs lines come from Actions (~30min, reliably persisted); the board reads them. The real
  # fix for a fast board = stop committing the 81MB DB to git each cycle (push a small JSON, like TT).
  # DK lines arrive via the Mac's residential IP (dk_publish.py -> dk_board.json, git-pulled
  # each cycle); ingest lights up book-aware prices everywhere. Local-only, cheap, idempotent.
  python3 dk_ingest.py >/dev/null 2>&1 || true
  # dk_collect DISABLED on the VM (2026-07-16): DraftKings Akamai-blocks the Oracle datacenter
  # IP -> it 403s EVERY cycle (never once landed a row from here), but still spawns a curl_cffi
  # chrome-impersonation process each time = pure memory pressure on the 956MB box for nothing.
  # Re-enable only behind a residential proxy. (DK line-shopping runs fine from the Mac.)
  # python3 dk_collect.py --wnba >/dev/null 2>&1 || true
  python3 wnba_ledger.py --grade >/dev/null 2>&1 || true
  python3 wnba_clv.py --close >/dev/null 2>&1 || true
  # PORTED FROM ACTIONS 2026-07-29 — cheap grading belongs next to the action, not on a cron.
  python3 wnba_clv.py --grade >/dev/null 2>&1 || true
  python3 wnba_proj_log.py --grade >/dev/null 2>&1 || true
  prune_lines; board; }

# Keep wnba_lines.sqlite at its intended ~2-day WNBA window (the retention that lived in the
# now-disabled wnba-watch.yml, orphaned on the VM migration). Cheap DELETE each cycle; sqlite
# reuses freed pages so the file stays ~1-2MB after the one-time VACUUM done at deploy.
prune_lines(){ python3 - >/dev/null 2>&1 <<'PY' || true
import sqlite3, os
c=sqlite3.connect("wnba_lines.sqlite"); c.execute("PRAGMA busy_timeout=60000")
c.execute("DELETE FROM fd_lines WHERE collected_at < datetime('now','-2 days')")
c.commit()
# VACUUM, which this never did. The old comment claimed "sqlite reuses freed pages so the file
# stays ~1-2MB" -- pages ARE reused, but the file never RETURNS space without a VACUUM. Measured
# 2026-08-02: 274MB holding a 136MB freelist, i.e. half the file was deleted rows it would not
# give back. A third of the boot disk, on the box whose worst documented outage was disk-full.
if os.path.getsize("wnba_lines.sqlite") > 40*1024*1024:
    c.execute("VACUUM")
c.close()
# golf_lines.sqlite: THE THIRD FILE to hit this exact cliff (wnba_lines 100MB, fanduel_props 100MB
# on 2026-07-25 = an 18h line freeze, now this one at 114.2MB = a 19h publish outage). It is
# excluded from git entirely now, so the 100MB limit no longer applies -- this is purely disk. The
# durable record lives in golf_moves.sqlite, which keeps the paired open->close permanently, so the
# raw snapshot archive genuinely does not need to be kept forever.
try:
    c=sqlite3.connect("golf_lines.sqlite"); c.execute("PRAGMA busy_timeout=60000")
    c.execute("DELETE FROM golf_lines WHERE collected_at < datetime('now','-2 days')")
    c.commit()
    if os.path.getsize("golf_lines.sqlite") > 60*1024*1024:
        c.execute("VACUUM")
    c.close()
except Exception:
    pass
# fanduel_props hit GitHub's HARD 100MB blob limit 2026-07-25 (99.x committed, pushes of bigger
# versions rejected outright -> the 18h line freeze). This VM is now the ONLY committer of the
# blob: keep 3 days of rows and VACUUM when the file nears the cliff so it never crosses again.
c=sqlite3.connect("fanduel_props.sqlite"); c.execute("PRAGMA busy_timeout=60000")
c.execute("DELETE FROM fd_lines WHERE collected_at < datetime('now','-3 days')")
c.commit()
if os.path.getsize("fanduel_props.sqlite") > 80*1024*1024:
    c.execute("VACUUM")
c.close()
PY
}

# TT Elite FanDuel.ca total-line board — the VM is the only host that can reach FanDuel.ca
# (Actions' US IP is geo-blocked). Writes fd_board.json; push() commits it to this PUBLIC
# repo, and tt-elite's daily.yml fetches it via raw.githubusercontent to grade Elite at real
# lines. THROTTLED to >=4 min between fetches (self-timed, not per-cycle) so it adds minimal
# memory pressure on the 956MB box — TT lines don't need 75s freshness.
board(){ local f=/tmp/.fd_board_last now last; now=$(date +%s); last=$(cat "$f" 2>/dev/null || echo 0)
  [ $((now - last)) -lt 240 ] && return 0
  python3 fd_tt.py --write --board --captured-at "$(date -u +%FT%TZ)" >/dev/null 2>&1 && echo "$now" > "$f" || true; }

fullscan(){
  if ! python3 wnba_alert.py >/dev/null 2>/tmp/.alert_err; then
    # the flag engine crashing is a SILENT-EDGE-KILLER (2026-07-17: a missing DB column killed
    # every pass for 2.5h while Boston was ruled out) -> page ONCE per distinct error + journal it
    err=$(tail -2 /tmp/.alert_err | tr -d "\n" | cut -c1-160)
    echo "[$(date +%H:%M)] ALERT PASS FAILED: $err"
    sig=$(echo "$err" | md5sum | cut -c1-8)
    if [ ! -f "/tmp/.alert_err_$sig" ]; then
      touch "/tmp/.alert_err_$sig"
      curl -s -m 10 -H "Priority: urgent" -H "Title: WNBA flag engine CRASHED" \
        -d "$err" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
    fi
  fi
  python3 dashboard.py >/dev/null 2>&1 || true
  python3 wnba_oppbig_shadow.py >/dev/null 2>&1 || true
  python3 wnba_ledger.py --train >/dev/null 2>&1 || true
  python3 wnba_context_report.py >/dev/null 2>&1 || true; }

# exit 0 when a game is live or tips within ~75min -> switch to fast scratch polling
# Sleep, but wake every second to look for a fresh @UnderdogWNBA ruling. The flag used to be
# checked once per tick, so a ruling that landed just after a tick waited the full 25s (75s
# cold) before anything happened — pure dead time on the one path where speed IS the edge.
# The scan still runs in the LOOP, never in the watcher: one writer to the sqlite files.
wait_trig(){
  local n="$1" i=0
  while [ "$i" -lt "$n" ]; do
    [ -f /tmp/.force_fullscan ] && return 0
    sleep 1; i=$((i+1))
  done
  return 0
}

in_hot(){ python3 hot_window.py >/dev/null 2>&1; }

# liveness heartbeat: one parentless commit force-pushed to the `heartbeat` branch each cycle
# (no history growth). The Actions vm-watchdog alerts if this stops updating (VM down / token dead).
beat(){
  local c b t k last now age
  # A HEARTBEAT MUST MEAN "I AM PUBLISHING", NOT "I AM LOOPING". This commit is synthesised with
  # plumbing and force-pushed to its own branch, so it bypasses the index, HEAD and main entirely
  # -- which is exactly why it stayed green through 19 hours of rejected pushes, a detached HEAD
  # and a missing refs/heads/main. Withholding it when the publisher is stale routes a dead
  # publisher into the alert path that already exists: Actions' vm-watchdog pages at 15 minutes.
  # PROCESS liveness is a different question and keeps its own separate signal
  # (~/.wnba_loop_beat + the on-box wnba-watchdog.timer, which restarts rather than pages).
  last=$(cat "$HOME/.wnba_push_ok" 2>/dev/null || echo 0)
  now=$(date -u +%s); age=$(( now - last ))
  if [ "$age" -gt 1800 ]; then
    echo "[$(date +%H:%M)] heartbeat WITHHELD -- no successful push for $((age/60)) min"
    return 0
  fi
  c="$(date -u +%s) $(date -u +%FT%TZ)"
  b=$(printf '%s\n' "$c" | git hash-object -w --stdin 2>/dev/null) || return 0
  t=$(printf '100644 blob %s\theartbeat.txt\n' "$b" | git mktree 2>/dev/null) || return 0
  k=$(printf 'vm heartbeat %s\n' "$c" | git commit-tree "$t" 2>/dev/null) || return 0
  git push -q --force "$URL" "$k:refs/heads/heartbeat" 2>/dev/null || true; }

# Seed the publish stamp on a cold start so a freshly booted box does not page before its first
# push cycle has run. A genuinely broken publisher still pages ~30 min after boot.
[ -f "$HOME/.wnba_push_ok" ] || date -u +%s > "$HOME/.wnba_push_ok"
echo "[$(date)] wnba-loop up (topic:$([ -n "$NTFY_TOPIC" ]&&echo yes||echo NO) pat:$([ -n "$GIT_PAT" ]&&echo yes||echo NO))"
i=0; hot_ticks=0; cold_i=0; was_hot=2
while true; do i=$((i+1))
  # WINDOW-INDEPENDENT (2026-07-29): must run in COLD windows too — the watchlist digest
  # fires at 16:00 UTC, which is not a hot window, and a self-check that only runs while
  # the loop is already busy is not a health check.
  date -u +%s > "$HOME/.wnba_loop_beat"   # local liveness (survives a wedged git)
  cross_sport_block
  nightly_block
  pin_block
  slow_block
  date -u +%s > "$HOME/.wnba_loop_beat"   # re-stamp: the 4h slow block is a legitimately long tick
  digest_block
  python3 wnba_watch.py --watchdog >/dev/null 2>&1 || true
  beat
  if in_hot; then
    # HOT PATH: wnba_watch (scratch detector -> instant ntfy) every ~25s.
    # Refresh odds/grade + dashboard + push every 3rd tick (~75s) so the board tracks the action.
    if [ "$was_hot" != "1" ]; then echo "[$(date +%H:%M)] >>> HOT window (25s scratch polling)"; hot_ticks=0; fi
    was_hot=1; hot_ticks=$((hot_ticks+1))
    db_guard
    # TRIGGER FIRST (2026-07-29): push() can block for minutes on a slow git op, and while it
    # does, a fresh @UnderdogWNBA ruling sits unserved. Check the flag before ANY git work so
    # breaking news always gets its scan on the very next tick.
    if [ -f /tmp/.force_fullscan ]; then
      rm -f /tmp/.force_fullscan
      echo "[$(date +%H:%M)] TRIGGERED full scan (fresh out / new lines)"; fullscan
    fi
    python3 wnba_watch.py >/dev/null 2>&1 || true
    python3 wnba_news_watch.py 2>&1 | grep -i "NEWS\|trigger" || true
    # underdog_watch runs as its own systemd daemon (underdog-watch.service, --loop 10s) — NOT here,
    # so it polls @UnderdogWNBA every 10s independently without waiting on this loop's 25-60s cadence.
    if [ -f /tmp/.force_fullscan ]; then
      rm -f /tmp/.force_fullscan
      echo "[$(date +%H:%M)] TRIGGERED full scan (fresh out / new lines)"; fullscan
    fi
    if [ $((hot_ticks % 3)) -eq 0 ]; then
      git pull -q "$URL" main 2>/dev/null || true
      collectors
      python3 dashboard.py >/dev/null 2>&1 || true
      push
    fi
    # next-day plays must fire fast too (user: post as soon as 1 out-confirmation + FD lines):
    # the full flagger also runs every ~40 hot ticks (~17 min) — it never ran in hot before,
    # so a new out + fresh next-day lines could sit unflagged for a whole evening.
    # FAST INJURY PROBE near tip (user 2026-07-17, the Boston ruling): a late OUT pulls the
    # slate; the edge is catching the REPOSTED lines within minutes. Full beneficiary scan
    # every 6 hot ticks (~2.5 min) instead of ~17 min. ~52s/pass on this box = ~35% duty,
    # hot windows only.
    if [ $((hot_ticks % 6)) -eq 0 ]; then echo "[$(date +%H:%M)] full scan (hot fast-probe)"; fullscan; fi
    wait_trig 25
  else
    # COLD PATH: normal 75s cycle; heavy full scan every 25 cold iterations.
    if [ "$was_hot" != "0" ]; then echo "[$(date +%H:%M)] <<< COLD window (75s cycle)"; fi
    was_hot=0; cold_i=$((cold_i+1))
    git pull -q "$URL" main 2>/dev/null || true
    collectors
    python3 wnba_watch.py >/dev/null 2>&1 || true
    python3 wnba_news_watch.py 2>&1 | grep -i "NEWS\|trigger" || true
    # underdog_watch runs as its own systemd daemon (underdog-watch.service, --loop 10s) — NOT here,
    # so it polls @UnderdogWNBA every 10s independently without waiting on this loop's 25-60s cadence.
        if [ -f /tmp/.force_fullscan ]; then
      rm -f /tmp/.force_fullscan
      echo "[$(date +%H:%M)] TRIGGERED full scan (fresh out / new lines)"; fullscan
    fi
if [ $((cold_i % 8)) -eq 1 ]; then echo "[$(date +%H:%M)] full scan (cold iter $cold_i)"; fullscan; fi
    push; wait_trig 60
  fi
done
