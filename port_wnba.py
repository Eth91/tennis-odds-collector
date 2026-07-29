"""Port the last Actions-only WNBA steps into vm_loop.sh, so the crons can be cut.

The VM loop already ran collectors, wnba_watch, news_watch, the flagger, dashboard, ledger
grade/train, clv --close and context_report. These were still ONLY in Actions:

  wnba_clv.py --grade / --report      CLV grading + the report the board reads
  wnba_proj_log.py --grade            projection-tracker grading
  wnba_question_log.py --resolve      sit-prob recalibration
  wnba_watch.py --watchdog            the scratch-detector's own health check
  wnba_lineup_model.py                empirical replacement model (fit)
  wnba_redist.py --fit                per-team redistribution fit
  show_watchlist.py --push            the twice-daily watchlist digest

All seven were verified to RUN from Oracle before porting -- the 24live lesson: never move a
step without proving its data source is reachable from the box that will run it.

CADENCE. Grading is cheap and belongs near the action, so clv/proj grading joins the existing
~75s collectors block. The model fits and the recalibration are expensive and slow-moving, so
they run once every ~4h. The digest is TIME-based (not tick-based) and fires once per target
hour, guarded by a marker file so a restart cannot double-send.
"""
import ast  # noqa: F401
import io
import sys

p = "vm_loop.sh"
s = io.open(p, encoding="utf-8").read()

# 1) grading steps ride along with the existing collectors block
OLD = '''  python3 wnba_ledger.py --grade >/dev/null 2>&1 || true
  python3 wnba_clv.py --close >/dev/null 2>&1 || true'''
NEW = '''  python3 wnba_ledger.py --grade >/dev/null 2>&1 || true
  python3 wnba_clv.py --close >/dev/null 2>&1 || true
  # PORTED FROM ACTIONS 2026-07-29 — cheap grading belongs next to the action, not on a cron.
  python3 wnba_clv.py --grade >/dev/null 2>&1 || true
  python3 wnba_proj_log.py --grade >/dev/null 2>&1 || true'''
if OLD not in s:
    sys.exit("ANCHOR MISSING: collectors grading")
s = s.replace(OLD, NEW, 1)

# 2) slow block + time-gated digest, defined next to the other helpers
GUARD = '''
# SLOW BLOCK (ported from Actions 2026-07-29): model fits and recalibration. Expensive and
# slow-moving, so ~every 4h rather than on the hot path. Marker file keeps it honest across
# restarts so a bouncing service cannot refit every boot.
slow_block(){
  local m="$HOME/.wnba_slow_last" now; now=$(date -u +%s)
  local last; last=$(cat "$m" 2>/dev/null || echo 0)
  [ $(( now - last )) -lt 14400 ] && return 0
  echo "$now" > "$m"
  echo "[$(date -u +%H:%M)] slow block: clv report + model fits"
  python3 wnba_clv.py --report >/dev/null 2>&1 || true
  python3 wnba_question_log.py --resolve --recalibrate >/dev/null 2>&1 || true
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
'''
anchor = "db_guard(){"
if anchor not in s:
    sys.exit("ANCHOR MISSING: db_guard")
s = s.replace(anchor, GUARD.lstrip("\n") + "\n" + anchor, 1)

# 3) call them, and add the watch watchdog, right after db_guard each hot tick
OLD3 = """    db_guard
    # TRIGGER FIRST (2026-07-29): push() can block for minutes on a slow git op, and while it"""
NEW3 = """    db_guard
    slow_block
    digest_block
    python3 wnba_watch.py --watchdog >/dev/null 2>&1 || true
    # TRIGGER FIRST (2026-07-29): push() can block for minutes on a slow git op, and while it"""
if OLD3 not in s:
    sys.exit("ANCHOR MISSING: db_guard call")
s = s.replace(OLD3, NEW3, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("vm_loop.sh: ported clv --grade/--report, proj_log --grade, question_log,")
print("            watch --watchdog, lineup_model, redist --fit, watchlist digest")
