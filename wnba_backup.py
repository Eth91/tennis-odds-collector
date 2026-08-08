#!/usr/bin/env python3
"""Durable backup for the WNBA data on the board VM. Sibling of tt-elite/fd_backup.py.

WHAT IS IRREPLACEABLE HERE
    wnba_lines.fd_lines is 1.6M timestamped line snapshots and cannot be refetched -- it is the
    entire WNBA CLV substrate, and [[feedback_real_lines_only]] means every honest backtest runs
    on it. wnba_ledger holds predictions/selections/parlays: the actual track record, which
    exists nowhere else. wnba_stints cost real work to repair (the clock bug that read 12.8%
    when the truth was 1.4%) and is expensive to rebuild. The props archives are scraped history.
    None of it is reconstructible from a live API.

WHY IT NEEDED THIS
    The repo-dir wnba_*.sqlite files are SYMLINKS into ~/wnba_data/ -- the real bytes live in one
    directory on one box. The stale db_backup_*/db_safe_*/db_premove/.git-clobbered directories
    scattered around this box are fossils of past scares, all one-off and none scheduled. The TT
    side had the same shape and its stated rebuild path had silently died; see fd_backup.py.

DESIGN NOTES SPECIFIC TO THIS BOX
  * VACUUM INTO, not a file copy. wnba_lines and fanduel_props are written continuously by the
    live loop, so copying the file could catch a torn write. VACUUM INTO takes a consistent
    snapshot of a live DB (~13s for the 292MB one).
  * NO OFF-BOX PUSH FROM HERE. This box has no key on worker-2, and minting one is an access
    grant that belongs to the operator, not to a backup script. worker-2 already has a key HERE,
    so redundancy is achieved by worker-2 PULLING (see pull_wnba.sh on that box). Same result,
    no new credential.
  * MONOTONE GUARD, per DB, on total rows. These stores only grow. A shrink means something is
    wrong, and overwriting a good backup with a truncated one is the worst version of the
    silent-zero failure class this system keeps hitting. --force overrides deliberately.
  * FAIL LOUD reading ~/wnba-loop.env directly: wnba_alert.py resolves NTFY_TOPIC from os.environ
    only, which is UNSET under cron, so an env-only alert here would be a silent no-op.
"""
import argparse, gzip, hashlib, io, json, os, shutil, sqlite3, sys, datetime as dt
import code_backup

OUT = "/home/ubuntu/backups/wnba"
ENV_FILE = "/home/ubuntu/wnba-loop.env"
REPO = "/home/ubuntu/tennis-odds-collector"
DATA = "/home/ubuntu/wnba_data"

# ⚠️ ROLLING-WINDOW SOURCES. `fd_maintain.py` prunes fd_lines to KEEP_DAYS (~2 days), so
# wnba_lines is NOT a historical archive -- it is a rotating buffer that drops ~500k rows/day.
# Two consequences, both learned the hard way when the monotone guard fired on 2026-08-07:
#   1. the shrink guard must NOT apply to these, or the backup fails every single day and the
#      net effect is NO backup at all -- strictly worse than the risk the guard protects against
#   2. their snapshots must NEVER be pruned. Every daily file is the ONLY surviving copy of that
#      day's lines; deleting one deletes that day permanently. Non-rolling DBs can be thinned
#      because the source still holds their history -- these cannot.
ROLLING = {"wnba_lines"}
ROLLING_FLOOR = 50_000        # a rolling table below this is broken, not merely rotating

DBS = [
    ("wnba_lines",      f"{DATA}/wnba_lines.sqlite"),       # 1.6M line snapshots -- the CLV substrate
    ("fanduel_props",   f"{DATA}/fanduel_props.sqlite"),
    ("wnba_ledger",     f"{DATA}/wnba_ledger.sqlite"),      # the track record
    ("wnba_clv",        f"{DATA}/wnba_clv.sqlite"),
    ("wnba_proj_log",   f"{DATA}/wnba_proj_log.sqlite"),
    ("wnba_stints",     f"{REPO}/wnba_stints.sqlite"),      # expensive to rebuild
    ("wnba_props_2025", f"{REPO}/wnba_props_2025.sqlite"),
    ("wnba_props_hist", f"{REPO}/wnba_props_hist.sqlite"),
    ("wnba_boxscores",  f"{REPO}/wnba_boxscores.sqlite"),
    ("bet_ledger",      f"{REPO}/bet_ledger.sqlite"),
]


