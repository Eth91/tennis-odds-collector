"""NBA_PAGE_MINUTES_PREREG.md (b1c0925655): V3 vs V3-P vs L5 on 2026-27, 10-26 to 11-18, point in time."""
import json, random, sqlite3, sys
from collections import defaultdict
sys.path[:0] = ["/Users/ethandown/nba-engine-lumin"]
import nba_research as RS
import nba_role as RL
H = "/private/tmp/claude-501/-Users-ethandown-dev/6bcda0e4-ceef-45a9-9890-c43eb7a756a4/scratchpad/minacc/"
rd = RL.RoleData(H + "matchup.sqlite", H + "gamelogs.sqlite", "2026-27")
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
hist = defaultdict(list)                                  # pid -> [(date, team)] he played
for team, gs in rd.season.games.items():
    for d, g, b in gs:
        for p, r in b.items():
            if r["min"]:
                hist[p].append((d, team))
for v in hist.values():
    v.sort()
rows, dnp, n_games = [], [0, 0], 0
for gid, d, home, away in games:
    n_games += 1
    for team in (away, home):
        roster = {}
        for p, v in hist.items():
            last = [t for dd, t in v if dd < d]
            if last:
                roster[str(p)] = [last[-1], "", ""]
        e = lus.get(f"{d}|{team}")
        lu = {f"{d}|{team}": {"status": e["status"], "starters": [[p, "", ""] for p in e["starters"]], "inactive": [[p, ""] for p in e["inactive"]]}} if e else {}
        out = RS.projected_minutes(rd, [{"date_et": d, "home": home, "away": away}], status[d], lu, roster).get(f"{d}|{team}")
        if not out:
            continue
        prior = rd.season.before(team, d)
        last10 = prior[-10:]
        last3 = rd.season.roster(team, d)
        starters = set(e["starters"]) if e else set()
        P = {}
        for pid, *_ in out:
            P[pid] = 1.0 if pid in starters or pid not in last3 else sum(1 for _d, _g, b in last10 if pid in b and b[pid]["min"]) / len(last10)
        c = 240 / sum(P[r[0]] * r[2] for r in out)
        act = actual[(gid, team)]
        for pid, _n, v3, l5, _st in out:
            a = act.get(pid, 0.0)
            dnp[1] += 1
            if a <= 0:
                dnp[0] += 1
                continue
            rows.append({"gid": gid, "starter": pid in starters if e else None, "a": a, "V3": v3, "V3-P": min(40.0, v3 * c), "L5": l5})
print(f"{n_games} games, {len(rows)} player-games played; DNP among the available {dnp[0]}/{dnp[1]} = {dnp[0] / dnp[1]:.1%}")
M = ("V3", "V3-P", "L5")
def stats(rs):
    return {k: (round(sum(abs(r[k] - r["a"]) for r in rs) / len(rs), 2), round(sum(r[k] - r["a"] for r in rs) / len(rs), 2)) for k in M}
res = {"n_games": n_games, "dnp": dnp}
for name, sel in (("all", lambda r: True), ("starters", lambda r: r["starter"] is True), ("bench", lambda r: r["starter"] is False)):
    rs = [r for r in rows if sel(r)]
    res[name] = {"n": len(rs), **stats(rs)}
    print(name, len(rs), "MAE (bias):", {k: v for k, v in stats(rs).items()})
by = defaultdict(list)
for r in rows:
    by[r["gid"]].append(abs(r["V3-P"] - r["a"]) - abs(r["V3"] - r["a"]))
keys, rnd, bs = list(by), random.Random(5), []
for _ in range(2000):
    s = [x for k in (rnd.choice(keys) for _ in keys) for x in by[k]]
    bs.append(sum(s) / len(s))
bs.sort()
diff = sum(x for v in by.values() for x in v) / len(rows)
res["V3P_minus_V3"] = {"mae_diff": round(diff, 3), "ci": [round(bs[50], 3), round(bs[1949], 3)]}
print("MAE(V3-P) - MAE(V3):", res["V3P_minus_V3"])
ok = diff < 0 and bs[1949] < 0 and res["starters"]["V3-P"][0] <= res["starters"]["V3"][0]
res["decision"] = "V3-P" if ok else "V3"
print("decision:", res["decision"])
json.dump(res, open(H + "acc_result.json", "w"), indent=1)
