"""Exploration on 2025-26 only (training): role-aware minutes vs V3. Pool approximated without injury reports."""
import sqlite3, sys, json, itertools
from collections import defaultdict
sys.path[:0] = [str(__import__("pathlib").Path(__file__).resolve().parents[2])]
import nba_role as RL
H = sys.argv[2] if len(sys.argv) > 2 else "minacc/"
SEASON = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
rd = RL.RoleData(H + "matchup.sqlite", H + "gamelogs.sqlite", SEASON)
m = sqlite3.connect(f"file:{H}matchup.sqlite?mode=ro", uri=True)
START = {(g, p) for g, p in m.execute("SELECT p.gid, p.pid FROM player_games p JOIN games g ON g.gid=p.gid WHERE g.season=? AND p.starter=1", (SEASON,))}
games = defaultdict(list)                       # team -> [(d, gid, box)]
for t, gs in rd.season.games.items():
    games[t] = gs
nxt_team = {}                                    # (pid, date) -> next game's team (any team) after date
by_pid = defaultdict(list)
for t, gs in games.items():
    for d, g, b in gs:
        for p, r in b.items():
            if r["min"]:
                by_pid[p].append((d, t))
for v in by_pid.values():
    v.sort()
rows = []
for t, gs in games.items():
    for i, (d, gid, box) in enumerate(gs):
        if i < 8:
            continue
        prior = gs[:i]
        played = {p for p, r in box.items() if r["min"]}
        last3 = {p for _d, _g, b in prior[-3:] for p, r in b.items() if r["min"]}
        nxt = gs[i + 1][2] if i + 1 < len(gs) else {}
        def avail(p):                            # not playing tonight: available if he plays the team's next game
            if p in played:
                return True
            return p in nxt and nxt[p]["min"] > 0
        pool = {p for p in last3 | played if avail(p)}
        # traded: his next game anywhere is for another team
        gone = (last3 - pool)
        spots = {x for x, n in rd.season.absences(t, d, gone).items() if n <= RL.SPOT_MAX}
        five = {p for p in played if (gid, p) in START}
        v3 = RL.project(rd.season, rd.priors, rd.groups, t, d, pool, spots, mode="v3")
        for p in pool:
            pm = [b[p]["min"] for _d, _g, b in prior if p in b and b[p]["min"]]
            his = [(g_, b[p]["min"]) for _d, g_, b in prior if p in b and b[p]["min"]]
            l10 = prior[-10:]
            rows.append({"gid": gid, "team": t, "pid": p, "a": box.get(p, {}).get("min") or 0.0, "st": p in five,
                         "v3": v3[p]["min"], "l5": v3[p]["base_min"],
                         "starts5": sum(1 for g_, _m in his[-5:] if (g_, p) in START), "n5": len(his[-5:]),
                         "s_last": [mn for g_, mn in his if (g_, p) in START][-5:], "b_last": [mn for g_, mn in his if (g_, p) not in START][-5:],
                         "pl10": sum(1 for _d, _g, b in l10 if p in b and b[p]["min"]) / len(l10),
                         "spots": sorted(spots), "npool": len(pool), "grp": rd.groups.get(p),
                         "xsh": {str(x): (sum(1 for _d, _g, b in [(dd, gg, bb) for dd, gg, bb in prior if p in bb and bb[p]["min"]][-5:] if x in b and b[x]["min"]) / max(1, min(5, len(pm)))) for x in spots},
                         "xs": [[x, RL.ewma([b[x]["min"] for _d, _g, b in prior if x in b and b[x]["min"]]) or 0.0, rd.groups.get(x)] for x in spots]})
json.dump(rows, open(f"rows_{SEASON}.json", "w"))
pl = [r for r in rows if r["a"] > 0]
print(SEASON, len(rows), "pool rows;", len(pl), "played; DNP among pool", round(1 - len(pl) / len(rows), 3))
mae = lambda rs, k: round(sum(abs(r[k] - r["a"]) for r in rs) / len(rs), 3)
bias = lambda rs, k: round(sum(r[k] - r["a"] for r in rs) / len(rs), 3)
for lab, rs in (("all", pl), ("starters", [r for r in pl if r["st"]]), ("bench", [r for r in pl if not r["st"]])):
    print(lab, len(rs), "V3", mae(rs, "v3"), bias(rs, "v3"), "L5", mae(rs, "l5"), bias(rs, "l5"))
