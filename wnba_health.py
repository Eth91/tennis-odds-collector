#!/usr/bin/env python3
"""DATA-SOURCE HEALTH CHECK — assert every live input is present AND COMPLETE.

WHY THIS EXISTS (2026-08-13). Three separate silent failures in one day, all of which looked
healthy from the outside:
  * fd_collect died every cycle on "database is locked" with errors sent to /dev/null
  * git push failed for 8 days with `2>/dev/null` swallowing the reason
  * box_actuals PARTIALLY parsed a date, and the missing players read as DNPs — which voided
    two real LOSSES out of the record

The common shape is not "it threw an exception". It is "it returned something, and something
looked like data". So every check here asserts a MAGNITUDE, not truthiness: `players()`
returning 3 is a failure even though 3 is truthy, and a box score covering 2 of 4 games is a
failure even though it parsed.

⚠️ QUIET IS NOT BROKEN. A source with nothing to say on an off-day must not page. Checks that
depend on a slate resolve whether games exist first and report SKIP, never FAIL, when they do
not. A health check that cries wolf at 6am gets ignored by the time it matters.

Exit 0 = all green (or green + skips). Exit 1 = at least one FAIL.
Usage:  python3 wnba_health.py [--quiet] [--ping]
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ET = dt.timezone(dt.timedelta(hours=-4))
results: list[tuple[str, str, str]] = []      # (name, OK|FAIL|SKIP, detail)


import contextlib
import io


def check(name):
    """Run one probe, capturing whatever the imported module prints.

    ⚠️ THE CHECKS MUST BE SILENT WHEN GREEN. injuries() and friends print progress lines
    ("RotoWire OK: 6 lineups..."), which under `--quiet >> health.log` would append noise on
    every run -- and then "empty log means all green" stops being true, which is the entire
    operational contract of this file. Captured output is discarded on OK and surfaced only
    when a check FAILS, where it is diagnostic rather than clutter.
    """
    def deco(fn):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                state, detail = fn()
        except Exception as e:                                       # noqa: BLE001
            state, detail = "FAIL", f"raised {type(e).__name__}: {str(e)[:70]}"
        if state == "FAIL":
            noise = " ".join(buf.getvalue().split())[:120]
            if noise:
                detail = f"{detail}  [stdout: {noise}]"
        results.append((name, state, detail))
        return fn
    return deco


def _slate_date():
    """Today's ET slate date — the WNBA day rolls at ET midnight, not UTC."""
    return dt.datetime.now(ET).date().isoformat()


# ── roster / player universe ──────────────────────────────────────────────────
@check("espn.players")
def _players():
    import wnba_wowy as W
    pl = W.players()
    n = len(pl)
    # a real WNBA roster universe is ~180-220. Anything under 120 means a partial parse,
    # which is exactly the failure mode that must not pass as "truthy".
    return ("OK" if n >= 120 else "FAIL"), f"{n} players (expect >=120)"


@check("espn.game_log")
def _gamelog():
    import wnba_wowy as W
    pl = W.players()
    # pick the highest-minute player: if anyone has a log, she does
    top = max(pl.items(), key=lambda kv: kv[1].get("min", 0))
    lg = W.game_log(top[1]["id"])
    return ("OK" if len(lg) >= 5 else "FAIL"), f"{top[0]}: {len(lg)} games (expect >=5)"


# ── box scores: the source that caused the phantom voids ──────────────────────
@check("espn.box_actuals")
def _box():
    import wnba_ledger as L
    # look back for the most recent date that actually had games
    for back in range(1, 8):
        d = (dt.datetime.now(ET).date() - dt.timedelta(days=back)).isoformat()
        b = L.box_actuals(d)
        if b:
            ok = L.box_complete(d)
            n = len(b)
            if not ok:
                return "FAIL", f"{d}: INCOMPLETE parse ({n} players) -- DNP voids unsafe"
            return ("OK" if n >= 40 else "FAIL"), f"{d}: {n} players, complete"
    return "SKIP", "no games in the last 7 days"


# ── betting lines ─────────────────────────────────────────────────────────────
@check("fanduel.fd_lines")
def _fd():
    """⚠️ 'database is locked' IS NOT A DATA-SOURCE FAILURE — it is the opposite.

    fd_collect writes this DB continuously; a lock means the writer is ACTIVE, which is
    evidence the collector is healthy. The first version of this probe made one attempt and
    reported the exception as "WNBA data source FAILING", paging every 30 minutes while
    fd_lines held 656k fresh quotes and the newest was 36 seconds old. A monitor that pages on
    its own read contention is worse than no monitor: it trains you to ignore it.

    So: retry patiently, and if it is STILL locked, decide by the file's own mtime. Recently
    written == the writer is busy == SKIP. Only a DB that is both unreadable AND untouched is
    a real failure.
    """
    import time as _t
    db = os.environ.get("FD_DB") or str(HERE / "wnba_lines.sqlite")
    if not Path(db).exists():
        return "FAIL", f"{Path(db).name} missing"
    row, lasterr = None, None
    for _try in range(4):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=45)
            con.execute("PRAGMA busy_timeout=45000")
            row = con.execute(
                "SELECT MAX(collected_at), COUNT(*) FROM fd_lines "
                "WHERE sport='wnba' AND collected_at > datetime('now','-2 hours')").fetchone()
            con.close()
            break
        except sqlite3.OperationalError as e:
            lasterr = e
            _t.sleep(3)
    if row is None:
        mtime_age = (dt.datetime.now().timestamp() - Path(db).stat().st_mtime) / 60
        if mtime_age <= 10:
            return "SKIP", (f"locked after 4 tries, but the DB was written "
                            f"{mtime_age:.1f} min ago -- the collector is ACTIVE")
        return "FAIL", f"unreadable AND untouched for {mtime_age:.0f} min: {str(lasterr)[:40]}"
    newest, n = row[0], row[1]
    if not newest:
        return "SKIP", "no wnba quotes in 2h (off-hours or no slate)"
    age = (dt.datetime.utcnow() - dt.datetime.fromisoformat(newest)).total_seconds() / 60
    # the collector runs every cycle; >25 min stale means it is failing silently again
    return ("OK" if age <= 25 else "FAIL"), f"{n:,} quotes/2h, newest {age:.0f} min old (expect <=25)"


