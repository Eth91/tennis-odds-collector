#!/usr/bin/env python3
"""NBA morning check — did the speed test collect cleanly in the last 24 hours, and what did it find?

Read-only. Prints one report; exits 1 if anything needs the user's attention (so a scheduler or a
human can tell a clean night from a broken one). Sections:

  CAPTURE   for every game that tipped in the window: was there a price snapshot within 10 min of
            tip? No snapshot = no closing line = that game's flags cannot be scored (usually: the
            Mac was asleep).
  GAPS      runs of the 10-minute cycle more than 30 min apart.
  ERRORS    failed cycle steps; news-source errors; the X watcher's heartbeat.
  REPORTS   official injury reports stored (96 a day is every mark), worst capture lag, unresolved
            names, matchups whose missing team came WITH unresolved rows (possible misattribution).
  FLAGS     shadow flags by game, tier and trigger; voided flags.
  SCORE     the speed scoreboard (nba_clv) — the canonical query of NBA_SPEED_PREREG.md.
  NEWS      each news Out seen in the window, its source, and its lead over the official report.

    python nba_morning_check.py            # last 24 h
    python nba_morning_check.py --hours 48
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRON = Path(os.environ.get("NBA_LOG_DIR") or Path.home() / "cron-jobs")   # VM: ~/nba-logs (amend. 4)
CYCLE_LOG, WATCH_LOG = CRON / "nba_cycle.log", CRON / "nba_watch.log"
LINES, NEWS, SHADOW = HERE / "nba_lines.sqlite", HERE / "nba_news.sqlite", HERE / "nba_shadow.sqlite"
TIP_WINDOW_MIN, GAP_MIN = 10, 30


def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def main(hours):
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    since = now - dt.timedelta(hours=hours)
    s_iso = since.isoformat()
    attention = []
    print(f"NBA MORNING CHECK — {now:%Y-%m-%d %H:%M} UTC, last {hours} h\n")

    # ── CAPTURE: a snapshot near every tip? ──────────────────────────────────────
    import nba_rosters as R
    try:
        sched = R.schedule()
    except R.Blind as e:
        print(f"CAPTURE  cannot read the schedule ({e})")
        sched = []
    lc = ro(LINES)
    cycles = sorted(dt.datetime.fromisoformat(t) for (t,) in lc.execute(
        "SELECT DISTINCT ts FROM cycles WHERE status IN ('ok','no_lines','partial') AND ts >= ?",
        ((since - dt.timedelta(hours=1)).isoformat(),)))
    tipped = [g for g in sched if s_iso <= g["utc"].replace("Z", "") <= now.isoformat()]
    missed = []
    for g in tipped:
        tip = dt.datetime.fromisoformat(g["utc"].replace("Z", ""))
        near = [c for c in cycles if tip - dt.timedelta(minutes=TIP_WINDOW_MIN) <= c <= tip]
        if not near:
            missed.append(f"{g['away']}@{g['home']} ({tip:%H:%M}Z)")
    print(f"CAPTURE  {len(tipped)} game(s) tipped · price snapshot within {TIP_WINDOW_MIN} min of tip: "
          f"{len(tipped) - len(missed)}/{len(tipped)}")
    if missed:
        print(f"         NO CLOSE for: {', '.join(missed)}")
        attention.append(f"{len(missed)} game(s) have no closing price (Mac asleep?)")

    # ── GAPS ─────────────────────────────────────────────────────────────────────
    gaps = [(a, b) for a, b in zip(cycles, cycles[1:]) if (b - a).total_seconds() > GAP_MIN * 60
            and b >= since]
    print(f"GAPS     {len(gaps)} gap(s) over {GAP_MIN} min between line snapshots"
          + "".join(f"\n         {a:%m-%d %H:%M} -> {b:%H:%M}Z ({(b - a).total_seconds() / 3600:.1f} h)"
                    for a, b in gaps[:8]))

    # ── ERRORS ───────────────────────────────────────────────────────────────────
    fails = Counter()
    last_msg = {}
    for line in (CYCLE_LOG.read_text().splitlines() if CYCLE_LOG.exists() else []):
        m = re.match(r"(\S+)Z (\S+)\s+rc=(\d+) ?(.*)", line)
        if m and m.group(1) >= s_iso and m.group(3) != "0":
            fails[m.group(2)] += 1
            last_msg[m.group(2)] = m.group(4)[-160:]
    src_err = Counter()
    for line in (WATCH_LOG.read_text().splitlines() if WATCH_LOG.exists() else []):
        m = re.search(r"news source error: (\w+): (\w+)", line)
        if m:
            src_err[f"{m.group(1)} ({m.group(2)})"] += 1
    print(f"ERRORS   failed cycle steps: {dict(fails) or 'none'}")
    for step, msg in last_msg.items():
        print(f"         last {step}: {msg}")
    print(f"         news-source errors in the watch log: {dict(src_err) or 'none'}")
    hb_cmd = ("systemctl is-active underdog-watch; journalctl -u underdog-watch -n 1 "
              "-o short-unix --no-pager | tail -1")
    if os.environ.get("NBA_X_LOG"):                   # running ON the VM (amendment 4): ask locally
        hb = subprocess.run(["sh", "-c", hb_cmd], capture_output=True, text=True, timeout=40)
    else:
        hb = subprocess.run(["ssh", "-i", str(Path.home() / ".ssh/oracle_vm"), "-o", "ConnectTimeout=10",
                             "-o", "BatchMode=yes", "ubuntu@155.248.217.149", hb_cmd],
                            capture_output=True, text=True, timeout=40)
    parts = hb.stdout.split()
    try:
        age = (dt.datetime.now(dt.timezone.utc).timestamp() - float(parts[1])) / 60
        hb_txt = f"{parts[0]}, last poll {age:.0f} min ago"
        if parts[0] != "active" or age > 10:
            attention.append(f"X watcher {hb_txt}")
    except (IndexError, ValueError):
        hb_txt = f"unreachable (rc {hb.returncode})"
        attention.append("X watcher unreachable")
    print(f"         X watcher (@UnderdogNBA on the VM): {hb_txt}")
    if sum(fails.values()) > 6:
        attention.append(f"{sum(fails.values())} failed cycle steps")

    # ── REPORTS ──────────────────────────────────────────────────────────────────
    nc = ro(NEWS)
    rep = nc.execute("SELECT COUNT(*), SUM(missing_teams != '') FROM reports WHERE published_at >= ?",
                     (s_iso,)).fetchone()
    n_rep, misattr = rep[0], rep[1] or 0
    lags = sorted(x for (x,) in nc.execute(
        "SELECT (julianday(fetched_at) - julianday(published_at)) * 86400 FROM reports "
        "WHERE published_at >= ?", (s_iso,)) if x is not None)
    live = [x for x in lags if x < 3600]              # > 1 h = a backfill, not a live capture
    lag = live[len(live) // 2] if live else 0
    slow = sum(1 for x in live if x > 120)
    names = [p for (p,) in nc.execute("SELECT DISTINCT player FROM snapshots WHERE pid IS NULL AND "
                                      "published_at >= ?", (s_iso,))]
    print(f"REPORTS  {n_rep} official report(s) stored (96/day = every mark) · live capture lag median "
          f"{lag:.0f} s, {slow} over 2 min (Mac asleep at the mark) · unresolved names: {names[:6] or 'none'}"
          + (f" · {misattr} with possible misattribution" if misattr else ""))
    if misattr:
        attention.append("possible misattribution in an injury report")

    # ── FLAGS ────────────────────────────────────────────────────────────────────
    if SHADOW.exists():
        sh = ro(SHADOW)
        rows = sh.execute("SELECT game_date, tier, COALESCE(horizon,0), COALESCE(trigger_src,'report'), "
                          "COUNT(*), SUM(void_reason IS NOT NULL), SUM(result IS NOT NULL) FROM flags "
                          "WHERE logged_at >= ? GROUP BY 1,2,3,4 ORDER BY 1,2", (s_iso,)).fetchall()
        print(f"FLAGS    logged in the window (game, tier, horizon, trigger: n / voided / graded):")
        for g, t, h, src, n, v, gr in rows:
            print(f"         {g} {t:<6} h{h} {src:<14} {n:3d} / {v} / {gr}")
        if not rows:
            print("         none")
    else:
        print("FLAGS    no shadow table yet")

    # ── SCORE ────────────────────────────────────────────────────────────────────
    import nba_clv as V
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V.scoreboard(V.collect())
    print("SCORE    " + "\n         ".join(l for l in buf.getvalue().splitlines()
                                        if not l.startswith(("one row", "h1 =", "unconfirmed-news",
                                                             "(amendment", "beat-close CI"))))

    # ── NEWS ─────────────────────────────────────────────────────────────────────
    try:
        items = nc.execute("""
            SELECT n.source, n.player, n.game_date, MIN(n.detected_at),
                   (SELECT MIN(s.published_at) FROM snapshots s WHERE s.pid = n.pid
                     AND s.game_date = n.game_date AND s.status = 'Out')
            FROM news_items n WHERE n.status='out' AND n.pid IS NOT NULL AND COALESCE(n.seeded,0)=0
              AND n.detected_at >= ? GROUP BY n.source, n.pid, n.game_date ORDER BY 4""",
                           (s_iso,)).fetchall()
    except sqlite3.OperationalError:
        items = []
    leads = defaultdict(list)
    print(f"NEWS     news Outs seen in the window: {len(items)}")
    for src, pl, gd, seen, off in items:
        lead = ((dt.datetime.fromisoformat(off) - dt.datetime.fromisoformat(seen)).total_seconds()
                / 60) if off else None
        if lead is not None:
            leads[src].append(lead)
        print(f"         [{src}] {pl} ({gd}) seen {seen[11:16]}Z · league "
              + (f"{off[11:16]}Z · lead {lead:+.0f} min" if off else "not (yet) listed Out"))
    for src, ls in leads.items():
        ahead = [x for x in ls if x > 1]
        print(f"         {src}: ahead of the report on {len(ahead)}/{len(ls)}"
              + (f", median lead when ahead {sorted(ahead)[len(ahead) // 2]:.0f} min" if ahead else ""))

    print("\nATTENTION: " + ("; ".join(attention) if attention else "nothing — clean night"))
    return 1 if attention else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    sys.exit(main(ap.parse_args().hours))
