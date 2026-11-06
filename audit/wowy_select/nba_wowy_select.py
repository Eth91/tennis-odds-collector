"""NBA_WOWY_SELECT_PREREG.md (b80d0b3e4f): C1-C7 on 2024-25 and 2025-26 (M1, carry-over) and at 2024-25 tip lines (M2).
    python3 select_test.py"""
import json
import random
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict

HERE = "/private/tmp/claude-501/-Users-ethandown-dev/6bcda0e4-ceef-45a9-9890-c43eb7a756a4/scratchpad/wowytest/"
SEASONS = {"2024-25": (HERE + "onoff_2024.sqlite", HERE + "m2425.sqlite"),
           "2025-26": (HERE + "onoff_2025.sqlite", "/Users/ethandown/nba-engine-proj/.projdata/vm_backup_20261103/nba_matchup.20261103.sqlite")}
ODDS = "/Users/ethandown/tennis-odds-collector/basketball_nba_odds_hist.sqlite"
ST = ("pts", "reb", "ast", "fga", "fta", "tov")
I = {k: i for i, k in enumerate(ST)}
GRP = {"PG": "G", "SG": "G", "SF": "F", "PF": "F", "C": "C"}


def ro(p):
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def events_for(season):
    on_db, m_db = SEASONS[season]
    con, m = ro(on_db), ro(m_db)
    games = con.execute("SELECT gid, date FROM games WHERE season = ? AND ok = 1 ORDER BY date, gid", (season,)).fetchall()
    lu = defaultdict(list)
    for gid, team, key, secs in con.execute("SELECT gid, team, lineup, secs FROM lineups"):
        lu[(gid, team)].append((frozenset(int(p) for p in key.split(",")), key, secs))
    ps = defaultdict(dict)
    for gid, team, key, pid, *v in con.execute(f"SELECT gid, team, lineup, pid, {', '.join(ST)} FROM pstats"):
        ps[(gid, team, key)][pid] = [x or 0 for x in v]
    slot = {(g, p): pos for g, p, pos in m.execute("SELECT gid, pid, pos FROM player_games WHERE starter = 1 AND pos IN ('PG','SG','SF','PF','C')")}
    out = []
    for team in sorted({t for (_, t) in lu}):
        tg = [g for g, _ in games if (g, team) in lu]
        date = dict(games)
        secs, gp = defaultdict(float), defaultdict(int)
        pair = defaultdict(lambda: [0.0, [0] * len(ST)])
        tot = defaultdict(lambda: [0.0, [0] * len(ST)])          # per-36 base: seconds and stats
        pg = defaultdict(lambda: [0] * len(ST))                   # per-game base: stats over his games
        starts = defaultdict(list)                                # pid -> his starting slots so far
        recent = []
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
            current = [y for y in gp if reg(y) and any(y in r for r in recent[-3:])]
            usg = lambda y: (tot[y][1][I["fga"]] + .44 * tot[y][1][I["fta"]] + tot[y][1][I["tov"]]) / tot[y][0] * 2160 if tot[y][0] else 0
            star = max(current, key=usg) if current else None
            grp = lambda p: GRP[Counter(starts[p]).most_common(1)[0][0]] if starts[p] else None
            for y in [y for y in current if y not in here]:
                for x in here:
                    if tot[x][0] < 300 * 60:
                        continue
                    on, off = pair[(x, y, "on")], pair[(x, y, "off")]
                    if off[0] < 60 * 60 or on[0] < 60 * 60:
                        continue
                    r = lambda c: [v / c[0] * 2160 for v in c[1]]
                    o, a = r(off), r(tot[x])
                    out.append({"season": season, "gid": g, "date": date[g], "team": team, "x": x, "y": y,
                                "gap": {k: o[I[k]] - a[I[k]] for k in ST}, "off_min": off[0] / 60,
                                "avg": {k: pg[x][I[k]] / gp[x] for k in ST}, "g": {k: gstat[x][I[k]] for k in ST},
                                "min_g": played[x] / 60, "star": y == star,
                                "same": grp(x) is not None and grp(x) == grp(y)})
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
                pg[p] = [a + b for a, b in zip(pg[p], gstat[p])]
                if (g, p) in slot:
                    starts[p].append(slot[(g, p)])
            recent.append(here)
    return out


