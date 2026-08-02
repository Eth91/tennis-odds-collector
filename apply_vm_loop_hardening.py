"""Make the loop's publisher unable to wedge itself, and make a wedge impossible to miss.

THE OUTAGE THIS FIXES (2026-08-01/02). The main VM published nothing for 19 hours while every
monitor reported green. Root cause, in order:

  1. `golf_lines.sqlite` had NO prune. It reached 114.2 MiB — past GitHub's 100 MB HARD limit — so
     every push was rejected outright.
  2. A rejected push drops into the rebase-recovery path, which replays this VM's data with
     `git checkout "$C" -- "*.sqlite"`. That RE-STAGES the 114 MB file that `unstage_big` had just
     removed, because unstage_big runs in the normal path only and never in the recovery. The
     recovery then commits the oversized blob again and the next push is rejected again. Forever.
  3. 17 GB of pack accumulated from ~7000 replayed commits of that blob; `refs/heads/main` was lost
     and HEAD went detached.
  4. Nothing paged, because `beat()` builds a synthetic parentless commit with plumbing and
     force-pushes it. It never touches the index, HEAD or main — so a totally wedged repo with a
     dead publisher still produced a perfectly fresh heartbeat.

FIVE CHANGES, and the last one is the only one that makes the class self-reporting.

A. unstage_big MOVES INTO THE SHARED STAGING FUNCTION so it cannot be skipped by a code path that
   forgets to call it. That is what happened: the guard existed, was correct, and simply was not on
   the path that mattered.

B. ONE staging function, not two copies. The normal path and the recovery path each carried their
   own `git add -A -f` + `git rm --cached` pair, and they had ALREADY DRIFTED — the recovery copy
   was missing `pga_model.sqlite`, so a model DB the normal path refuses to commit was committed by
   the recovery. Same failure family as tt_board's filter drifting from check_today's gate and the
   correlation cap drifting from selection's band. A single function cannot drift from itself.

C. golf_lines.sqlite joins the exclude pathspec AND the uncache list. .gitignore alone is not
   enough and this is the subtle part: the loop stages with `git add -A -f`, and -f FORCE-ADDS
   ignored files. The ignore is real (it is what stops a `git add -A` on the Mac) but on this box
   only the `:(exclude)` pathspec actually holds.

D. golf_lines gets the 2-day prune every other line DB already has, and wnba_lines finally gets a
   VACUUM. wnba_lines is presently 274 MB holding 136 MB of freelist — its comment claims "sqlite
   reuses freed pages so the file stays ~1-2MB", which is simply not true: pages are reused, but
   the file never gives space back without a VACUUM, and this one has been growing for weeks. That
   is a third of the boot disk on a box whose documented worst outage was disk-full.

E. THE HEARTBEAT NOW MEANS "I AM PUBLISHING", not "I am looping". push() stamps ~/.wnba_push_ok
   only when git push actually exits 0; beat() refuses to emit a heartbeat when that stamp is over
   30 minutes old. The existing Actions vm-watchdog pages on a heartbeat older than 15 minutes, so
   a dead publisher now pages within ~45 minutes with no new infrastructure and no new alert path.
   The two liveness signals stay deliberately separate and answer different questions:
       ~/.wnba_loop_beat  + wnba-watchdog.timer (on-box)   -> is the PROCESS alive -> restart it
       git heartbeat      + Actions vm-watchdog (off-box)  -> is it PUBLISHING     -> page the user
   A watchdog that only proves the process is alive is exactly how 19 hours of silence looked green.
"""
import io
import re
import shutil
import subprocess

P = "vm_loop.sh"
s = io.open(P, encoding="utf-8").read()

if "stage_all()" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── A+B+C. one staging function, guard inside it, golf_lines excluded ───────────────────────────
# ORDER MATTERS: collapse the two existing staging sites FIRST, then insert the replacement. Doing
# it the other way round makes the new function's own `git rm --cached` line the third match of the
# regex meant to delete the old ones — it would have eaten the fix it had just installed.
ADD = ("  git add -A -f -- . ':(exclude)fanduel_props.sqlite' "
       "':(exclude)fanduel_props.bak.sqlite' ':(exclude)wnba_lines.sqlite' 2>/dev/null\n")
assert s.count(ADD) == 2, "expected exactly 2 add sites, found %d" % s.count(ADD)
s = s.replace(ADD, "  stage_all\n")

RM = re.compile(r"^[ \t]*git rm --cached -q wnba_lines\.sqlite .*\n", re.M)
n_rm = len(RM.findall(s))
assert n_rm == 2, "expected 2 rm --cached sites, found %d" % n_rm
s = RM.sub("", s)