def notify(msg, tag="rotating_light"):
    topic = os.environ.get("NTFY_TOPIC")
    try:                                    # cron has no env -- read the loop's file directly
        for ln in io.open(ENV_FILE):
            ln = ln.strip()
            if ln.startswith("NTFY_TOPIC=") and not ln.startswith("#"):
                topic = ln.split("=", 1)[1].strip().strip('"').strip("'") or topic
    except Exception:
        pass
    if not topic:
        print("  [notify] NO TOPIC RESOLVED -- message was: %s" % msg)
        return
    try:
        import requests
        requests.post("https://ntfy.sh/%s" % topic,
                      data=("wnba_backup: " + msg).encode("utf-8"),
                      headers={"Tags": tag, "Title": "WNBA data backup"}, timeout=10)
    except Exception as e:
        print("  [notify failed] %s -- message was: %s" % (e, msg))


def fail(msg):
    print("REFUSED: " + msg)
    notify("REFUSED -- " + msg)
    sys.exit(1)


def counts(path):
    c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    out = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        try:
            out[t] = c.execute('SELECT count(*) FROM "%s"' % t).fetchone()[0]
        except Exception:
            pass
    c.close()
    return out


def last_good():
    p = os.path.join(OUT, "latest.json")
    try:
        return json.load(io.open(p))
    except Exception:
        return None


def snapshot(label, src, stamp):
    """VACUUM INTO a consistent copy, gzip it, verify it reopens with the same row counts."""
    tmp_db = "/tmp/wnba_snap_%s.sqlite" % label
    for p in (tmp_db, tmp_db + "-wal", tmp_db + "-shm"):
        if os.path.exists(p):
            os.unlink(p)
    c = sqlite3.connect("file:%s?mode=ro" % src, uri=True)
    c.execute("VACUUM INTO '%s'" % tmp_db)
    c.close()
    cnt = counts(tmp_db)                      # count the SNAPSHOT, not the moving source
    out = os.path.join(OUT, "%s.%s.sqlite.gz" % (label, stamp))
    part = out + ".part"
    h = hashlib.sha256()
    with open(tmp_db, "rb") as fin, gzip.open(part, "wb", compresslevel=6) as fout:
        while True:
            b = fin.read(1 << 20)
            if not b:
                break
            h.update(b)
            fout.write(b)
    raw = os.path.getsize(tmp_db)
    os.unlink(tmp_db)
    # integrity: the gzip must decompress to a valid sqlite with identical counts
    chk = "/tmp/wnba_chk_%s.sqlite" % label
    with gzip.open(part, "rb") as fin, open(chk, "wb") as fout:
        shutil.copyfileobj(fin, fout, 1 << 20)
    back = counts(chk)
    os.unlink(chk)
    if back != cnt:
        os.unlink(part)
        fail("%s: gzip round-trip changed row counts (%s -> %s)" % (label, cnt, back))
    return {"tables": cnt, "rows": sum(cnt.values()), "raw_bytes": raw,
            "gz_bytes": os.path.getsize(part), "sha256_raw": h.hexdigest()}, part, out


def prune(today):
    removed = 0
    for fn in sorted(os.listdir(OUT)):
        parts = fn.split(".")
        day = next((p for p in parts if len(p) == 8 and p.isdigit()), None)
        if not day:
            continue
        try:
            d = dt.datetime.strptime(day, "%Y%m%d").date()
        except ValueError:
            continue
        age = (today - d).days
        # a rolling source's snapshot is the ONLY copy of that day -- never thin those
        if any(fn.startswith(r + ".") for r in ROLLING):
            continue
        keep = (age <= 7) or (age <= 60 and d.weekday() == 6) or (d.day == 1)
        if not keep:
            os.unlink(os.path.join(OUT, fn))
            removed += 1
    return removed


