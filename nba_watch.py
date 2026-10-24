#!/usr/bin/env python3
"""NBA speed layer — act on the official injury report the moment it publishes. MAC-ONLY.

The WNBA's money is partly SPEED: its bets beat the closing line 67% of the time, and the same
bets bought at the close earned about half as much (+11.5% vs +20.2%). The NBA analogue of its
`wnba_watch` is this: poll cheap, act only on change.

Run once a minute (cron). Each run:
  1. REPORT. The league publishes a game-dated PDF ~4 s after every :00/:15/:30/:45 mark. In the
     first minute after a mark this polls until the new report exists (HEAD every 3 s), then
     ingests it (nba_injury_report.fetch_new). Otherwise one cheap HEAD catches up.
  2. DIFF. A FRESH Out = a player listed Out for a game in the new report who was not Out for
     that game in the previous stored report. Games TONIGHT and TOMORROW both count — the league
     publishes tomorrow's rulings the afternoon before, and that is news the book has to price
     too (NBA_SPEED_PREREG.md, amendment 1; flags carry horizon 0/1 and are scored apart). If a
     fresh Out's team plays that day (not started): refresh both books NOW (nba_lines.cycle),
     then run the flag pass for each affected game date — so each shadow flag's price is the
     price right after the news.
     Every trigger is logged in nba_news.sqlite `triggers` with its timings.
  2b. NEWS (amendment 2). At most every NEWS_EVERY_S, poll the news layer (nba_news_watch). A news
     Out for a game tonight/tomorrow that the official report does NOT already list as Out fires
     the same action — lines + flag pass — before the report catches up. Add-only.
  3. CLOSE CAPTURE. Within HOT_LEAD_MIN of any tip, refresh lines every HOT_EVERY_MIN, so the
     closing price nba_clv rebuilds is minutes old, not up to ten.
  4. REACTION FOLLOW (amendment 5). For FOLLOW_MIN after any trigger, refresh FanDuel every minute,
     so the change log times the book's reaction to the news at ~1-minute resolution
     (nba_reaction.py). Data only: flags and the speed test's yardstick are untouched.

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
NEWS_EVERY_S = 55                                     # same self-throttle the WNBA news layer uses
FOLLOW_MIN = 20                                       # amendment 5: per-minute FanDuel after a trigger
NEWS_STAMP = Path("/tmp/nba-news.last")
TRIG_DDL = """CREATE TABLE IF NOT EXISTS triggers (
    mark TEXT, published_at TEXT, detected_at TEXT, fresh TEXT, lines_at TEXT,
    flags_at TEXT, n_flags INTEGER, note TEXT)"""


def _now():
    return dt.datetime.now(dt.timezone.utc)


def follow_due(con, now):
    """True while a trigger fired less than FOLLOW_MIN ago (amendment 5)."""
    last = con.execute("SELECT MAX(detected_at) FROM triggers").fetchone()[0]
    if not last:
        return False
    t = dt.datetime.fromisoformat(last)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return 0 <= (now - t).total_seconds() / 60 < FOLLOW_MIN


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


def trigger_gids(fresh):
    """The not-started games of the fresh Outs: {gid} for each (team, ET date)."""
    import nba_rosters as R
    try:
        sched = R.schedule()
    except Exception:                                        # noqa: BLE001 — caller falls back
        return set()
    want = {(t, gd) for _pid, _nm, t, gd in fresh}
    return {g["gid"] for g in sched if g["status"] == 1
            and ((g["home"], g["date_et"]) in want or (g["away"], g["date_et"]) in want)}


def _fire(con, label, published, fresh, log):
    """The trigger action: refresh both books once, then a flag pass per affected game date.
    fresh: [(pid, name, team, game_date)]."""
    import nba_flags as F
    import nba_lines as L
    det = _now().isoformat()
    # PER-GAME REFRESH (amendment 12): only the games of the fresh Outs (~2 s, not the ~12 s board).
    # Any failure falls back to the full refresh, so a trigger is never priced off a stale board.
    gids = trigger_gids(fresh)
    res, lout, lerr = _quiet(L.cycle, None, only_gids=gids) if gids else (None, "", "no game found")
    if lerr or (res and "fd" in res):                    # raised, or FanDuel's fetch failed inside
        _, lout, lerr = _quiet(L.cycle)
    lines_at = _now().isoformat()
    fl, fout, ferr = [], "", None
    for gd in sorted({f[3] for f in fresh}):
        r, o, e = _quiet(F.flags, dry=False, game_date=gd)
        fl += r or []
        fout += o
        ferr = ferr or e
    flags_at = _now().isoformat()
    names = [f"{n} ({t}, {gd})" for _, n, t, gd in fresh]
    con.execute("INSERT INTO triggers VALUES (?,?,?,?,?,?,?,?)",
                (label, published, det, json.dumps(names), lines_at, flags_at, len(fl),
                 "; ".join(x for x in (lerr, ferr) if x)))
    con.commit()
    log.append(f"TRIGGER {label} fresh Out {names} -> lines + flags ({len(fl)} flag(s)); "
               f"published {published[11:19]} · flagged {flags_at[11:19]} UTC"
               + (f" · {lerr or ''} {ferr or ''}" if lerr or ferr else ""))
    for line in (fout or "").splitlines():
        if line.startswith(("  [NBA", "nba flags")):
            log.append("   " + line.strip())


def news_step(con, playing, log, sources=None):
    """Poll the news layer (all sources, or `sources`) and fire on each Out the official report does
    not list yet. Returns True if anything fired (the books were refreshed)."""
    import nba_news_watch as NW
    outs, errs = NW.poll(_now(), con=con, sources=sources)
    for e in errs:
        log.append(f"news source error: {e}")
    by_src = {}
    for src, pid, nm, tri, gd, at in outs:
        if (gd, tri) not in playing:
            continue
        cur, _ = I.current(gd, con)
        if (cur.get(pid) or (None, None, None))[2] == "Out":
            continue                                      # the report already has it
        by_src.setdefault((src, at), []).append((pid, nm, tri, gd))
    for (src, at), fr in by_src.items():
        _fire(con, f"news:{src}", at, fr, log)
    return bool(by_src)


def playing_now():
    """{(ET date, team)} for teams with a not-started game today or tomorrow."""
    import nba_flags as F
    import nba_rosters as R
    sched = R.schedule()
    d0 = _now().astimezone(I.ET).date()
    dates = {(d0 + dt.timedelta(days=h)).isoformat() for h in range(F.HORIZONS)}
    return sched, {(g["date_et"], t) for g in sched if g["date_et"] in dates and g["status"] == 1
                   for t in (g["home"], g["away"])}


def x_fast(interval=2.0):
    """FAST X PATH (user 2026-10-24: "0 latency"): a daemon that watches the X log the two X watchers
    write (@UnderdogNBA + 62 beat writers). The moment it grows, it takes the cycle lock and runs the
    news step for the X source only: fire -> lines -> flags -> ping. The minute cron + 55 s news
    throttle had cost 59 s on Cooper Flagg (2026-10-24). RotoWire/bsky stay on the throttled path."""
    path = Path(os.environ.get("NBA_X_LOG", ""))
    size = path.stat().st_size if path.is_file() else 0
    print(f"x_fast: watching {path} every {interval}s", flush=True)
    while True:
        try:
            now_size = path.stat().st_size if path.is_file() else 0
            if now_size != size:
                size = now_size
                log = []
                with cycle_lock() as got:
                    if got:
                        con = sqlite3.connect(I.DB, timeout=60)
                        con.executescript(I.DDL)
                        con.execute(TRIG_DDL)
                        _sched, playing = playing_now()
                        news_step(con, playing, log, sources=["x"])
                        con.close()
                    else:
                        log.append("lock busy — the next growth or the minute run will catch it")
                for line in log:
                    print(f"[{_now():%H:%M:%S}] x_fast {line}", flush=True)
        except Exception as e:                                       # noqa: BLE001
            print(f"[{_now():%H:%M:%S}] x_fast error: {type(e).__name__}: {e}", flush=True)
        time.sleep(interval)


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
                       # a team with nobody to list is OMITTED from the PDF (MIL 2026-10-23) —
                       # that alone is not a fault; misattributed players would be UNRESOLVED
                       + (f" !! TEAMS MISSING {s['missing_teams']} WITH unresolved rows in the same "
                          f"matchup — possible misattribution" if s["missing_teams"] else ""))
        # 2. DIFF -> trigger
        sched = R.schedule()
        d0 = _now().astimezone(I.ET).date()
        dates = {(d0 + dt.timedelta(days=h)).isoformat() for h in range(F.HORIZONS)}
        playing = {(g["date_et"], t) for g in sched if g["date_et"] in dates and g["status"] == 1
                   for t in (g["home"], g["away"])}
        refreshed = False                                 # did this run already fetch FanDuel?
        for s in sorted(new, key=lambda s: s["mark"]):
            fr = [f for f in fresh_outs(con, s["mark"]) if (f[3], f[2]) in playing]
            if fr:
                pub = con.execute("SELECT published_at FROM reports WHERE mark=?",
                                  (s["mark"],)).fetchone()[0]
                _fire(con, s["mark"], pub, fr, log)
                refreshed = True
        if new:
            F.void_pass()                      # a new report can retract a pinged play: VOID now
        # 2b. NEWS — throttled; fires only on an Out the official report does not list yet
        try:
            last = NEWS_STAMP.stat().st_mtime
        except FileNotFoundError:
            last = 0
        if time.time() - last >= NEWS_EVERY_S:
            NEWS_STAMP.touch()
            refreshed = news_step(con, playing, log) or refreshed
        # 3. CLOSE CAPTURE near tip
        soon = [g for g in sched if g["status"] == 1 and 0 <= (
            dt.datetime.fromisoformat(g["utc"].replace("Z", "+00:00")) - _now()
        ).total_seconds() / 60 <= HOT_LEAD_MIN]
        if soon:
            lc = sqlite3.connect(f"file:{L.DB}?mode=ro", uri=True)
            # FanDuel's own last fetch: since amendment 4 a DraftKings snapshot row carries ITS
            # fetch time, so the newest row of any book no longer says when FanDuel was polled
            last = lc.execute("SELECT MAX(ts) FROM cycles WHERE book='fd' AND status != 'game'"
                              ).fetchone()[0]                # a per-game refresh is not a full one
            lc.close()
            age = ((_now().replace(tzinfo=None) - dt.datetime.fromisoformat(last))
                   .total_seconds() / 60) if last else 1e9
            if age >= HOT_EVERY_MIN:
                _, lout, lerr = _quiet(L.cycle)
                log.append(f"close capture: {len(soon)} game(s) tip within {HOT_LEAD_MIN} min -> "
                           f"lines refreshed" + (f" ({lerr})" if lerr else ""))
                refreshed = True
        # 4. REACTION FOLLOW — per-minute FanDuel for FOLLOW_MIN after a trigger (amendment 5)
        if not refreshed and follow_due(con, _now()):
            _, lout, lerr = _quiet(L.cycle, ("fd",))
            log.append("reaction follow: FanDuel refreshed" + (f" ({lerr})" if lerr else ""))
        con.close()
    for line in log:
        print(f"[{_now():%H:%M:%S}] {line}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--x-fast", action="store_true", help="daemon: fire the moment the X log grows")
    a = ap.parse_args()
    if a.x_fast:
        x_fast()
    elif a.once:
        sys.exit(once())
    else:
        ap.error("--once or --x-fast")
