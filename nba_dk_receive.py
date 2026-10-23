#!/usr/bin/env python3
"""DraftKings snapshot receiver on the VM (NBA_SPEED_PREREG.md amendment 4).

It is the FORCED COMMAND of the GitHub Actions key. In ~/.ssh/authorized_keys that key is pinned to
    restrict,command="/usr/bin/python3 /home/ubuntu/nba-engine/nba_dk_receive.py" ssh-ed25519 ...
so whatever a client asks to run, only this runs: no shell, no forwarding, no pty. It reads ONE
snapshot on stdin, checks it, and atomically replaces dk_snapshot.json. That file is all the key can
touch, and a forged snapshot could only feed the SECONDARY yardstick. The Mac's sender pipes through
it too, so both senders get the same checks.

THE RULES
  - at most MAX_BYTES on stdin and MAX_ROWS rows;
  - {"book": "dk", "fetched_at": "YYYY-MM-DDTHH:MM:SS" (UTC), "rows": [...], "detail": str};
  - fetched_at within MAX_AGE_S in the past and not more than MAX_AHEAD_S in the future;
  - each row is [event, player, stat, line, side, odds]: short strings, a numeric line, side over/under,
    decimal odds in (1, 1000);
  - a snapshot NOT NEWER than the one on disk is refused, so two senders can never step it backwards.
Exit 0 = written (or already newer on disk); 2 = refused. One line of output either way.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dk_snapshot.json"
MAX_BYTES, MAX_ROWS = 8_000_000, 60_000
MAX_AGE_S, MAX_AHEAD_S = 900, 120


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate(raw, now):
    """(snapshot, None) if acceptable, else (None, reason). `now` is naive UTC."""
    if len(raw) > MAX_BYTES:
        return None, f"too large ({len(raw):,} bytes)"
    try:
        snap = json.loads(raw)
    except ValueError:
        return None, "not JSON"
    if not isinstance(snap, dict) or snap.get("book") != "dk":
        return None, "not a DraftKings snapshot"
    try:
        at = dt.datetime.fromisoformat(snap.get("fetched_at", ""))
    except (TypeError, ValueError):
        return None, "fetched_at missing or not ISO"
    if at.tzinfo is not None or len(snap["fetched_at"]) != 19:
        return None, "fetched_at must be naive UTC YYYY-MM-DDTHH:MM:SS"
    age = (now - at).total_seconds()
    if age > MAX_AGE_S or age < -MAX_AHEAD_S:
        return None, f"fetched_at {snap['fetched_at']} is {age:+.0f} s from now"
    rows = snap.get("rows")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        return None, "rows missing or too many"
    for r in rows:
        if not (isinstance(r, list) and len(r) == 6
                and all(isinstance(r[i], str) and 0 < len(r[i]) <= n for i, n in ((0, 200), (1, 100), (2, 40)))
                and _num(r[3]) and r[4] in ("over", "under") and _num(r[5]) and 1.0 < r[5] < 1000):
            return None, f"bad row {str(r)[:80]}"
    detail = snap.get("detail", "")
    if not isinstance(detail, str) or len(detail) > 500:
        return None, "bad detail"
    return {"book": "dk", "fetched_at": snap["fetched_at"], "rows": rows, "detail": detail}, None


def receive(raw, now, out=OUT):
    """Validate and write; returns (exit code, message)."""
    snap, err = validate(raw, now)
    if err:
        return 2, f"refused: {err}"
    if out.exists():
        try:
            cur = json.loads(out.read_text()).get("fetched_at", "")
        except ValueError:
            cur = ""
        if cur and snap["fetched_at"] <= cur:
            return 0, f"kept: the snapshot on disk ({cur}) is not older than {snap['fetched_at']}"
    tmp = out.with_name(out.name + ".part")
    tmp.write_text(json.dumps(snap))
    tmp.replace(out)
    return 0, f"ok: {len(snap['rows'])} rows fetched {snap['fetched_at']}"


if __name__ == "__main__":
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    code, msg = receive(raw, dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0))
    print(msg)
    sys.exit(code)
