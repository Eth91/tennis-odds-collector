#!/usr/bin/env python3
"""DK freshness watchdog + self-heal.

WHY. Measured 2026-08-29 over 3 days: the FD-minus-DK lag is BIMODAL — median 3.4 min (fine), but
p75 85.6 min and p90 245.8 min. DK is inside the 10-min FRESH_MIN window only 61.2% of the time,
so its rungs are silently dropped from selection 38.8% of the time. Loosening FRESH_MIN does not
help (60 min only recovers 61.2% -> 72.5%) because the bad tail is at HOURS, not minutes. The
transport is what breaks, so the fix is to detect and re-pull, not to widen the gate.

DESIGN RULES this obeys, each learned the hard way here:
  * PROVE THE OUTCOME, NOT THE ATTEMPT. A heal only counts if the lag actually FALLS afterwards;
    "I ran a git fetch" is not evidence. Verified by re-measuring.
  * SAY WHICH BOX IS BROKEN. If origin's dk_board.json is itself stale, the Mac publisher is the
    fault and no amount of VM-side pulling can fix it — pulling harder would look like a fix and
    change nothing. The two causes get different messages.
  * NEVER PAGE ON READ CONTENTION. "database is locked" means the writer is ACTIVE. That is a
    SKIP, not a failure — a monitor that pages on its own contention trains you to ignore it.
  * REFUSE, DON'T GUESS. Unreadable input exits without healing rather than treating it as stale.
  * THROTTLED. One ping per PING_EVERY_H while unhealthy; the stamp clears on recovery.
"""
import datetime as dt
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = os.environ.get("FD_DB") or str(HERE / "wnba_lines.sqlite")
BOARD = HERE / "dk_board.json"
STAMP = Path.home() / ".dk_watchdog_pinged"
HEAL_ABOVE_MIN = 15.0        # FRESH_MIN is 10; heal a little past it, not at the boundary
STALE_ORIGIN_MIN = 25.0      # origin older than this ⇒ the Mac is the fault, not the VM
PING_EVERY_H = 3.0


def log(m):
    print(f"[{dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()}] {m}", flush=True)


def lag_minutes():
    """(newest FD) - (newest DK) in minutes, or None when the DB cannot be read.

    None means UNKNOWN and must never be treated as stale — that is the silent-zero trap."""
    for _ in range(4):
        try:
            c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=45)
            c.execute("PRAGMA busy_timeout=45000")
            row = c.execute(
                "SELECT MAX(CASE WHEN book='dk' THEN collected_at END), "
                "       MAX(CASE WHEN book!='dk' THEN collected_at END) "
                "FROM fd_lines WHERE sport='wnba' AND (live IS NULL OR live=0) "
                "AND collected_at > datetime('now','-12 hours')").fetchone()
            c.close()
            if not row or not row[1]:
                return None, None, None            # no FD either ⇒ off-hours, not a DK fault
            if not row[0]:
                return 9e9, None, row[1]           # FD live, DK entirely absent
            d = dt.datetime.fromisoformat(str(row[0]))
            f = dt.datetime.fromisoformat(str(row[1]))
            return (f - d).total_seconds() / 60.0, row[0], row[1]
        except sqlite3.OperationalError:
            time.sleep(3)
    return None, None, None


def origin_board_age():
    """Age in minutes of dk_board.json ON ORIGIN. Distinguishes a VM pull failure from a Mac
    publish failure — the whole point of this check."""
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=HERE, timeout=90,
                       capture_output=True)
        out = subprocess.run(["git", "show", "FETCH_HEAD:dk_board.json"], cwd=HERE,
                             timeout=60, capture_output=True, text=True)
        if out.returncode != 0:
            return None, None
        import json
        d = json.loads(out.stdout)
        ts = dt.datetime.fromisoformat(str(d["ts"]).replace("Z", "+00:00"))
        age = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 60.0
        return age, out.stdout
    except Exception as e:                                            # noqa: BLE001
        log(f"origin check failed: {str(e)[:70]}")
        return None, None


