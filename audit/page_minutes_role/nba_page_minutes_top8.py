"""NBA_PAGE_MINUTES_ROLE_PREREG.md, the user's choice (8f2e424a4f): the most accurate model for each team's top 8.
    python3 nba_page_minutes_top8.py DATA_DIR      (matchup.sqlite, gamelogs.sqlite, pit.json from the VM)"""
import json, random, sqlite3, sys
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R)]
import nba_research as RS
import nba_role as RL
H = sys.argv[1].rstrip("/") + "/"
tab = lambda f: {tuple(json.loads(k.replace("(", "[").replace(")", "]"))): v for k, v in json.load(open(Path(__file__).with_name(f))).items()}
c1 = tab("p_2026_h1.json")                                 # RM2h: the table from 10-26 to 11-06, smoothed as RM2's
col = {j: sum(v[0] for k, v in c1.items() if k[1] == j) / sum(v[1] for k, v in c1.items() if k[1] == j) for j in (0, 1, 2)}
RM2H_P = {k: round(v[0] / v[1] if v[1] >= 50 else col[k[1]], 3) for k, v in c1.items()}
print("RM2h table", dict(sorted(RM2H_P.items())))
rd = RL.RoleData(H + "matchup.sqlite", H + "gamelogs.sqlite", "2026-27")
starts = RS.season_starts(H + "matchup.sqlite", "2026-27")
pit = json.load(open(H + "pit.json"))
status = defaultdict(dict)
for d, pid, s in pit["status"]:
    status[d][(d, pid)] = {"status": s}
m = sqlite3.connect(f"file:{H}matchup.sqlite?mode=ro", uri=True)
games = m.execute("SELECT gid, date, home, away FROM games WHERE season = '2026-27' AND date BETWEEN '2026-10-26' AND '2026-11-18' ORDER BY date, gid").fetchall()
actual = defaultdict(dict)
for gid, team, pid, mn in m.execute("SELECT gid, team, pid, min FROM player_games"):
    actual[(gid, team)][pid] = mn or 0.0
hist = defaultdict(list)
for team, gs in rd.season.games.items():
    for d, g, b in gs:
        for p, r in b.items():
            if r["min"]:
                hist[p].append((d, team))
M = ("V3", "RM", "RM2", "RM2h", "L5")
rows = []
for gid, d, home, away in games:
    for team in (away, home):
        roster = {str(p): [[t for dd, t in v if dd < d][-1], "", ""] for p, v in hist.items() if any(dd < d for dd, _t in v)}
        e = pit["lineups"][f"{d}|{team}"]
        lu = {f"{d}|{team}": {"status": e["status"], "starters": [[p, "", ""] for p in e["starters"]], "inactive": [[p, ""] for p in e["inactive"]]}}
        g1, sd = [{"date_et": d, "home": home, "away": away}], status[d]
        v3 = RS.projected_minutes(rd, g1, sd, lu, roster).get(f"{d}|{team}")
        if not v3:
            continue
        got = {"RM": RS.projected_minutes(rd, g1, sd, lu, roster, model="role", starts=starts),
               "RM2": RS.projected_minutes(rd, g1, sd, lu, roster, model="role", starts=starts, chance_table=RS.RM2_P),
               "RM2h": RS.projected_minutes(rd, g1, sd, lu, roster, model="role", starts=starts, chance_table=RM2H_P)}
        got = {k: {r[0]: r[2] for r in v[f"{d}|{team}"]} for k, v in got.items()}
        prior = rd.season.before(team, d)
        avg = {}
        for pid, *_ in v3:
            mins = [b[pid]["min"] for _d, _g, b in prior if pid in b and b[pid]["min"]]
            avg[pid] = sum(mins) / len(mins) if mins else 0.0
        rank = {pid: i for i, pid in enumerate(sorted(avg, key=lambda p: (-avg[p], p)))}
        act = actual[(gid, team)]
        for pid, _n, x3, l5, _st in v3:
            a = act.get(pid, 0.0)
            if a > 0 and rank[pid] < 8:
                rows.append({"gid": gid, "date": d, "rank": rank[pid], "a": a, "V3": x3, "L5": l5, **{k: got[k][pid] for k in got}})
def table(rs, lab):
    out = {"n": len(rs)}
    for k in M:
        out[k] = (round(sum(abs(r[k] - r["a"]) for r in rs) / len(rs), 3), round(sum(r[k] - r["a"] for r in rs) / len(rs), 2))
    print(lab, out)
    return out
def vs_v3(rs, k):
    by = defaultdict(list)
    for r in rs:
        by[r["gid"]].append(abs(r[k] - r["a"]) - abs(r["V3"] - r["a"]))
    keys, rnd, bs = list(by), random.Random(5), []
    for _ in range(2000):
        s = [x for g in (rnd.choice(keys) for _ in keys) for x in by[g]]
        bs.append(sum(s) / len(s))
    bs.sort()
    return round(sum(x for v in by.values() for x in v) / len(rs), 3), [round(bs[50], 3), round(bs[1949], 3)]
res = {}
late = [r for r in rows if r["date"] >= "2026-11-07"]
res["late_top8"] = table(late, "11-07 to 11-18, top 8 (decides):")
res["late_top7"] = table([r for r in late if r["rank"] < 7], "11-07 to 11-18, top 7:")
res["all_top8"] = table(rows, "10-26 to 11-18, top 8 (RM2 in-sample):")
res["all_top7"] = table([r for r in rows if r["rank"] < 7], "10-26 to 11-18, top 7:")
res["late_vs_V3"] = {k: vs_v3(late, k) for k in M if k != "V3"}
res["all_vs_V3"] = {k: vs_v3(rows, k) for k in M if k != "V3"}
print("minus V3, 11-07 to 11-18:", res["late_vs_V3"])
print("minus V3, full window:", res["all_vs_V3"])
best = min(M, key=lambda k: res["late_top8"][k][0])
res["decision"] = "RM2" if best == "RM2h" else best
res["late_games"] = len({r["gid"] for r in late})
print("late games", res["late_games"], "| decision: the page shows", res["decision"])
json.dump(res, open(Path(__file__).with_name("result_top8.20261120.json"), "w"), indent=1)
