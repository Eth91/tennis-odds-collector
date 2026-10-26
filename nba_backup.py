#!/usr/bin/env python3
"""Nightly backup of the NBA engine's irreplaceable stores on the Oracle VM. Restore steps: NBA_BACKUP.md.

WHAT CANNOT BE REBUILT (everything else re-fetches or rebuilds: nba_gamelogs, nba_tracking, nba_profiles,
nba_wowy, nba_lab_cache, the .json/.pkl caches)
  nba_lines      the FanDuel/DK quote change log: the CLV substrate, ~260k quotes a day (2026-10-26)
  nba_shadow     shadow flags, pings, tip card: the forward record
  nba_news       official injury-report snapshots and news items, with their arrival times
  nba_proj_log   the projection engine's pre-tip forecasts: prospective test C (NBA_PROJECTION_PREREG.md)
  nba_pm         the Kalshi prop change log behind T1-T3 (amendment 20); Kalshi keeps no quote history
  nba_matchup    for its `playtypes`: Synergy gives season totals only, snapshotted daily (amendment 30),
                 so a past day's snapshot cannot be re-fetched. The box scores beside it can (2.5 MB, kept whole)
  underdog_nba_log.jsonl   the raw X news log the watchers append to (NBA_X_LOG)

MODELLED ON wnba_backup.py, with three changes its own record forced:
  * PER-STORE, NOT ALL-OR-NOTHING. wnba_backup refused the whole run when ONE store shrank: fanduel_props
    went to 0 on 2026-08-14 and the job refused every night until it was retired on 10-23, so none of its
    ten stores was backed up after Aug 13 (and worker-2's pull failed daily on the stale stamp). Here a
    store that shrinks is quarantined on its own and the others are backed up as usual.
  * PER-TABLE GUARD. A store's total can grow while one table is wiped (flags truncated while cands grows).
    Every table must hold at least the rows of the last good backup. nba_lines.board is the current board,
    replaced every cycle, and is the only table exempt.
  * THE BACKUP API, NOT VACUUM INTO. These stores use rollback journals (journal_mode=delete), so a reader
    blocks writers' commits. On nba_lines (222 MB, 2026-10-26) VACUUM INTO held the read lock 17.5 s, the
    backup API 6.1 s; the writers wait up to 60 s (nba_proj_log's 30 s). The lock time is recorded per store
    and pinged above LOCK_WARN_S, long before a writer times out (nba_lines grows ~45 MB a day).
A shrunk (or corrupt) store's snapshot is still written, as <label>.<stamp>.SHRUNK.sqlite.gz, because its
new rows exist nowhere else; but it never becomes the baseline, and the last good snapshot is pinned
against pruning until `--accept LABEL` (after checking WHY) makes the new one the baseline.

OFF-BOX. This box holds no key on worker-2 and worker-2 holds one here (wnba_backup's design), so
nba_backup_pull.py on worker-2 PULLS at 10:05 UTC, checks every file against the sha256 recorded here,
and leaves offbox.json in OUT. A run that finds the off-box copy more than OFFBOX_STALE_D days old pings.

FAIL LOUD. Cron has no NTFY_TOPIC in its environment, so it is also read from ~/.nba-ping.env directly
(an env-only alert would be a silent no-op, the wnba_backup lesson).

    python3 nba_backup.py                    # the nightly run (cron 09:48 UTC: after the :43 cycle's lines step
                                             # and the :45 report trigger, done before :53; clear of 10:30-11:20)
    python3 nba_backup.py --verify           # restore-test the newest good snapshot of every store
    python3 nba_backup.py --accept nba_news  # accept a shrink you have explained
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("NBA_BACKUP_DIR") or Path.home() / "backups" / "nba")
X_LOG = Path(os.environ.get("NBA_X_LOG") or "/home/ubuntu/tennis-odds-collector/underdog_nba_log.jsonl")
STORES = [(n, HERE / f"{n}.sqlite") for n in
          ("nba_lines", "nba_shadow", "nba_news", "nba_proj_log", "nba_pm", "nba_matchup")] + [("underdog_nba_log", X_LOG)]
EXEMPT = {("nba_lines", "board")}            # current state, replaced every cycle: not a history
KEEP_DAILY, KEEP_SUNDAYS = 7, 28             # days; a store's last good snapshot is kept regardless
LOCK_WARN_S = 20
OFFBOX_STALE_D = 2
FREE_FLOOR = 3e9                             # bytes that must stay free after this run's writes
ENV_FILES = [Path.home() / ".nba-ping.env", Path.home() / ".nba-engine.env"]


def notify(msg, env_files=ENV_FILES, title="NBA backup"):
    topic = os.environ.get("NTFY_TOPIC")
    for f in env_files:
        if topic:
            break
        try:
            for ln in f.read_text().splitlines():
                ln = ln.strip().removeprefix("export ").strip()
                if ln.startswith("NTFY_TOPIC="):
                    topic = ln.split("=", 1)[1].strip().strip('"').strip("'") or topic
        except OSError:
            pass
    if not topic:
        print(f"  [notify] NO TOPIC RESOLVED -- message was: {msg}")
        return
    try:
        import requests
        requests.post(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
                      headers={"Title": title, "Tags": "rotating_light"}, timeout=10)
    except Exception as e:
        print(f"  [notify failed] {type(e).__name__} -- message was: {msg}")


def counts(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        c.close()


def is_db(path):
    return str(path).endswith((".sqlite", ".sqlite.gz"))


def tally(path):
    """{table: rows} for a store file; a line file is one table, `lines`."""
    if is_db(path):
        return counts(path)
    with open(path, "rb") as f:
        return {"lines": sum(b.count(b"\n") for b in iter(lambda: f.read(1 << 20), b""))}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def gunzip(gz, dest):
    with gzip.open(gz, "rb") as fin, open(dest, "wb") as fout:
        shutil.copyfileobj(fin, fout, 1 << 20)


def snapshot(label, src, work):
    """A consistent copy of `src` in `work`, gzipped to a .part and verified by a round trip."""
    ext = ".sqlite" if is_db(src) else src.suffix
    tmp = work / f"{label}{ext}"
    t0 = time.monotonic()
    if is_db(src):
        s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=60)
        d = sqlite3.connect(tmp)
        try:
            s.backup(d)                               # one step: the source's read lock is held only for the copy
        finally:
            d.close()
            s.close()
        lock = time.monotonic() - t0
        c = sqlite3.connect(tmp)
        check = c.execute("PRAGMA quick_check").fetchone()[0]
        c.close()
    else:                                             # append-only text: keep complete lines only
        data = src.read_bytes()
        tmp.write_bytes(data[:data.rfind(b"\n") + 1])
        lock, check = 0.0, "ok"
    tables = tally(tmp)
    part = work / f"{label}{ext}.gz.part"
    with open(tmp, "rb") as fin, gzip.open(part, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, 1 << 20)
    raw = tmp.stat().st_size
    tmp.unlink()
    chk = work / f"{label}.chk{ext}"
    gunzip(part, chk)
    back = tally(chk)
    chk.unlink()
    if back != tables:
        part.unlink()
        raise RuntimeError(f"gzip round trip changed the counts ({tables} -> {back})")
    return {"tables": tables, "rows": sum(tables.values()), "lock_s": round(lock, 2), "quick_check": check,
            "raw_bytes": raw, "gz_bytes": part.stat().st_size, "sha256_gz": sha256(part)}, part, ext + ".gz"


def shrunk(label, now, was):
    """The tables holding fewer rows than the last good backup (a dropped table holds 0)."""
    return [f"{t} {n} -> {now.get(t, 0)}" for t, n in sorted(was.items())
            if (label, t) not in EXEMPT and now.get(t, 0) < n]


def _day(fn):
    p = next((p for p in fn.split(".") if len(p) == 8 and p.isdigit()), None)
    try:
        return dt.datetime.strptime(p, "%Y%m%d").date() if p else None
    except ValueError:
        return None


def prune(out, today, pinned):
    """Thin the snapshots: KEEP_DAILY days, then Sundays to KEEP_SUNDAYS. Every store here only grows, so
    the newest good snapshot holds every older row; `pinned` (each store's last good file) is never touched."""
    removed = 0
    for fn in sorted(os.listdir(out)):
        d = _day(fn)
        if not fn.endswith(".gz") or d is None or fn in pinned:
            continue
        age = (today - d).days
        if not (age <= KEEP_DAILY or (age <= KEEP_SUNDAYS and d.weekday() == 6)):
            (out / fn).unlink()
            removed += 1
    return removed


def _load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_json(path, obj):
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(obj, indent=2))
    os.replace(part, path)


