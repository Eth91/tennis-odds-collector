"""On the VM, read-only: each date's latest official report and lineups snapshot (as the page reads them), from
2026-11-19 to the date given (the 150th forward game's). python3 extract_vm_fwd.py 2026-12-08"""
import datetime as dt, json, sqlite3, sys
sys.path.insert(0, "/home/ubuntu/nba-engine")
import nba_research as RS
ro = lambda p: sqlite3.connect(f"file:{p}?mode=ro", uri=True)
d0, d1 = dt.date(2026, 11, 19), dt.date.fromisoformat(sys.argv[1])
dates = [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
status, _t, _m = RS.official_status(ro("/home/ubuntu/nba-engine/nba_news.sqlite"), dates)
lu = RS.lineups(ro("/home/ubuntu/nba-engine/nba_lineups.sqlite"), dates, {}, status)
out = {"status": [[d, pid, v["status"]] for (d, pid), v in status.items()],
       "lineups": {k: {"status": v["status"], "starters": [s[0] for s in v["starters"]], "inactive": [x[0] for x in v["inactive"]]} for k, v in lu.items()}}
json.dump(out, open("/tmp/lumin_check/pit.json", "w"))
print(len(out["status"]), "report rows,", len(out["lineups"]), "team lineups")
