"""RM2's bench chance of playing, fitted on 2026-27's real pool (10-26 to 11-18: the reports and inactive lists, as
the page builds it). RM2 is tested on games from 11-19 on only (NBA_PAGE_MINUTES_ROLE_PREREG.md, RM2).
    python3 fit_2026_p.py DATA_DIR [END_DATE OUT_NAME]     (RM2h: 2026-11-06 p_2026_h1.json)"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[2])]
import nba_research as RS
import nba_role as RL
H = sys.argv[1].rstrip("/") + "/"
END, OUT = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("2026-11-18", "p_2026.json")
rd = RL.RoleData(H + "matchup.sqlite", H + "gamelogs.sqlite", "2026-27")
starts = RS.season_starts(H + "matchup.sqlite", "2026-27")
pit = json.load(open(H + "pit.json"))
status = defaultdict(dict)
for d, pid, s in pit["status"]:
    status[d][(d, pid)] = {"status": s}
m = sqlite3.connect(f"file:{H}matchup.sqlite?mode=ro", uri=True)
games = m.execute("SELECT gid, date, home, away FROM games WHERE season = '2026-27' AND date BETWEEN '2026-10-26' AND ? ORDER BY date, gid", (END,)).fetchall()
played = defaultdict(set)
for gid, team, pid, mn in m.execute("SELECT gid, team, pid, min FROM player_games"):
    if mn:
        played[(gid, team)].add(pid)
hist = defaultdict(list)
for team, gs in rd.season.games.items():
    for d, g, b in gs:
        for p, r in b.items():
            if r["min"]:
                hist[p].append((d, team))
cnt = defaultdict(lambda: [0, 0])
for gid, d, home, away in games:
    for team in (away, home):
        roster = {str(p): [[t for dd, t in v if dd < d][-1], "", ""] for p, v in hist.items() if any(dd < d for dd, _t in v)}
        e = pit["lineups"].get(f"{d}|{team}")
        lu = {f"{d}|{team}": {"status": e["status"], "starters": [[p, "", ""] for p in e["starters"]], "inactive": [[p, ""] for p in e["inactive"]]}}
        out = RS.projected_minutes(rd, [{"date_et": d, "home": home, "away": away}], status[d], lu, roster, model="role", starts=starts).get(f"{d}|{team}")
        if not out:
            continue
        prior = rd.season.before(team, d)
        l10 = prior[-10:]
        for pid, _n, _m, l5, _st in out:
            if pid in e["starters"]:
                continue
            pl10 = sum(1 for _d, _g, b in l10 if pid in b and b[pid]["min"]) / len(l10)
            k = (min(int(pl10 * 10) // 3, 3), 0 if l5 < 10 else 1 if l5 < 20 else 2)
            cnt[k][0] += pid in played[(gid, team)]
            cnt[k][1] += 1
print({k: (round(v[0] / v[1], 3), v[1]) for k, v in sorted(cnt.items())})
json.dump({str(k): [v[0], v[1]] for k, v in sorted(cnt.items())}, open(Path(__file__).with_name(OUT), "w"))