def run(stores=STORES, out=OUT, today=None, accept=(), notify=notify):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    today = today or dt.datetime.now(dt.timezone.utc).date()
    stamp = today.strftime("%Y%m%d")
    latest = _load(out / "latest.json") or {"first": stamp, "good": {}}
    problems, night = [], {}

    sizes = [p.stat().st_size for _l, p in stores if p.exists()]
    need = max(sizes, default=0) + sum(sizes) // 4     # the largest raw copy at a time, plus the gzips
    free = shutil.disk_usage(out).free
    if free - need < FREE_FLOOR:
        msg = (f"REFUSED: {free / 1e9:.1f} GB free, this run needs ~{need / 1e9:.1f} GB and "
               f"{FREE_FLOOR / 1e9:.0f} GB must stay free -- nothing written or pruned")
        print(msg)
        notify(msg)
        return 1
    work = out / ".work"
    shutil.rmtree(work, ignore_errors=True)            # a crashed run's leftovers
    work.mkdir()

    for label, src in stores:
        if not src.exists() or src.stat().st_size < 100:
            problems.append(f"{label} MISSING at {src}")
            night[label] = {"status": "missing"}
            continue
        try:
            info, part, ext = snapshot(label, src, work)
        except Exception as e:
            problems.append(f"{label} snapshot FAILED: {str(e)[:160]}")
            night[label] = {"status": "error"}
            continue
        prev = latest["good"].get(label)
        fell = shrunk(label, info["tables"], prev["tables"]) if prev else []
        status = "SHRUNK" if fell else "CORRUPT" if info["quick_check"] != "ok" else "ok"
        if status != "ok" and label in accept:
            print(f"  {label}: {status} ACCEPTED by --accept ({', '.join(fell) or info['quick_check'][:80]})")
            status = "ok"
        name = f"{label}.{stamp}{ext}" if status == "ok" else f"{label}.{stamp}.{status}{ext}"
        os.replace(part, out / name)
        info.update(status=status, file=name, stamp=stamp)
        night[label] = info
        if status == "ok":
            latest["good"][label] = info
        else:
            if fell:
                problems.append(f"{label} SHRANK ({'; '.join(fell)}): kept as {name}, the good copy of "
                                f"{prev['stamp']} stays the baseline (--accept {label} once explained)")
            if info["quick_check"] != "ok":
                problems.append(f"{label} fails quick_check ({info['quick_check'][:80]}): the LIVE store may be corrupt")
        if info["lock_s"] > LOCK_WARN_S:
            problems.append(f"{label} held the read lock {info['lock_s']:.0f}s (writers wait 60s): time for incremental backups")
    shutil.rmtree(work, ignore_errors=True)

    off = _load(out / "offbox.json")
    since = (today - dt.datetime.strptime((off or {}).get("stamp") or latest["first"], "%Y%m%d").date()).days
    if since > OFFBOX_STALE_D:
        problems.append(f"the off-box copy on worker-2 is {since} days old" if off else
                        f"no off-box copy yet, {since} days after the first backup (worker-2 nba_backup_pull.py)")

    latest.update(stamp=stamp, run=night)
    _write_json(out / f"manifest.{stamp}.json", {"stamp": stamp, "stores": night, "problems": problems})
    _write_json(out / "latest.json", latest)
    for label, i in night.items():
        if "file" in i:
            print(f"  {label:<17}{i['status']:<8}{i['rows']:>10} rows {i['raw_bytes'] / 1e6:8.1f} MB -> "
                  f"{i['gz_bytes'] / 1e6:6.1f} MB  lock {i['lock_s']:5.1f}s")
        else:
            print(f"  {label:<17}{i['status']}")
    n = prune(out, today, {i["file"] for i in latest["good"].values()})
    total = sum(p.stat().st_size for p in out.glob("*.gz"))
    print(f"  pruned {n} old file(s); {total / 1e6:.1f} MB of snapshots in {out}")
    if problems:
        for p in problems:
            print("PROBLEM: " + p)
        notify(" | ".join(problems)[:1500])
        return 1
    print("OK")
    return 0