def board_status():
    """(status, age_min) from the Mac-published dk_board.json, or (None, None) if unreadable.

    UNKNOWN IS NOT HEALTHY and is also not a fault: boards published before 2026-08-31 carry no
    'status' key at all, so its absence must not page. It just means this backstop has nothing
    to say and the slate-based checks below still apply."""
    try:
        import json
        d = json.loads(BOARD.read_text())
        ts = dt.datetime.fromisoformat(str(d.get("ts", "")).replace("Z", "+00:00"))
        return d.get("status"), (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 60.0
    except Exception:                                                 # noqa: BLE001
        return None, None


def ping(msg):
    if STAMP.exists():
        age = (time.time() - STAMP.stat().st_mtime) / 3600.0
        if age < PING_EVERY_H:
            log(f"(throttled, last ping {age:.1f}h ago) {msg}")
            return
    topic = None
    for envf in (Path.home() / "wnba-loop.env", Path.home() / "tt-loop.env"):
        if envf.exists():
            for ln in envf.read_text().splitlines():
                if ln.startswith("NTFY_TOPIC"):
                    topic = ln.split("=", 1)[1].strip().strip('"').strip("'")
    if not topic:
        log(f"NO NTFY TOPIC — cannot page. {msg}")
        return
    try:
        import urllib.request
        req = urllib.request.Request(f"https://ntfy.sh/{topic}",
                                     data=msg.encode("utf-8", "replace"),
                                     headers={"Title": "WNBA DK stale".encode("latin-1", "replace").decode("latin-1")})
        urllib.request.urlopen(req, timeout=20).read()
        STAMP.write_text(dt.datetime.now(dt.timezone.utc).isoformat())
        log(f"PAGED: {msg}")
    except Exception as e:                                            # noqa: BLE001
        log(f"ping failed ({str(e)[:50]}) — NOT stamping, will retry")


def hours_to_next_tip():
    """Hours until the next tip, or None if no slate. DK only MATTERS in the run-up to a game.

    ⚠️ MEASURED 2026-08-29: DK sits inside FRESH_MIN 97.9% of the time in the 20:00-24:00 UTC
    selection window, but only ~45-49% overnight and midday — because dk_publish SKIPS on
    "quiet hours" by design. Judging DK outside the selection window conflates a design choice
    with a failure, and would page every single night. The first version of this file did exactly
    that on its first run.
    """
    try:
        sys.path.insert(0, str(HERE))
        import wnba_tonight as T
        tips = T.tip_times() or {}
        now = dt.datetime.now(dt.timezone.utc)
        fut = []
        for _t, when in tips.items():
            w = when if isinstance(when, dt.datetime) else dt.datetime.fromisoformat(str(when))
            if w.tzinfo is None:
                w = w.replace(tzinfo=dt.timezone.utc)
            fut.append((w - now).total_seconds() / 3600.0)
        upcoming = [h for h in fut if h > -0.25]
        return min(upcoming) if upcoming else None
    except Exception as e:                                            # noqa: BLE001
        log(f"tip_times unavailable ({str(e)[:50]}) — treating as NO SLATE, not as a fault")
        return None


WATCH_WITHIN_H = 8.0          # only judge DK inside the run-up to a tip


def main():
    # ENDPOINT HEALTH IS CHECKED BEFORE THE SLATE GATE, DELIBERATELY.
    #
    # A/B'd this file 2026-08-31 by injecting a hard block into main() at each slate state:
    #     ACTIVE slate (tip 2h out) + hard block -> PAGES        (the guard does work...)
    #     no slate                 + hard block -> SILENT        (...but only inside the window)
    #     next tip 408h out        + hard block -> SILENT
    #     ACTIVE slate + healthy DK             -> silent        (no false positive)
    # The two SILENT rows are the hole. Staleness is only observable when something fresh exists
    # to be stale against, so during an off-week a total DK outage looks exactly like a quiet
    # night. The WNBA went dark 2026-08-30 -> 2026-09-17: a block starting in that gap would have
    # gone unreported for 17 days and surfaced at the first tip, when DK-vs-FD line shopping is
    # worth +3.31pp of ROI. So a REFUSAL is judged on its own, never through its stale shadow.
    st, bage = board_status()
    if st in ("blocked", "error", "partial"):
        log(f"BOARD STATUS={st} (board {bage:.0f}min old) — endpoint fault, slate is irrelevant")
        ping(f"DK endpoint {st}: the Mac publisher reports DraftKings is refusing it. DK "
             f"collection is DOWN regardless of slate — best-price line shopping is degraded to "
             f"FanDuel-only until this clears.")
        return
    h = hours_to_next_tip()
    if h is None:
        # tip_times() returns {} for "no games today" AND for "ESPN did not answer" — it cannot
        # tell them apart, so this line must not claim the first. It no longer matters much: the
        # endpoint check above already ran, and it does not depend on knowing the slate.
        log(f"no slate visible (no games, or ESPN unavailable) — not judging staleness "
            f"[endpoint status={st or 'unknown'}]")
        return
    if h > WATCH_WITHIN_H:
        log(f"next tip {h:.1f}h away (> {WATCH_WITHIN_H}h) — outside the selection window; not judging")
        return
    log(f"next tip {h:.1f}h away — inside the window, checking DK")
    before, dk_ts, fd_ts = lag_minutes()
    if before is None:
        log("DB unreadable or no FD data in 12h — REFUSING to act (unknown != stale)")
        return
    if before <= HEAL_ABOVE_MIN:
        if STAMP.exists():
            STAMP.unlink(missing_ok=True)
            log(f"recovered: lag {before:.1f} min — ping stamp cleared")
        log(f"ok: DK lag {before:.1f} min (heal above {HEAL_ABOVE_MIN})")
        return

    log(f"DK lag {before:.1f} min > {HEAL_ABOVE_MIN} — investigating")
    oage, blob = origin_board_age()
    if oage is None:
        log("could not read dk_board.json from origin — cannot distinguish cause; not healing")
        ping(f"DK lag {before:.0f}min and origin unreadable — check the VM's git access.")
        return
    if oage > STALE_ORIGIN_MIN:
        # Pulling harder cannot help: the data is not on origin yet.
        ping(f"DK stale {before:.0f}min AND origin board is {oage:.0f}min old — the MAC publisher "
             f"is the fault (com.pickz.dkpublish), not the VM. Pulling will not fix it.")
        log(f"origin board is {oage:.1f} min old — Mac-side fault, no heal attempted")
        return

    log(f"origin board is fresh ({oage:.1f} min) — VM failed to pull it. Healing.")
    try:
        if blob:
            BOARD.write_text(blob)
        r = subprocess.run([sys.executable, "dk_ingest.py"], cwd=HERE, timeout=240,
                           capture_output=True, text=True)
        log(f"dk_ingest: {(r.stdout or r.stderr).strip()[:120]}")
    except Exception as e:                                            # noqa: BLE001
        log(f"heal failed: {str(e)[:80]}")

    after, _, _ = lag_minutes()
    if after is None:
        log("post-heal read failed — outcome UNVERIFIED, not claiming success")
        return
    if after < before - 1:
        log(f"HEALED: lag {before:.1f} -> {after:.1f} min")
        STAMP.unlink(missing_ok=True)
    else:
        log(f"heal did NOT work: lag {before:.1f} -> {after:.1f} min")
        ping(f"DK stale {after:.0f}min. Origin board was fresh ({oage:.0f}min) but re-pull + "
             f"ingest did NOT reduce the lag. Look at dk_ingest.py on the VM.")


if __name__ == "__main__":
    main()
