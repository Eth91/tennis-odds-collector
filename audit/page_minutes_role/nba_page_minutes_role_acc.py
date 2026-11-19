"""NBA_PAGE_MINUTES_ROLE_PREREG.md (bb6a1fa91d): RM vs V3 on 2026-27, 10-26 to 11-18, point in time.
    python3 nba_page_minutes_role_acc.py DATA_DIR      (matchup.sqlite, gamelogs.sqlite, pit.json from the VM)"""
import json, random, sqlite3, sys
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R)]
import nba_research as RS
import nba_role as RL
H = sys.argv[1].rstrip("/") + "/"
rd = RL.RoleData(H + "matchup.sqlite", H + "gamelogs.sqlite", "2026-27")
starts = RS.season_starts(H + "matchup.sqlite", "2026-27")
pit = json.load(open(H + "pit.json"))
status = defaultdict(dict)
for d, pid, s in pit["status"]:
    status[d][(d, pid)] = {"status": s}
lus = pit["lineups"]
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
for v in hist.values():
    v.sort()
rows, dnp, floor = [], [0, 0], 0
for gid, d, home, away in games:
    for team in (away, home):
        roster = {}
        for p, v in hist.items():
            last = [t for dd, t in v if dd < d]
            if last:
                roster[str(p)] = [last[-1], "", ""]
        e = lus.get(f"{d}|{team}")
        lu = {f"{d}|{team}": {"status": e["status"], "starters": [[p, "", ""] for p in e["starters"]], "inactive": [[p, ""] for p in e["inactive"]]}} if e else {}
        g1 = [{"date_et": d, "home": home, "away": away}]
        v3 = RS.projected_minutes(rd, g1, status[d], lu, roster).get(f"{d}|{team}")
        rm = RS.projected_minutes(rd, g1, status[d], lu, roster, model="role", starts=starts).get(f"{d}|{team}")
        if not v3:
            continue
        assert {r[0] for r in v3} == {r[0] for r in rm}                      # the same players in both
        rmm = {r[0]: r[2] for r in rm}
        five = set(e["starters"]) if e else set()
        act = actual[(gid, team)]
        for pid, _n, x3, l5, _st in v3:
            a = act.get(pid, 0.0)
            dnp[1] += 1
            if a <= 0:
                dnp[0] += 1
                continue
            floor += rmm[pid] == 0.0
            rows.append({"gid": gid, "team": team, "pid": pid, "starter": pid in five, "a": a, "V3": x3, "RM": rmm[pid], "L5": l5})
n_games = len(games)
print(f"{n_games} games, {len(rows)} player-games played; DNP among the available {dnp[0]}/{dnp[1]} = {dnp[0] / dnp[1]:.1%}; RM at the 0 floor: {floor}")
M = ("V3", "RM", "L5")
st = lambda rs: {k: (round(sum(abs(r[k] - r["a"]) for r in rs) / len(rs), 2), round(sum(r[k] - r["a"] for r in rs) / len(rs), 2)) for k in M}
res = {"n_games": n_games, "dnp": dnp, "floor": floor}
for name, sel in (("all", lambda r: True), ("starters", lambda r: r["starter"]), ("bench", lambda r: not r["starter"])):
    rs = [r for r in rows if sel(r)]
    res[name] = {"n": len(rs), **st(rs)}
    print(name, len(rs), "MAE (bias):", st(rs))
by = defaultdict(list)
for r in rows:
    by[r["gid"]].append(abs(r["RM"] - r["a"]) - abs(r["V3"] - r["a"]))
keys, rnd, bs = list(by), random.Random(5), []
for _ in range(2000):
    s = [x for k in (rnd.choice(keys) for _ in keys) for x in by[k]]
    bs.append(sum(s) / len(s))
bs.sort()
diff = sum(x for v in by.values() for x in v) / len(rows)
res["RM_minus_V3"] = {"mae_diff": round(diff, 3), "ci": [round(bs[50], 3), round(bs[1949], 3)]}
print("MAE(RM) - MAE(V3):", res["RM_minus_V3"])
ok = diff < 0 and bs[1949] < 0 and res["starters"]["RM"][0] <= res["starters"]["V3"][0]
res["decision"] = "RM" if ok else "V3"
print("decision:", res["decision"])
json.dump(res, open(Path(__file__).with_name("result.20261119.json"), "w"), indent=1)
json.dump(rows, open(H + "role_rows.json", "w"))
