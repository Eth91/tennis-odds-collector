"""NBA_WOWY_PER36_PREREG.md (e482219708): WOWY per-36 x projected minutes, 2023-24 / 2024-25 / 2025-26.
    python3 per36_test.py"""
import json
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/Users/ethandown/nba-engine")
import nba_role as NR                                    # read-only use of the engine's role model

HERE = "/private/tmp/claude-501/-Users-ethandown-dev/6bcda0e4-ceef-45a9-9890-c43eb7a756a4/scratchpad/wowytest/"
SEASONS = {"2023-24": (HERE + "onoff_2023.sqlite", HERE + "m2324.sqlite", ("2023-10-24", "2024-04-14")),
           "2024-25": (HERE + "onoff_2024.sqlite", HERE + "m2425.sqlite", ("2024-10-22", "2025-04-13")),
           "2025-26": (HERE + "onoff_2025.sqlite",
                       "/Users/ethandown/nba-engine-proj/.projdata/vm_backup_20261103/nba_matchup.20261103.sqlite", None)}
LINE_SEASONS = ("2023-24", "2024-25")
GAMELOGS = "/Users/ethandown/nba-engine-proj/.projdata/nba_gamelogs.sqlite"
ODDS = "/Users/ethandown/tennis-odds-collector/basketball_nba_odds_hist.sqlite"
ST = ("pts", "reb", "ast")
MK = ("pts", "reb", "ast")
K = {"pts": .17, "reb": .15, "ast": .32}
T = {"pts": (1, 2, 3), "reb": (.5, 1, 1.5), "ast": (.5, 1, 1.5)}
RATES, MINS = ("W", "O", "S"), ("E", "WO", "L3", "L5")


def ro(p):
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def engine_minutes():
    """{(season, team, date): {pid: {min, pts, reb, ast}}} from nba_role.project v3 for every team-game with a
    rotation player out (the engine's tip_props conventions: active = last-3 roster who play, absent = last-3
    rotation players who don't)."""
    rows, groups = NR.load(GAMELOGS)
    out = {}
    for s in SEASONS:
        season, priors = NR.Season(rows[s]), NR.Priors(rows[NR.PREV[s]], groups)
        for team, games in season.games.items():
            for d, _g, box in games:
                played = {p for p, r in box.items() if r["min"]}
                last3 = season.roster(team, d)
                absent = set(season.absences(team, d, last3 - played))
                if not absent:
                    continue
                proj = NR.project(season, priors, groups, team, d, last3 & played, absent, mode="v3")
                out[(s, team, d)] = {p: {k: v[k] for k in ("min",) + ST} for p, v in proj.items()}
    return out