# unstage_big was called explicitly in push(); it now lives inside stage_all
s = s.replace("  unstage_big\n  git commit -m \"vm loop data [skip ci]\"",
              "  git commit -m \"vm loop data [skip ci]\"", 1)

OLD_GUARD_END = '''      git rm --cached -q "$f" 2>/dev/null && echo "size-guard: unstaged $f ($((sz/1048576))MB)"
    fi
  done
}
'''
NEW_GUARD_END = '''      git rm --cached -q "$f" 2>/dev/null && echo "size-guard: unstaged $f ($((sz/1048576))MB)"
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
  git add -A -f -- . \\
    ':(exclude)fanduel_props.sqlite' ':(exclude)fanduel_props.bak.sqlite' \\
    ':(exclude)wnba_lines.sqlite' ':(exclude)golf_lines.sqlite' 2>/dev/null
  git rm --cached -q wnba_lines.sqlite golf_lines.sqlite wnba_glog_cache.json \\
    fanduel_props.sqlite fanduel_props.bak.sqlite tt.sqlite tt.sqlite-wal tt.sqlite-shm \\
    wnba_ledger.sqlite wnba_proj_log.sqlite wnba_clv.sqlite pga_model.sqlite 2>/dev/null || true
  unstage_big
}
'''
assert OLD_GUARD_END in s, "size-guard anchor"
s = s.replace(OLD_GUARD_END, NEW_GUARD_END, 1)

# ── D. golf_lines gets the prune every other line DB has; wnba_lines finally VACUUMs ────────────
OLD_PRUNE = '''c=sqlite3.connect("wnba_lines.sqlite")
c.execute("DELETE FROM fd_lines WHERE collected_at < datetime('now','-2 days')")
c.commit(); c.close()'''
NEW_PRUNE = '''c=sqlite3.connect("wnba_lines.sqlite"); c.execute("PRAGMA busy_timeout=60000")
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
    pass'''
assert OLD_PRUNE in s, "prune anchor"
s = s.replace(OLD_PRUNE, NEW_PRUNE, 1)

# ── E. the heartbeat now means "publishing", not "looping" ───────────────────────────────────────
OLD_PUSH = '''  git push -q "$URL" HEAD:main 2>/dev/null || echo "[$(date +%H:%M)] push deferred"; }'''
NEW_PUSH = '''  # STAMP ONLY ON A REAL SUCCESS. This file is what beat() reads to decide whether the loop has
  # earned a heartbeat, so it must record that git push exited 0 -- not that push() was reached.
  if git push -q "$URL" HEAD:main 2>/dev/null; then
    date -u +%s > "$HOME/.wnba_push_ok"
  else
    echo "[$(date +%H:%M)] push deferred"
  fi; }'''
assert OLD_PUSH in s, "push tail anchor"
s = s.replace(OLD_PUSH, NEW_PUSH, 1)

OLD_BEAT = '''beat(){
  local c b t k
  c="$(date -u +%s) $(date -u +%FT%TZ)"'''
NEW_BEAT = '''beat(){
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
  c="$(date -u +%s) $(date -u +%FT%TZ)"'''
assert OLD_BEAT in s, "beat anchor"
s = s.replace(OLD_BEAT, NEW_BEAT, 1)

# a fresh boot must not page before the first push has had a chance to happen
OLD_BOOT = '''echo "[$(date)] wnba-loop up (topic:'''
NEW_BOOT = '''# Seed the publish stamp on a cold start so a freshly booted box does not page before its first
# push cycle has run. A genuinely broken publisher still pages ~30 min after boot.
[ -f "$HOME/.wnba_push_ok" ] || date -u +%s > "$HOME/.wnba_push_ok"
echo "[$(date)] wnba-loop up (topic:'''
assert OLD_BOOT in s, "boot anchor"
s = s.replace(OLD_BOOT, NEW_BOOT, 1)

shutil.copyfile(P, "/tmp/vm_loop.prehardening.sh")
io.open(P, "w", encoding="utf-8").write(s)
r = subprocess.run(["bash", "-n", P], capture_output=True, text=True)
if r.returncode:
    shutil.copyfile("/tmp/vm_loop.prehardening.sh", P)
    raise SystemExit("bash -n FAILED, reverted:\n" + r.stderr)
print("  + stage_all() (one staging path, guard inside), golf_lines excluded+pruned,")
print("  + wnba_lines VACUUMs, heartbeat now requires a successful push")
