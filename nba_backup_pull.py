#!/usr/bin/env python3
"""Pull the board VM's NBA backup (nba_backup.py) to worker-2, so the NBA stores live on two machines.

Runs ON worker-2 (cron 10:05 UTC, after the VM's 09:45 run) from ~/nba-backup/, beside a copy of
nba_backup.py whose checks and retention it reuses. nba_vm_deploy.sh deploys the board VM only; this box is
installed by hand (NBA_BACKUP.md).

worker-2 PULLS because the board VM holds no key here and worker-2 holds one there (pull_wnba.py's design).
Each file is checked against the sha256 the VM recorded when it WROTE the file, not a digest taken at pull
time, so damage at rest on the VM is caught too; the biggest store is reopened and its table counts compared.
On success it leaves offbox.json on the VM, so the VM's own run pings on the NBA topic when this pull stops;
a failure here also pings worker-2's own topic (~/tt-loop.env), as pull_wnba.py does.

    python3 nba_backup_pull.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import nba_backup as B

REMOTE = "ubuntu@155.248.217.149"
RDIR = "/home/ubuntu/backups/nba"
OUT = Path.home() / "backups" / "nba-board"
OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
STALE_D = 2
ENV_FILES = [Path.home() / "tt-loop.env"]


class Remote:
    """What the pull asks of the VM: read a small file, fetch one, leave one (a test swaps in a directory)."""

    def __init__(self, host=REMOTE, rdir=RDIR):
        self.host, self.rdir = host, rdir

    def _sh(self, args, text=None):
        r = subprocess.run(args, input=text, capture_output=True, text=True, timeout=600)
        if r.returncode:
            raise RuntimeError((r.stderr or r.stdout or "").strip()[:200])
        return r.stdout

    def read(self, name):
        return self._sh(["ssh", *OPTS, self.host, f"cat {self.rdir}/{name}"])

    def fetch(self, name, dest):
        self._sh(["scp", "-q", *OPTS, f"{self.host}:{self.rdir}/{name}", str(dest)])

    def put(self, name, text):
        self._sh(["ssh", *OPTS, self.host, f"cat > {self.rdir}/{name}.part && mv {self.rdir}/{name}.part {self.rdir}/{name}"],
                 text)


def pull(remote=None, out=OUT, today=None, notify=None):
    remote, out = remote or Remote(), Path(out)
    notify = notify or (lambda m: B.notify("pull: " + m, ENV_FILES, "NBA backup pull"))
    today = today or dt.datetime.now(dt.timezone.utc).date()

    def fail(msg):
        print("FAILED: " + msg)
        notify(msg)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    try:
        latest = json.loads(remote.read("latest.json"))
    except Exception as e:
        return fail(f"cannot read the VM's latest.json: {str(e)[:160]}")
    stamp = latest["stamp"]
    age = (today - dt.datetime.strptime(stamp, "%Y%m%d").date()).days
    if age > STALE_D:
        return fail(f"the VM's newest backup is {age} days old ({stamp}): its cron may be dead")

    # every store's last good snapshot, and tonight's files (a quarantined SHRUNK copy holds rows found nowhere else)
    want = {i["file"]: i["sha256_gz"] for grp in ("good", "run") for i in latest.get(grp, {}).values() if i.get("file")}
    pulled = kept = 0
    for name, sha in sorted(want.items()):
        dest = out / name
        if dest.exists() and B.sha256(dest) == sha:
            kept += 1
            continue
        part = out / (name + ".part")
        try:
            remote.fetch(name, part)
        except Exception as e:
            return fail(f"fetch {name}: {str(e)[:160]}")
        got = B.sha256(part)
        if got != sha:
            part.unlink()
            return fail(f"{name}: sha256 {got[:12]} after the pull, the VM recorded {sha[:12]} when it wrote it")
        os.replace(part, dest)
        pulled += 1

    dbs = [i for i in latest["good"].values() if B.is_db(i["file"])]
    if dbs:
        big = max(dbs, key=lambda i: i["rows"])
        chk = out / ".chk.sqlite"
        try:
            B.gunzip(out / big["file"], chk)
            got = B.tally(chk)
        except Exception as e:
            got = f"an error ({str(e)[:120]})"
        chk.unlink(missing_ok=True)
        if got != big["tables"]:
            return fail(f"{big['file']} reopened with {got}, the VM recorded {big['tables']}")
    B._write_json(out / "latest.json", latest)
    try:
        remote.put("offbox.json", json.dumps({"stamp": stamp, "pulled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                              "host": socket.gethostname(), "files": len(want)}))
    except Exception as e:
        return fail(f"pulled, but could not leave offbox.json on the VM: {str(e)[:160]}")
    n = B.prune(out, today, {i["file"] for i in latest["good"].values()})
    total = sum(p.stat().st_size for p in out.glob("*.gz"))
    print(f"  stamp {stamp} ({age} day(s) old) | {pulled} pulled, {kept} already here, all sha256-verified")
    if dbs:
        print(f"  {big['file']} reopened: {big['rows']} rows, table counts match")
    print(f"  pruned {n}; {total / 1e6:.1f} MB in {out}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(pull())