def events_for(season, eng):
    on_db, m_db, _ = SEASONS[season]
    con = ro(on_db)
    games = con.execute("SELECT gid, date FROM games WHERE season = ? AND ok = 1 ORDER BY date, gid", (season,)).fetchall()
    date = dict(games)
    lu = defaultdict(list)
    for gid, team, key, secs in con.execute("SELECT gid, team, lineup, secs FROM lineups"):
        lu[(gid, team)].append((frozenset(int(p) for p in key.split(",")), key, secs))
    ps = defaultdict(dict)
    for gid, team, key, pid, *v in con.execute(f"SELECT gid, team, lineup, pid, {', '.join(ST)} FROM pstats"):
        ps[(gid, team, key)][pid] = [x or 0 for x in v]
    out, eng_hit, eng_try = [], 0, 0
    for team in sorted({t for (_, t) in lu}):
        tg = [g for g, _ in games if (g, team) in lu]
        secs, gp = defaultdict(float), defaultdict(int)
        pair = defaultdict(lambda: [0.0, [0] * len(ST)])
        tot = defaultdict(lambda: [0.0, [0] * len(ST)])
        hist = []                                        # [(set who played, {pid: minutes})] in order
        for g in tg:
            units = lu[(g, team)]
            played = defaultdict(float)
            gstat = defaultdict(lambda: [0] * len(ST))
            for five, key, s in units:
                for p in five:
                    played[p] += s
                    st = ps[(g, team, key)].get(p, [0] * len(ST))
                    gstat[p] = [a + b for a, b in zip(gstat[p], st)]
            here = {p for p, s in played.items() if s > 0}
            reg = lambda y: gp[y] >= 10 and secs[y] / 60 / gp[y] >= 20
            outs = [y for y in gp if reg(y) and y not in here and any(y in h for h, _ in hist[-3:])]
            proj = eng.get((season, team, date[g]))
            for x in here:
                if tot[x][0] < 300 * 60:
                    continue
                ok = [y for y in outs if pair[(x, y, "off")][0] >= 3600 and pair[(x, y, "on")][0] >= 3600]
                if not ok:
                    continue
                y = max(ok, key=lambda y: secs[y] / gp[y])        # two or more out: the biggest absence
                r36 = lambda c: {k: c[1][i] / c[0] * 2160 for i, k in enumerate(ST)}
                W, O = r36(pair[(x, y, "off")]), r36(tot[x])
                S = {k: O[k] + K[k] * (W[k] - O[k]) for k in ST}
                mine = [m[x] for h, m in hist if x in h]
                wo = [m[x] for h, m in hist if x in h and y not in h]
                eng_try += 1
                e_ = proj.get(x) if proj else None
                eng_hit += e_ is not None
                mins = {"E": e_["min"] if e_ else None, "WO": sum(wo) / len(wo) if len(wo) >= 2 else None,
                        "L3": sum(mine[-3:]) / 3 if len(mine) >= 3 else None,
                        "L5": sum(mine[-5:]) / 5 if len(mine) >= 5 else None}
                out.append({"season": season, "gid": g, "date": date[g], "team": team, "x": x, "y": y,
                            "rate": {"W": W, "O": O, "S": S}, "mins": mins, "R": {k: e_[k] for k in ST} if e_ else None,
                            "g": {k: gstat[x][i] for i, k in enumerate(ST)}, "min_g": played[x] / 60,
                            "off_min": pair[(x, y, "off")][0] / 60})
            for five, key, s in units:
                st_by = ps[(g, team, key)]
                for x in five:
                    st = st_by.get(x, [0] * len(ST))
                    tot[x][0] += s
                    tot[x][1] = [a + b for a, b in zip(tot[x][1], st)]
                    for y in here | set(gp):
                        if y != x:
                            c = pair[(x, y, "on" if y in five else "off")]
                            c[0] += s
                            c[1] = [a + b for a, b in zip(c[1], st)]
            for p in here:
                secs[p] += played[p]
                gp[p] += 1
            hist.append((here, {p: played[p] / 60 for p in here}))
    return out, (eng_hit, eng_try)


