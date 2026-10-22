#!/usr/bin/env python3
"""NBA speed layer — act on the official injury report the moment it publishes. MAC-ONLY.

The WNBA's money is partly SPEED: its bets beat the closing line 67% of the time, and the same
bets bought at the close earned about half as much (+11.5% vs +20.2%). The NBA analogue of its
`wnba_watch` is this: poll cheap, act only on change.

Run once a minute (cron). Each run:
  1. REPORT. The league publishes a game-dated PDF ~4 s after every :00/:15/:30/:45 mark. In the
     first minute after a mark this polls until the new report exists (HEAD every 3 s), then
     ingests it (nba_injury_report.fetch_new). Otherwise one cheap HEAD catches up.
  2. DIFF. A FRESH Out = a player listed Out for tonight in the new report who was not Out for
     that game in the previous stored report. If any fresh Out is on a team that plays tonight
     (pre-tip): refresh both books NOW (nba_lines.cycle), then run the flag pass
     (nba_flags.flags) — so each shadow flag's price is the price right after the news.
     Every trigger is logged in nba_news.sqlite `triggers` with its timings.
  3. CLOSE CAPTURE. Within HOT_LEAD_MIN of any tip, refresh lines every HOT_EVERY_MIN, so the
     closing price nba_clv rebuilds is minutes old, not up to ten.

It shares nba_cycle.sh's lock (/tmp/nba-cycle.lock), waiting up to LOCK_WAIT_S for it, so the
two never write the same databases at once. NOTHING HERE BETS: nba_flags.LIVE_TIERS is empty.

    python nba_watch.py --once
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import nba_injury_report as I

HERE = Path(__file__).resolve().parent
LOCK = Path("/tmp/nba-cycle.lock")
LOCK_WAIT_S = 50
REPORT_POLL_S, REPORT_POLL_WINDOW_S = 3, 75
HOT_LEAD_MIN, HOT_EVERY_MIN = 35, 2
TRIG_DDL = """CREATE TABLE IF NOT EXISTS triggers (
    mark TEXT, published_at TEXT, detected_at TEXT, fresh TEXT, lines_at TEXT,
    flags_at TEXT, n_flags INTEGER, note TEXT)"""


def _now():
    return dt.datetime.now(dt.timezone.utc)


@contextlib.contextmanager
def cycle_lock():
    t0 = time.time()
    while True:
        try:
            LOCK.mkdir()
            break
        except FileExistsError:
            if time.time() - LOCK.stat().st_mtime > 1800:      # a crashed run, not a live one
                LOCK.rmdir()
                continue
            if time.time() - t0 > LOCK_WAIT_S:
                yield False
                return
            time.sleep(1)
    try:
        yield True
    finally:
        try:
            LOCK.rmdir()
        except FileNotFoundError:
            pass


def fresh_outs(con, mark):
    """[(pid, name, team, game_date)] Out in `mark` but not Out in the previous report that
    listed the same game date."""
    out = []
    for gdate in [g for (g,) in con.execute(
            "SELECT DISTINCT game_date FROM snapshots WHERE mark=?", (mark,))]:
        prev = con.execute("SELECT MAX(mark) FROM snapshots WHERE game_date=? AND mark<?",
                           (gdate, mark)).fetchone()[0]
        was = {p for (p,) in con.execute(
            "SELECT pid FROM snapshots WHERE mark=? AND game_date=? AND status='Out'",
            (prev, gdate))} if prev else set()
        for pid, name, team in con.execute(
                "SELECT pid, player, team FROM snapshots WHERE mark=? AND game_date=? AND "
                "status='Out' AND pid IS NOT NULL", (mark, gdate)):
            if pid not in was:
                out.append((pid, name, team, gdate))
    return out


def _quiet(fn, *a, **k):
    """Run fn, capturing its stdout; a SystemExit (a BLIND input) is returned, not raised."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = fn(*a, **k)
        return res, buf.getvalue(), None
    except SystemExit as e:
        return None, buf.getvalue(), f"exit {e.code}"
    except Exception as e:                               # e.g. nba_rosters.Blind from cdn
        return None, buf.getvalue(), f"{type(e).__name__}: {str(e)[:80]}"


