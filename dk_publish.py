"""Mac-side DraftKings publisher — the residential-IP half of the two-book pipeline.

DraftKings Akamai-blocks datacenter IPs (Oracle VM 403s every request; Actions is flaky),
but collection works perfectly from the Mac. This script runs on a launchd timer (~5 min):

  1. dk_collect --wnba  -> fresh book='dk' rows in the LOCAL fanduel_props.sqlite
  2. snapshot the current DK WNBA board -> dk_board.json (small, Mac-OWNED file)
  3. commit+push ONLY dk_board.json when its content changed (hash guard, autostash
     rebase + retry so it never fights the VM's data commits)

The VM ingests dk_board.json each loop cycle (dk_ingest.py) into its own wnba_lines.sqlite,
which lights up every existing consumer unchanged: card book-logos/best-price
(dashboard._book_prices), posted_props' book-aware quotes, and CLV's alt-book column.
Flag/record odds remain FanDuel's (the executable book); DK is price context + the
reprice-race second target.

    python3 dk_publish.py            # one publish pass
    python3 dk_publish.py --loop     # for testing; production uses launchd StartInterval
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE / "dk_board.json"
QUIET_START, QUIET_END = 1, 6          # local hours with no games/lines worth publishing
NTFY_TOPIC = "ttelite-bets-f2002ae9"
HEALTH_STAMP = Path.home() / ".dk_publish_health_ping"
PING_EVERY_H = 3.0
BAD = ("blocked", "error", "partial")  # statuses that mean the ENDPOINT is at fault


def _ntfy(title, msg, tags="warning"):
    """Fire-and-forget phone ping. Headers must be latin-1 clean or urllib raises."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://ntfy.sh/" + NTFY_TOPIC, data=msg.encode("utf-8", "replace"),
            headers={"Title": title.encode("latin-1", "replace").decode("latin-1"), "Tags": tags})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:                                                 # noqa: BLE001
        return False


def alert_if_bad(status):
    """Page on an endpoint REFUSAL, unconditionally — no slate gate, no quiet-hours gate.

    WHY THIS EXISTS (2026-08-31). DK staleness was judged only by dk_watchdog.py on the VM, and
    only inside an 8h pre-tip window. A/B'd that guard: with a hard block injected it pages when a
    tip is 2h away, and stays SILENT when there is no slate or the next tip is >8h out. The WNBA
    then went dark from 2026-08-30 until the 2026-09-17 restart, so a block starting in that gap
    would have gone unreported for 17 days and surfaced at the first tip — precisely when DK-vs-FD
    line shopping is worth +3.31pp of ROI. Staleness is not observable during an off-week; a 403
    is. So alert on the REFUSAL, not on its downstream shadow.

    'no_markets' is explicitly NOT a fault: DK simply has not posted player props yet.
    """
    if status not in BAD:
        if HEALTH_STAMP.exists():
            HEALTH_STAMP.unlink(missing_ok=True)
            print(f"health recovered (status={status}) — ping stamp cleared")
        return
    if HEALTH_STAMP.exists():
        age_h = (time.time() - HEALTH_STAMP.stat().st_mtime) / 3600.0
        if age_h < PING_EVERY_H:
            print(f"DK status={status} (throttled, last ping {age_h:.1f}h ago)")
            return
    msg = {"blocked": "DraftKings is REFUSING this Mac (HTTP 403 - Akamai). DK collection is "
                      "down; line shopping degrades to FanDuel-only. The Oracle VM is blocked by "
                      "design, so this Mac is the only DK source.",
           "partial": "DraftKings root is up but subcategory fetches are failing - the DK board "
                      "is incomplete.",
           "error":   "DraftKings endpoint unreachable (timeout/DNS/5xx). DK collection is down."}[status]
    if _ntfy(f"DK endpoint {status}", msg):
        HEALTH_STAMP.write_text(dt.datetime.utcnow().isoformat())
        print(f"PAGED: DK status={status}")
    else:
        print(f"DK status={status} but ping FAILED — not stamping, will retry")


def _status_from(out):
    """Last 'DKSTATUS wnba=<status>' dk_collect printed, or 'error' if it printed none."""
    m = re.findall(r"DKSTATUS\s+wnba=(\w+)", out)
    return m[-1] if m else "error"


def collect():
    r = subprocess.run([sys.executable, str(HERE / "dk_collect.py"), "--wnba"],
                       capture_output=True, text=True, timeout=240, cwd=HERE)
    ok = r.returncode == 0
    out = r.stdout + r.stderr
    print(("dk_collect ok: " if ok else "dk_collect FAILED: ") + out.strip()[-120:])
    return ok, _status_from(out)