def norm(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'’\-]", " ", n)
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv"))


def lines(season):
    """{(gid, pid, market): (line, over price, under price, book)} at tip, FanDuel else DraftKings; and the match rate."""
    _, m_db, (d0, d1) = SEASONS[season]
    m = ro(m_db)
    games = {(d, hn.split()[-1]): g for g, d, hn in m.execute("SELECT gid, date, home_name FROM games")}
    names = defaultdict(dict)
    for g, pid, nm in m.execute("SELECT gid, pid, name FROM player_games"):
        names[g][norm(nm)] = pid
    q = ro(ODDS)
    mk_of = {"player_points": "pts", "player_assists": "ast", "player_rebounds": "reb"}
    raw = defaultdict(lambda: defaultdict(dict))
    seen, hit = set(), set()
    for d, home, book, mk, player, side, line, price in q.execute(
            "SELECT game_date, home_team, book, market, player, side, line, price FROM props WHERE snap_kind = 'tip' "
            "AND book IN ('fanduel', 'draftkings') AND market IN ('player_points', 'player_assists', 'player_rebounds') "
            "AND game_date BETWEEN ? AND ?", (d0, d1)):
        g = games.get((d, home.split()[-1]))
        if not g:
            continue
        seen.add((g, player))
        pid = names[g].get(norm(player))
        if pid is None:
            continue
        hit.add((g, player))
        raw[(g, pid, mk_of[mk])][book].setdefault(line, {})[side.lower()] = price
    out = {}
    for k, books in raw.items():
        for b in ("fanduel", "draftkings"):
            two = [(abs(1 / v["over"] - 1 / v["under"]), ln, v) for ln, v in books.get(b, {}).items() if "over" in v and "under" in v]
            if two:
                _, ln, v = min(two)
                out[k] = (ln, v["over"], v["under"], b)
                break
    return out, len(hit) / max(1, len(seen)), len({g for g, _ in seen})


def proj(e, r, m, k):
    return None if e["mins"][m] is None else e["rate"][r][k] * e["mins"][m] / 36


RNG = np.random.default_rng(13)


def boot_mean(gids, vals, n=1000):
    """95% interval of the mean of vals, resampling whole games."""
    u, gi = np.unique(np.asarray(gids), return_inverse=True)
    c = RNG.multinomial(len(u), np.full(len(u), 1 / len(u)), size=n)[:, gi]
    v = np.asarray(vals, float)
    b = np.sort((c * v).sum(1) / c.sum(1))
    return float(b[int(.025 * n)]), float(b[int(.975 * n) - 1])


def accuracy(ev, L):
    res = {"minutes": {}, "mae": {}, "helps": {}}
    full = [e for e in ev if all(e["mins"][m] is not None for m in MINS)]
    for s in SEASONS:
        rows = [e for e in full if e["season"] == s]
        res["minutes"][s] = {"n": len(rows), **{m: round(sum(abs(e["mins"][m] - e["min_g"]) for e in rows) / len(rows), 2) for m in MINS},
                             "bias": {m: round(sum(e["mins"][m] - e["min_g"] for e in rows) / len(rows), 2) for m in MINS},
                             "actual": round(sum(e["min_g"] for e in rows) / len(rows), 1)}
    for k in MK:
        pop = {s: [e for e in full if e["season"] == s and (s not in LINE_SEASONS or (e["gid"], e["x"], k) in L)] for s in SEASONS}
        res["mae"][k] = {}
        for s, rows in pop.items():
            row = {"n": len(rows)}
            for r in RATES:
                for m in MINS:
                    err = [proj(e, r, m, k) - e["g"][k] for e in rows]
                    row[r + "x" + m] = [round(sum(map(abs, err)) / len(err), 3), round(sum(err) / len(err), 2)]
            rr = [e for e in rows if e["R"]]
            row["R engine"] = round(sum(abs(e["R"][k] - e["g"][k]) for e in rr) / len(rr), 3)
            if s in LINE_SEASONS:
                row["line"] = round(sum(abs(L[(e["gid"], e["x"], k)][0] - e["g"][k]) for e in rows) / len(rows), 3)
            res["mae"][k][s] = row
        res["helps"][k] = {}
        for m in MINS:
            for r in ("W", "S"):
                per = {s: res["mae"][k][s][r + "x" + m][0] - res["mae"][k][s]["Ox" + m][0] for s in SEASONS}
                allr = [e for s in SEASONS for e in pop[s]]
                d = [abs(proj(e, r, m, k) - e["g"][k]) - abs(proj(e, "O", m, k) - e["g"][k]) for e in allr]
                lo, hi = boot_mean([e["season"] + e["gid"] for e in allr], d)
                res["helps"][k][f"{r} vs O, {m}"] = {"by_season": {s: round(v, 3) for s, v in per.items()},
                                                    "pooled": round(sum(d) / len(d), 3), "ci": [round(lo, 3), round(hi, 3)],
                                                    "helps": all(v < 0 for v in per.values()) and hi < 0}
    return res


def bets(ev, L, s, combo):
    r, m, k, t, side = combo
    out = []
    for e in ev:
        key = (e["gid"], e["x"], k)
        if e["season"] != s or key not in L:
            continue
        p = proj(e, r, m, k)
        if p is None:
            continue
        ln, po, pu, _ = L[key]
        if (side == "over" and p - ln >= t) or (side == "under" and ln - p >= t):
            v = e["g"][k]
            win = v > ln if side == "over" else v < ln
            out.append((e["gid"], 0.0 if v == ln else ((po if side == "over" else pu) - 1 if win else -1.0), win, v != ln))
    return out


def summ(b, ci=False):
    if not b:
        return {"n": 0}
    rets = [x[1] for x in b]
    dec = [x for x in b if x[3]]
    row = {"n": len(b), "hit": round(sum(x[2] for x in dec) / max(1, len(dec)), 3), "roi": round(sum(rets) / len(rets), 3)}
    if ci:
        lo, hi = boot_mean([x[0] for x in b], rets)
        row["ci"] = [round(lo, 3), round(hi, 3)]
    return row


if __name__ == "__main__":
    eng = engine_minutes()
    ev, cover = [], {}
    for s in SEASONS:
        e_, c_ = events_for(s, eng)
        ev += e_
        cover[s] = c_
    print({s: sum(1 for e in ev if e["season"] == s) for s in SEASONS}, "events; engine coverage", cover, flush=True)
    print("minutes source present:", {s: {m: sum(1 for e in ev if e["season"] == s and e["mins"][m] is not None) for m in MINS} for s in SEASONS})
    L, info = {}, {}
    for s in LINE_SEASONS:
        l_, rate, ng = lines(s)
        L.update(l_)
        info[s] = {"lines": len(l_), "match_rate": round(rate, 4), "games_with_lines": ng}
    print("lines", info, flush=True)
    A = accuracy(ev, L)
    combos = [(r, m, k, t, side) for r in RATES for m in MINS for k in MK for t in T[k] for side in ("over", "under")]
    disc = {c: summ(bets(ev, L, "2023-24", c)) for c in combos}
    ranked = sorted((c for c in combos if disc[c]["n"] >= 100 and disc[c]["roi"] > 0), key=lambda c: -disc[c]["roi"])
    carried = ranked[:3]
    conf, verdict = {}, {}
    for c in carried:
        conf[c] = summ(bets(ev, L, "2024-25", c), ci=True)
        cc = conf[c]
        verdict[c] = "PASS" if cc["n"] and cc["ci"][0] > 0 else "PROMISING" if cc["n"] and cc["roi"] > .03 else "FAIL"
    wrows = {c: {"2023-24": disc[c], "2024-25": summ(bets(ev, L, "2024-25", c))} for c in combos if c[0] == "W"}
    base = {}
    for s in LINE_SEASONS:
        for k in MK:
            for side in ("over", "under"):
                b = []
                for e in ev:
                    key = (e["gid"], e["x"], k)
                    if e["season"] == s and key in L:
                        ln, po, pu, _ = L[key]
                        v = e["g"][k]
                        win = v > ln if side == "over" else v < ln
                        b.append((e["gid"], 0.0 if v == ln else ((po if side == "over" else pu) - 1 if win else -1.0), win, v != ln))
                base[f"{s} {k} {side}"] = summ(b)
    name = lambda c: f"{c[0]}x{c[1]} {c[2]} {c[4]} T{c[3]}"
    res = {"events": {s: sum(1 for e in ev if e["season"] == s) for s in SEASONS}, "engine_cover": cover, "lines": info,
           "accuracy": A, "discovery_top10": [[name(c), disc[c]] for c in ranked[:10]],
           "n_disc_qualifying": len(ranked), "carried": {name(c): {"2023-24": disc[c], "2024-25": conf[c], "verdict": verdict[c]} for c in carried},
           "W_all": {name(c): v for c, v in wrows.items()}, "baseline": base}
    json.dump(res, open(HERE + "per36_result.json", "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("events", "engine_cover", "lines")}))
    print("minutes MAE (bias), all-four events:", json.dumps(A["minutes"]))
    for k in MK:
        for s, row in A["mae"][k].items():
            print(k, s, "n", row["n"], "line", row.get("line"), "R", row["R engine"],
                  " ".join(f"{r}x{m} {row[r + 'x' + m][0]:.2f}" for r in RATES for m in MINS))
        for n_, h in A["helps"][k].items():
            print("   ", k, n_, h)
    print("discovery qualifying", len(ranked))
    for n_, v in res["discovery_top10"]:
        print("  disc", n_, v)
    for n_, v in res["carried"].items():
        print("CARRIED", n_, v)
    for n_, v in base.items():
        print("baseline", n_, v)