def cmd_run(force=False):
    os.makedirs(OUT, exist_ok=True)
    today = dt.datetime.now(dt.timezone.utc).date()
    stamp = today.strftime("%Y%m%d")
    prev = (last_good() or {}).get("dbs", {})
    man, staged = {"stamp": stamp, "dbs": {}}, []
    for label, src in DBS:
        if not os.path.exists(src) or os.path.getsize(src) < 100:
            print("  %-16s SKIP (missing or stub)" % label)
            continue
        info, part, final = snapshot(label, src, stamp)
        was = prev.get(label, {}).get("rows")
        if label in ROLLING:
            # rotating buffer: judge it against a floor, not against yesterday
            if info["rows"] < ROLLING_FLOOR:
                for p, _f in staged:
                    os.unlink(p)
                os.unlink(part)
                fail("%s is ROLLING but only %d rows (floor %d) -- collector may be dead"
                     % (label, info["rows"], ROLLING_FLOOR))
            was = None
        if was is not None and info["rows"] < was and not force:
            for p, _f in staged:
                os.unlink(p)
            os.unlink(part)
            fail("%s SHRANK %d -> %d rows; previous backup left intact (use --force to override)"
                 % (label, was, info["rows"]))
        man["dbs"][label] = info
        staged.append((part, final))
    if not staged:
        fail("nothing was backed up -- every source was missing or a stub")
    for part, final in staged:
        os.replace(part, final)
    # CODE, not just data. This box cannot push (suspended GitHub account) and the repo is
    # 1,805 commits ahead of an origin last updated 2026-08-02, so the source exists ONLY here.
    # A git bundle was tried first and REJECTED: `git bundle verify` passed it but cloning it
    # back failed ("Failed to traverse parents"), because git_reshallow_any.sh keeps the repo
    # shallow. Source tar restores; a bundle of pruned history does not.
    try:
        prevc = (last_good() or {}).get("code") or {}
        man["code"] = code_backup.snapshot(REPO, OUT, stamp, prev=prevc)
        cd = man["code"]
        print("  %-16s %9d files %7.1f MB -> %6.2f MB  [restore-tested]"
              % ("SOURCE", cd["files"], 0.0, cd["bytes"] / 1e6))
    except Exception as e:
        notify("code snapshot FAILED -- %s (DB backup is good)" % str(e)[:160])
        print("  SOURCE snapshot FAILED: %s" % str(e)[:200])

    io.open(os.path.join(OUT, "latest.json"), "w").write(json.dumps(man, indent=2))
    io.open(os.path.join(OUT, "manifest.%s.json" % stamp), "w").write(json.dumps(man, indent=2))
    tot_raw = sum(d["raw_bytes"] for d in man["dbs"].values())
    tot_gz = sum(d["gz_bytes"] for d in man["dbs"].values())
    for label, d in man["dbs"].items():
        print("  %-16s %9d rows  %7.1f MB -> %6.1f MB"
              % (label, d["rows"], d["raw_bytes"] / 1e6, d["gz_bytes"] / 1e6))
    print("  TOTAL            %9d rows  %7.1f MB -> %6.1f MB  (%.1fx)"
          % (sum(d["rows"] for d in man["dbs"].values()), tot_raw / 1e6, tot_gz / 1e6,
             tot_raw / max(tot_gz, 1)))
    n = prune(today)
    if n:
        print("  pruned %d old file(s)" % n)
    print("OK  (off-box copy is worker-2's job: it PULLS -- this box holds no key there)")


def cmd_verify():
    man = last_good()
    if not man:
        fail("no latest.json -- nothing has ever been backed up")
    stamp = man["stamp"]
    bad = []
    for label, info in man["dbs"].items():
        path = os.path.join(OUT, "%s.%s.sqlite.gz" % (label, stamp))
        if not os.path.exists(path):
            bad.append("%s: file missing" % label)
            continue
        chk = "/tmp/wnba_v_%s.sqlite" % label
        try:
            with gzip.open(path, "rb") as fin, open(chk, "wb") as fout:
                shutil.copyfileobj(fin, fout, 1 << 20)
            got = counts(chk)
            ok = got == info["tables"]
            live = None
            for lb, src in DBS:
                if lb == label and os.path.exists(src):
                    live = sum(counts(src).values())
            print("  %-16s restored %9d rows  [%s]   live now %s"
                  % (label, sum(got.values()), "ok" if ok else "MISMATCH",
                     ("%d (+%d since)" % (live, live - info["rows"])) if live else "?"))
            if not ok:
                bad.append("%s: table counts differ" % label)
        except Exception as e:
            bad.append("%s: %s" % (label, str(e)[:60]))
        finally:
            if os.path.exists(chk):
                os.unlink(chk)
    if bad:
        fail("restore test FAILED: " + "; ".join(bad))
    print("RESTORE TEST PASSED")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="accept a row-count shrink (use only after checking WHY)")
    a = ap.parse_args()
    cmd_verify() if a.verify else cmd_run(a.force)
