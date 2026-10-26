# NBA backup: what, where, and how to restore

`nba_backup.py` (on the VM) snapshots the stores that cannot be rebuilt every night. `nba_backup_pull.py`
(on worker-2) copies them off the VM. The reasons for each choice are in the docstring of `nba_backup.py`.

| store | why it cannot be rebuilt |
|---|---|
| `nba_lines.sqlite` | quote change log, the CLV substrate |
| `nba_shadow.sqlite` | shadow flags, pings, tip card: the forward record |
| `nba_news.sqlite` | official injury-report snapshots, news items and their arrival times |
| `nba_proj_log.sqlite` | the projection engine's pre-tip forecasts (prospective test C) |
| `nba_pm.sqlite` | the Kalshi change log for T1-T3 (amendment 20) |
| `nba_matchup.sqlite` | its `playtypes` daily Synergy snapshots (the box scores beside them can be re-fetched) |
| `~/tennis-odds-collector/underdog_nba_log.jsonl` | the raw X news log |

## Where the copies are

- **VM** `ubuntu@155.248.217.149:~/backups/nba/`, written 09:45 UTC (log `~/nba-logs/backup.log`).
- **worker-2** `ubuntu@140.238.143.104:~/backups/nba-board/`, pulled 10:05 UTC (log `~/nba_backup_pull.log`).
  From the Mac: `ssh -i ~/.ssh/oracle_vm ubuntu@140.238.143.104`.

Files: `<store>.<YYYYMMDD>.sqlite.gz` (`.jsonl.gz` for the X log). `latest.json` names each store's last
**good** snapshot with its table counts and sha256. `manifest.<YYYYMMDD>.json` records each night.
`offbox.json` records worker-2's last pull. Snapshots are kept for 7 days, then Sundays only up to 28 days.
Each store's last good snapshot is never pruned.

## Alerts (ntfy, title "NBA backup")

- **`<store> SHRANK (table a -> b)`**: a table has fewer rows than the last good backup. Tonight's copy is
  kept as `<store>.<stamp>.SHRUNK.sqlite.gz`. The last good copy stays the baseline and is never pruned.
  The other stores were backed up as usual. Find out why the table shrank. If the shrink was intended:
  `python3 nba_backup.py --accept <store>`. If it was not, restore that store (below).
- **`fails quick_check`**: the live store may be corrupt. Restore it.
- **`off-box copy on worker-2 is N days old`**: read `~/nba_backup_pull.log` on worker-2.
- **`held the read lock Ns`**: the store has grown enough that a whole-file snapshot now blocks its writers
  for too long. Switch that store to incremental backups before writers start timing out (they wait 60 s).
- **`REFUSED: ... GB free`**: the disk is nearly full. Nothing was written or pruned. Reduce `KEEP_DAILY`.

Restore test at any time: `cd ~/nba-engine && python3 nba_backup.py --verify`.

## Restore one store (on the VM)

```bash
cd ~/nba-engine
S=nba_shadow                                                   # the store's label
F=$(python3 -c "import json; print(json.load(open('$HOME/backups/nba/latest.json'))['good']['$S']['file'])")
# 1. pause every NBA writer, and wait for a running cycle to end (test the lock with -d: never open it)
crontab -l > ~/crontab.bak-restore-$(date -u +%Y%m%dT%H%M)
crontab -l | sed '/nba-engine/s/^/#RESTORE /' | crontab -
sudo systemctl stop nba-pm nba-x-beats nba-x-fast              # + underdog-watch for the X log
while [ -d /tmp/nba-cycle.lock ]; do sleep 5; done
# 2. sha256 against the digest recorded at write time, then a reopen with table counts. If this fails,
#    scp the same file back from worker-2's ~/backups/nba-board/ and verify again.
python3 nba_backup.py --verify
# 3. move the live store aside WITH any -journal (a hot journal would roll back into the restored file)
A=~/restore-aside-$(date -u +%Y%m%dT%H%M); mkdir -p $A && mv $S.sqlite* $A/
gunzip -c ~/backups/nba/$F > $S.sqlite
python3 -c "import sqlite3; print(sqlite3.connect('$S.sqlite').execute('pragma quick_check').fetchone()[0])"   # ok
# 4. resume: the newest crontab backup, then the services
crontab "$(ls -t ~/crontab.bak-restore-* | head -1)"
sudo systemctl start nba-pm nba-x-beats nba-x-fast
```

Rows written after the snapshot are only in the copy you moved aside (`$A`). If it still opens, copy them
back table by table. For an append-only table: `ATTACH '<aside>' AS old; INSERT INTO t SELECT * FROM old.t
WHERE rowid > (SELECT coalesce(max(rowid), 0) FROM main.t);`. Don't use `INSERT OR IGNORE`: `quotes` has no
unique key, so it would duplicate every row. Then run
`python3 nba_backup.py`. If rows were lost it reports SHRANK, and `--accept <store>` makes the restored
copy the new baseline.

For the X log, use `gunzip -c <file> > ~/tennis-odds-collector/underdog_nba_log.jsonl` in step 3, and stop
`underdog-watch` too.

**If the VM is lost:** copy `~/backups/nba-board/` from worker-2 to the new box, restore each store as
above, then deploy the code from `main` with `nba_vm_deploy.sh`.

## Installing the worker-2 side

`nba_vm_deploy.sh` deploys the board VM only. On worker-2, run from a checkout:

```bash
scp -i ~/.ssh/oracle_vm nba_backup.py nba_backup_pull.py ubuntu@140.238.143.104:nba-backup/
```

Its cron line, `5 10 * * * cd /home/ubuntu/nba-backup && /usr/bin/python3 nba_backup_pull.py >> /home/ubuntu/nba_backup_pull.log 2>&1`, needs no environment.
Its failure pings use worker-2's own topic in `~/tt-loop.env`.