def probe_status():
    """Cheap one-GET health check for cycles that skip the full collect."""
    try:
        r = subprocess.run([sys.executable, str(HERE / "dk_collect.py"), "--wnba", "--probe"],
                           capture_output=True, text=True, timeout=90, cwd=HERE)
        return _status_from(r.stdout + r.stderr)
    except Exception:                                                 # noqa: BLE001
        return "error"


def snapshot():
    """Freshest DK quote per (event, player, stat, line, side) from the last 15 min."""
    con = sqlite3.connect(HERE / "fanduel_props.sqlite")
    con.row_factory = sqlite3.Row
    cut = (dt.datetime.utcnow() - dt.timedelta(minutes=15)).isoformat()[:19]
    rows = con.execute(
        "SELECT event, player, stat, line, side, odds, MAX(collected_at) ca FROM fd_lines "
        "WHERE book='dk' AND sport='wnba' AND collected_at > ? "
        "GROUP BY event, player, stat, line, side", (cut,)).fetchall()
    con.close()
    return [{"event": r["event"], "player": r["player"], "stat": r["stat"],
             "line": r["line"], "side": r["side"], "odds": r["odds"]} for r in rows]


def publish(lines, status="ok"):
    body = {"ts": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "sport": "wnba", "book": "dk", "lines": sorted(
                lines, key=lambda x: (x["player"], x["stat"], x["line"], x["side"]))}
    payload = json.dumps({k: body[k] for k in ("sport", "book", "lines")}, sort_keys=True)
    digest = hashlib.sha1(payload.encode()).hexdigest()
    # HASH STAYS CONTENT-ONLY. dk_ingest.py stores it in .dk_ingest_state to skip re-ingesting the
    # same board; folding status into it would force spurious re-ingests. Status is a SEPARATE
    # commit trigger instead, so a health flip still reaches the VM while the board is unchanged.
    old = old_status = ""
    if BOARD.exists():
        try:
            d = json.loads(BOARD.read_text())
            old, old_status = d.get("hash", ""), d.get("status", "")
        except (ValueError, OSError):
            pass
    if digest == old and status == old_status:
        print(f"no change ({len(lines)} lines, status={status}) — skip commit")
        return
    body["hash"] = digest
    body["status"] = status
    # SYNC-THEN-WRITE (2026-07-29). The old flow committed locally first and then tried
    # `pull --rebase -X ours` — once this clone drifted (it reached 2,172 commits behind),
    # every rebase blew its 90s timeout and the push failed SILENTLY every 5 minutes for
    # 3 days while the VM read a stale board. This clone only ever authors dk_board.json,
    # so the right move is: adopt origin's tip wholesale, THEN write the board on top.
    # A local commit that never leaves this Mac has negative value — don't create one.
    for attempt in range(4):
        try:
            subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=HERE, check=True, timeout=60)
            subprocess.run(["git", "reset", "--hard", "FETCH_HEAD", "-q"], cwd=HERE, check=True, timeout=60)
            BOARD.write_text(json.dumps(body))
            subprocess.run(["git", "add", "dk_board.json"], cwd=HERE, check=True, timeout=30)
            subprocess.run(["git", "commit", "-q", "-m", "dk board [skip ci]"],
                           cwd=HERE, check=False, timeout=30)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=HERE, check=True, timeout=90)
            print(f"published {len(lines)} DK lines")
            return
        except subprocess.CalledProcessError:
            continue                       # lost a race with the VM's push — refetch and retry
    # Total failure is worth a phone ping: this exact path failed silently for 3 days once.
    BOARD.write_text(json.dumps(body))     # keep the local copy current even when unpublished
    print("PUSH FAILED 4x — DK board NOT published; VM will degrade to FanDuel-only")
    try:
        import urllib.request
        topic = "ttelite-bets-f2002ae9"
        req = urllib.request.Request("https://ntfy.sh/" + topic,
                                     data=b"dk_publish: 4 push attempts failed - DK board is not reaching the VM. Best-price line shopping is degraded to FanDuel-only until this is fixed.",
                                     headers={"Title": "DK board push failing", "Tags": "warning"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def main():
    h = dt.datetime.now().hour
    if QUIET_START <= h < QUIET_END:
        # Quiet hours skip the COLLECT, never the health check — a block starting at 02:00 used
        # to stay invisible until 06:00, on top of the VM watchdog's slate gate.
        status = probe_status()
        alert_if_bad(status)
        print(f"quiet hours ({h}h) — status={status}, skip collect")
        return
    ok, status = collect()
    alert_if_bad(status)
    if ok:
        publish(snapshot(), status)


if __name__ == "__main__":
    main()