CRIT = {  # name: (rule, market, side)
    "C1 trusted points split": (lambda e: e["off_min"] >= 300 and e["gap"]["pts"] >= 4, "pts", "over"),
    "C2 shot volume": (lambda e: e["off_min"] >= 300 and e["gap"]["fga"] >= 3, "pts", "over"),
    "C3 star out": (lambda e: e["star"] and e["off_min"] >= 200 and e["gap"]["fga"] >= 2, "pts", "over"),
    "C4 next man up": (lambda e: e["same"] and e["off_min"] >= 200 and e["gap"]["fga"] >= 2, "pts", "over"),
    "C5 assists": (lambda e: e["off_min"] >= 300 and e["gap"]["ast"] >= 2, "ast", "over"),
    "C6 rebounds": (lambda e: e["off_min"] >= 300 and e["gap"]["reb"] >= 2.5, "reb", "over"),
    "C7 mirror": (lambda e: e["off_min"] >= 300 and e["gap"]["pts"] <= -4, "pts", "under"),
}


def boot(rows_by_gid, stat, n=1000, seed=11):
    keys, rnd, out = list(rows_by_gid), random.Random(seed), []
    for _ in range(n):
        out.append(stat([r for k in (rnd.choice(keys) for _ in keys) for r in rows_by_gid[k]]))
    out = sorted(x for x in out if x is not None)
    return out[int(.025 * len(out))], out[int(.975 * len(out)) - 1]


def m1(ev):
    res = {}
    pop = [e for e in ev if e["min_g"] >= 12]
    for name, (rule, mk, side) in CRIT.items():
        sgn = 1 if side == "over" else -1
        exc = lambda e: sgn * (e["g"][mk] - e["avg"][mk])
        row = {}
        for s in SEASONS:
            sel = [exc(e) for e in pop if e["season"] == s and rule(e)]
            rest = [exc(e) for e in pop if e["season"] == s and not rule(e)]
            row[s] = {"n": len(sel), "sel": round(sum(sel) / len(sel), 2) if sel else None, "rest": round(sum(rest) / len(rest), 2),
                      "diff": round(sum(sel) / len(sel) - sum(rest) / len(rest), 2) if sel else None}
        by = defaultdict(list)
        for e in pop:
            by[e["gid"]].append((rule(e), exc(e)))

        def diff(rows):
            a = [x for f, x in rows if f]; b = [x for f, x in rows if not f]
            return sum(a) / len(a) - sum(b) / len(b) if a and b else None
        allrows = [r for v in by.values() for r in v]
        lo, hi = boot(by, diff)
        row["pooled"] = {"diff": round(diff(allrows), 2), "ci": [round(lo, 2), round(hi, 2)]}
        row["pass"] = all(row[s]["diff"] is not None and row[s]["diff"] > 0 for s in SEASONS) and lo > 0
        res[name] = row
    return res