def verify(stores=STORES, out=OUT, notify=notify):
    """Restore-test: reopen each store's newest good snapshot and compare it with what was recorded."""
    out = Path(out)
    latest = _load(out / "latest.json")
    if not latest or not latest.get("good"):
        notify("verify: nothing has ever been backed up")
        print("FAILED: no latest.json")
        return 1
    live = dict(stores)
    work = out / ".verify"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    bad = []
    for label, info in sorted(latest["good"].items()):
        gz = out / info["file"]
        try:
            if sha256(gz) != info["sha256_gz"]:
                raise ValueError("sha256 differs from the one recorded at write time")
            chk = work / info["file"].removesuffix(".gz")
            gunzip(gz, chk)
            got = tally(chk)
            if is_db(chk):
                c = sqlite3.connect(f"file:{chk}?mode=ro", uri=True)
                qc = c.execute("PRAGMA quick_check").fetchone()[0]
                c.close()
                if qc != "ok":
                    raise ValueError(f"quick_check: {qc[:60]}")
            chk.unlink()
            if got != info["tables"]:
                raise ValueError(f"table counts differ ({got} vs {info['tables']})")
            now = sum(tally(live[label]).values()) if live.get(label) and live[label].exists() else None
            print(f"  {label:<17}{info['stamp']}  restored {sum(got.values()):>10} rows  [ok]   live now "
                  + (f"{now} (+{now - info['rows']} since)" if now is not None else "?"))
        except Exception as e:
            bad.append(f"{label}: {str(e)[:120]}")
            print(f"  {label:<17}FAILED {str(e)[:120]}")
    shutil.rmtree(work, ignore_errors=True)
    if bad:
        notify("restore test FAILED: " + "; ".join(bad))
        return 1
    print("RESTORE TEST PASSED")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--accept", action="append", default=[], metavar="LABEL",
                    help="accept this store's shrink (or failed quick_check) as the new baseline; check WHY first")
    a = ap.parse_args()
    sys.exit(verify() if a.verify else run(accept=a.accept))