# ── injury feed ───────────────────────────────────────────────────────────────
@check("injuries.feed")
def _inj():
    import wnba_tonight as T
    inj = T.injuries()
    outs = sum(1 for v in inj.values() if "out" in str(v).lower())
    if not inj:
        return "FAIL", "injuries() returned EMPTY -- the whole beneficiary engine goes dark"
    return "OK", f"{len(inj)} entries, {outs} Out"


# ── slate metadata ────────────────────────────────────────────────────────────
@check("espn.tip_times")
def _tips():
    import wnba_tonight as T
    t = T.tip_times()
    if not t:
        return "SKIP", "no games today"
    return "OK", f"{len(t)} teams with tip times"


# ── the board actually publishing ─────────────────────────────────────────────
@check("board.published")
def _board():
    p = HERE / "docs" / "index.html"
    if not p.exists():
        return "FAIL", "docs/index.html missing"
    age = (dt.datetime.now().timestamp() - p.stat().st_mtime) / 60
    size = p.stat().st_size
    if size < 50_000:
        return "FAIL", f"index.html only {size:,} bytes -- truncated build"
    return ("OK" if age <= 45 else "FAIL"), f"{size//1024}KB, {age:.0f} min old (expect <=45)"


# ── the ledger itself ─────────────────────────────────────────────────────────
@check("ledger.grading")
def _ledger():
    p = HERE / "wnba_ledger.sqlite"
    if not p.exists():
        return "FAIL", "wnba_ledger.sqlite missing"
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=20)
    stale = con.execute(
        "SELECT COUNT(*) FROM predictions WHERE result IS NULL "
        "AND pred_date < date('now','-2 days')").fetchone()[0]
    con.close()
    # a row still ungraded 2+ days after its slate means the grader is stuck on it
    return ("OK" if stale == 0 else "FAIL"), f"{stale} rows ungraded >2 days after their slate"


def main():
    quiet = "--quiet" in sys.argv
    fails = [r for r in results if r[1] == "FAIL"]
    if not quiet or fails:
        stamp = dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
        print(f"WNBA data-source health  [{stamp}]")
        for name, state, detail in results:
            mark = {"OK": "  ok  ", "FAIL": " FAIL ", "SKIP": " skip "}[state]
            print(f" [{mark}] {name:22s} {detail}")
    if fails and "--ping" in sys.argv:
        # ⚠️ THROTTLE. Cron runs this every 30 min; without state, one stuck probe pages twice
        # an hour forever and the alert becomes wallpaper. Re-page only when the SET of failing
        # probes changes, or after 6h of the same failure as a reminder.
        sig = "|".join(sorted(n for n, _s, _d in fails))
        statef = Path.home() / ".wnba_health_pinged"
        prev_sig, prev_ts = "", 0.0
        try:
            prev_sig, _, prev_raw = statef.read_text().partition("\n")
            prev_ts = float(prev_raw.strip() or 0)
        except Exception:                                            # noqa: BLE001
            pass
        now_ts = dt.datetime.now().timestamp()
        fresh = sig != prev_sig or (now_ts - prev_ts) > 6 * 3600
        if not fresh:
            print(f"  (ping suppressed: same failure set as {(now_ts-prev_ts)/60:.0f} min ago)")
        topic = os.environ.get("NTFY_TOPIC") if fresh else None
        if fresh:
            try:
                statef.write_text(f"{sig}\n{now_ts}")
            except Exception:                                        # noqa: BLE001
                pass
        if topic:
            body = "; ".join(f"{n}: {d}" for n, _s, d in fails)[:400]
            try:
                req = urllib.request.Request(
                    f"https://ntfy.sh/{topic}", data=body.encode(),
                    headers={"Title": "WNBA data source FAILING",   # ascii only: latin-1 header
                             "Priority": "high", "Tags": "warning"})
                urllib.request.urlopen(req, timeout=15).read()
            except Exception as e:                                   # noqa: BLE001
                print(f"  (ntfy failed: {str(e)[:50]})")
    if not fails:
        # recovered: forget the last-pinged set so the NEXT failure pages immediately
        try:
            (Path.home() / ".wnba_health_pinged").unlink(missing_ok=True)
        except Exception:                                            # noqa: BLE001
            pass
    if fails:
        with open(Path.home() / "loop_fail.log", "a") as fh:
            fh.write(f"health {dt.datetime.now(dt.timezone.utc).isoformat()} "
                     + "; ".join(f"{n}={d}" for n, _s, d in fails) + "\n")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
