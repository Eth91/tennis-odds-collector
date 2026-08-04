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
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE / "dk_board.json"
QUIET_START, QUIET_END = 1, 6          # local hours with no games/lines worth publishing


def collect():
    r = subprocess.run([sys.executable, str(HERE / "dk_collect.py"), "--wnba"],
                       capture_output=True, text=True, timeout=240, cwd=HERE)
    ok = r.returncode == 0
    print(("dk_collect ok: " if ok else "dk_collect FAILED: ") + (r.stdout + r.stderr).strip()[-120:])
    return ok


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


def publish(lines):
    body = {"ts": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "sport": "wnba", "book": "dk", "lines": sorted(
                lines, key=lambda x: (x["player"], x["stat"], x["line"], x["side"]))}
    payload = json.dumps({k: body[k] for k in ("sport", "book", "lines")}, sort_keys=True)
    digest = hashlib.sha1(payload.encode()).hexdigest()
    old = ""
    if BOARD.exists():
        try:
            old = json.loads(BOARD.read_text()).get("hash", "")
        except (ValueError, OSError):
            pass
    if digest == old:
        print(f"no change ({len(lines)} lines) — skip commit")
        return
    body["hash"] = digest
    # DIRECT TO THE VM (2026-08-04). GitHub account gone, user off Actions for
    # good -- the git hop is deleted, not routed around. The VM's dk_ingest.py
    # reads ~/tennis-odds-collector/dk_board.json each loop cycle; deliver it
    # there atomically (tmp+mv) exactly like worker-2 delivers tt_board.json.
    # The 4-attempt + phone-ping shape is KEPT: this path once failed silently
    # for 3 days, and a silent DK outage degrades line-shopping to FD-only.
    BOARD.write_text(json.dumps(body))     # local copy always current
    VM = "ubuntu@155.248.217.149"
    DEST = "/home/ubuntu/tennis-odds-collector"
    KEY = str(Path.home() / ".ssh" / "oracle_vm")
    for attempt in range(4):
        try:
            subprocess.run(["scp", "-q", "-i", KEY, "-o", "BatchMode=yes",
                            "-o", "ConnectTimeout=20", str(BOARD),
                            f"{VM}:{DEST}/dk_board.json.tmp"], check=True, timeout=60)
            subprocess.run(["ssh", "-i", KEY, "-o", "BatchMode=yes",
                            "-o", "ConnectTimeout=20", VM,
                            f"mv {DEST}/dk_board.json.tmp {DEST}/dk_board.json"],
                           check=True, timeout=60)
            print(f"published {len(lines)} DK lines -> VM (direct scp)")
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    print("SCP FAILED 4x — DK board NOT published; VM will degrade to FanDuel-only")
    try:
        import urllib.request
        topic = "ttelite-bets-f2002ae9"
        req = urllib.request.Request("https://ntfy.sh/" + topic,
                                     data=b"dk_publish: 4 scp attempts failed - DK board is not reaching the VM. Line shopping degraded to FanDuel-only until fixed.",
                                     headers={"Title": "DK board delivery failing", "Tags": "warning"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def main():
    h = dt.datetime.now().hour
    if QUIET_START <= h < QUIET_END:
        print(f"quiet hours ({h}h) — skip")
        return
    if collect():
        publish(snapshot())


if __name__ == "__main__":
    main()