def norm(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'’\-]", " ", n)
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv"))


def lines_2425():
    """{(gid, pid, market): (line, over price, under price, book)} at tip, FanDuel else DraftKings; and the match rate."""
    m = ro(SEASONS["2024-25"][1])
    games = {(d, hn.split()[-1]): g for g, d, hn in m.execute("SELECT gid, date, home_name FROM games")}
    names = defaultdict(dict)
    for g, pid, nm in m.execute("SELECT gid, pid, name FROM player_games"):
        names[g][norm(nm)] = pid
    q = ro(ODDS)
    MK = {"player_points": "pts", "player_assists": "ast", "player_rebounds": "reb"}
    raw = defaultdict(lambda: defaultdict(dict))
    seen = set(); hit = set()
    for d, home, book, mk, player, side, line, price in q.execute(
            "SELECT game_date, home_team, book, market, player, side, line, price FROM props WHERE snap_kind = 'tip' "
            "AND book IN ('fanduel', 'draftkings') AND market IN ('player_points', 'player_assists', 'player_rebounds') "
            "AND game_date BETWEEN '2024-10-22' AND '2025-04-13'"):
        g = games.get((d, home.split()[-1]))
        if not g:
            continue
        seen.add((g, player))
        pid = names[g].get(norm(player))
        if pid is None:
            continue
        hit.add((g, player))
        raw[(g, pid, MK[mk])][book].setdefault(line, {})[side.lower()] = price
    out = {}
    for k, books in raw.items():
        for b in ("fanduel", "draftkings"):
            two = [(abs(1 / v["over"] - 1 / v["under"]), ln, v) for ln, v in books.get(b, {}).items() if "over" in v and "under" in v]
            if two:
                _, ln, v = min(two)
                out[k] = (ln, v["over"], v["under"], b)
                break
    return out, len(hit) / max(1, len(seen))


def m2(ev, L):
    box = {}
    for g, pid, mins, pts, reb, ast in ro(SEASONS["2024-25"][1]).execute("SELECT gid, pid, min, pts, reb, ast FROM player_games"):
        box[(g, pid)] = (mins, {"pts": pts, "reb": reb, "ast": ast})
    res = {}
    pop = [e for e in ev if e["season"] == "2024-25"]
    for name, (rule, mk, side) in list(CRIT.items()) + [("baseline over pts", (lambda e: True, "pts", "over")),
                                                         ("baseline over ast", (lambda e: True, "ast", "over")),
                                                         ("baseline over reb", (lambda e: True, "reb", "over")),
                                                         ("baseline under pts", (lambda e: True, "pts", "under"))]:
        by = defaultdict(list)
        seen = set()
        for e in pop:
            k = (e["gid"], e["x"], mk)
            if not rule(e) or k not in L or k in seen:           # one bet a player-game-market (two teammates out)
                continue
            mins, st = box.get((e["gid"], e["x"]), (0, {}))
            if not mins or st.get(mk) is None:
                continue                                         # did not play: void
            seen.add(k)
            ln, po, pu, _ = L[k]
            v = st[mk]
            win = v > ln if side == "over" else v < ln
            ret = 0.0 if v == ln else (po if side == "over" else pu) - 1 if win else -1.0
            by[e["gid"]].append((win, ret))
        rows = [r for v in by.values() for r in v]
        if not rows:
            res[name] = {"n": 0}
            continue
        roi = lambda rs: sum(r for _, r in rs) / len(rs) if rs else None
        lo, hi = boot(by, roi)
        res[name] = {"n": len(rows), "hit": round(sum(w for w, _ in rows) / len(rows), 3), "roi": round(roi(rows), 3),
                     "ci": [round(lo, 3), round(hi, 3)]}
    return res


if __name__ == "__main__":
    ev = events_for("2024-25") + events_for("2025-26")
    print({s: sum(1 for e in ev if e["season"] == s) for s in SEASONS}, "events (all who played)", flush=True)
    r1 = m1(ev)
    L, rate = lines_2425()
    r2 = m2(ev, L)
    verdict = {}
    for name in CRIT:
        mm = r2[name]
        if mm.get("n") and mm["ci"][0] > 0:
            verdict[name] = "PASS"
        elif r1[name]["pass"] and mm.get("n") and mm["roi"] > .05:
            verdict[name] = "PROMISING"
        else:
            verdict[name] = "FAIL"
    json.dump({"m1": r1, "m2": r2, "match_rate": rate, "lines": len(L), "verdict": verdict}, open(HERE + "select_result.json", "w"), indent=1)
    print(f"name match rate {rate:.1%}, {len(L)} main lines")
    for name in CRIT:
        a = r1[name]
        print(f"{name}: M1 " + " | ".join(f"{s} n {a[s]['n']} sel {a[s]['sel']} rest {a[s]['rest']} diff {a[s]['diff']}" for s in SEASONS)
              + f" | pooled {a['pooled']} {'pass' if a['pass'] else 'no'}")
        print(f"    M2 {r2[name]} -> {verdict[name]}")
    for k, v in r2.items():
        if k.startswith("baseline"):
            print(f"{k}: {v}")
