# WNBA RESEARCH TWIN — STATE
production: v1.8 frozen 2026-08-13, 8 files. UNTOUCHED.
research_root: research/   (nothing here is imported by production)

## data assets
- basketball_wnba_odds_hist.sqlite : 6 snap_kinds, 2023-05-21..2026-08-13
- wnba_props_hist.sqlite (2026), wnba_props_2025.sqlite : legacy, 45-min snaps
- wnba_stints.sqlite : onfloor/pairs/pteam, 942 games 2023-05-05..
- wnba_ledger.sqlite : 205 predictions, 2026-07-09..
- underdog_log.jsonl : 307 news items w/ timestamps

## open blockers
(none)

## priority queue
1 odds-timeline coverage   2 market timing   3 stint decomposition
4 role-transition graph    5 market response 6 new markets  7 ranking failure

## live research instruments
- research/pr002_shadow.py  cron */20  -> research/pr002_shadow.sqlite  (PR-002 forward test)
- wnba_health.py            cron */30  -> ~/health.log (empty = green)

## next when data allows
- PR-002 needs n>=40 shadow rows before any read. Do NOT peek at partial n.
- PR-001 (vac) needs n>=40 tracked rows graded after 2026-08-13.