def once():
    import nba_flags as F
    import nba_lines as L
    import nba_rosters as R
    log = []
    with cycle_lock() as got:
        if not got:
            print(f"[{_now():%H:%M:%S}] watch: lock busy > {LOCK_WAIT_S}s — skipped")
            return 0
        con = sqlite3.connect(I.DB, timeout=60)
        con.executescript(I.DDL)
        con.execute(TRIG_DDL)
        # 1. REPORT — poll through the publication instant right after a mark
        now = _now()
        et = now.astimezone(I.ET)
        mark_t = et.replace(minute=(et.minute // 15) * 15, second=0, microsecond=0)
        mark_iso = mark_t.strftime("%Y-%m-%dT%H:%M")
        new = I.fetch_new(now, con)
        while (not con.execute("SELECT 1 FROM reports WHERE mark=?", (mark_iso,)).fetchone()
               and (_now().astimezone(I.ET) - mark_t).total_seconds() < REPORT_POLL_WINDOW_S):
            time.sleep(REPORT_POLL_S)
            new += I.fetch_new(_now(), con)
        for s in new:
            log.append(f"report {s['mark']}: {s['rows']} rows, {s['out']} Out"
                       + (f", unresolved {s['unresolved'][:3]}" if s["unresolved"] else "")
                       + (f" !! TEAMS MISSING {s['missing_teams']}" if s["missing_teams"] else ""))
        # 2. DIFF -> trigger
        sched = R.schedule()
        today = _now().astimezone(I.ET).date().isoformat()
        playing = {t for g in sched if g["date_et"] == today and g["status"] == 1
                   for t in (g["home"], g["away"])}
        for s in sorted(new, key=lambda s: s["mark"]):
            fr = [f for f in fresh_outs(con, s["mark"]) if f[3] == today and f[2] in playing]
            if not fr:
                continue
            pub = con.execute("SELECT published_at FROM reports WHERE mark=?",
                              (s["mark"],)).fetchone()[0]
            det = _now().isoformat()
            _, lout, lerr = _quiet(L.cycle)
            lines_at = _now().isoformat()
            fl, fout, ferr = _quiet(F.flags, dry=False)
            flags_at = _now().isoformat()
            names = [f"{n} ({t})" for _, n, t, _ in fr]
            con.execute("INSERT INTO triggers VALUES (?,?,?,?,?,?,?,?)",
                        (s["mark"], pub, det, json.dumps(names), lines_at, flags_at,
                         len(fl or []), "; ".join(x for x in (lerr, ferr) if x)))
            con.commit()
            log.append(f"TRIGGER {s['mark']} fresh Out {names} -> lines + flags "
                       f"({len(fl or [])} flag(s)); published {pub[11:19]} · flagged "
                       f"{flags_at[11:19]} UTC" + (f" · {lerr or ''} {ferr or ''}" if lerr or ferr else ""))
            for line in (fout or "").splitlines():
                if line.startswith(("  [NBA", "nba flags")):
                    log.append("   " + line.strip())
        # 3. CLOSE CAPTURE near tip
        soon = [g for g in sched if g["status"] == 1 and 0 <= (
            dt.datetime.fromisoformat(g["utc"].replace("Z", "+00:00")) - _now()
        ).total_seconds() / 60 <= HOT_LEAD_MIN]
        if soon:
            lc = sqlite3.connect(f"file:{L.DB}?mode=ro", uri=True)
            last = lc.execute("SELECT MAX(ts) FROM cycles").fetchone()[0]
            lc.close()
            age = ((_now().replace(tzinfo=None) - dt.datetime.fromisoformat(last))
                   .total_seconds() / 60) if last else 1e9
            if age >= HOT_EVERY_MIN:
                _, lout, lerr = _quiet(L.cycle)
                log.append(f"close capture: {len(soon)} game(s) tip within {HOT_LEAD_MIN} min -> "
                           f"lines refreshed" + (f" ({lerr})" if lerr else ""))
        con.close()
    for line in log:
        print(f"[{_now():%H:%M:%S}] {line}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", required=True)
    ap.parse_args()
    sys.exit(once())
