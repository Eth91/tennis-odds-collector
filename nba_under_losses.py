#!/usr/bin/env python3
"""NBA_UNDER_PREREG.md amendment 8: why the unders lose. Features known at tip - 30 for every UNDER20 flag 20%+ below
the line (under -150 or better, not threes); bins whose ROI trails on 2023-24 are tested on 2024-25. Mac only.

    python3 nba_under_losses.py
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / ".projdata" / "under_losses_result.json"
GAP, SURE, TOP = 0.08, 0.95, 5
PASS_KEPT, PASS_PING, PASS_WIDE = 0.02, 0.08, 0.04
NUMERIC = ("A1 V3 - last-10 min", "A2 last game min - V3", "A3 last-3 min - V3", "A4 sd of last-10 min", "A5 games this season",
           "B1 this season's share of rate", "B2 last-5 per-min / our rate", "B3 line / season avg", "B4 line / last-5 avg",
           "B5 under rate at this line, last 10", "C1 under price", "C2 book no-vig over", "C3 MGM/Caesars line - ours",
           "C4 % below the line", "C5 line", "D1 team implied points", "D2 implied spread", "D3 implied spread size",
           "D4 rest days", "D5 team game index", "E1 opp allowed to his group / league", "E2 both teams' shot volume")
BINARY = ("A6 starts tonight", "A7 Capela-type bump", "D4 back-to-back")
rng = np.random.default_rng(11)


def other_books(M, MR, BOOST, books=("betmgm", "williamhill_us")):
    """{(date, pid, market): [main line per book]}: each book's rung with the over priced nearest even."""
    g = sqlite3.connect(f"file:{M.GAMELOGS}?mode=ro", uri=True)
    name2pid = {MR.norm(nm): pid for pid, nm in g.execute("SELECT DISTINCT player_id, player FROM logs_full")}
    o = sqlite3.connect(f"file:{M.ODDS}?mode=ro", uri=True)
    raw = defaultdict(lambda: defaultdict(dict))
    q = ("SELECT game_date, player, market, line, side, price, book FROM props WHERE price IS NOT NULL AND line IS NOT NULL "
         "AND book IN (%s) AND market IN (%s)" % (",".join("?" * len(books)), ",".join("?" * len(BOOST.ODDS_MARKETS))))
    for d, pl, m, line, side, price, book in o.execute(q, tuple(books) + tuple(BOOST.ODDS_MARKETS)):
        pid = name2pid.get(MR.norm(pl))
        if pid is not None:
            raw[(d, pid, BOOST.ODDS_MARKETS[m], book)].setdefault(float(line), {})[side] = float(price)
    out = defaultdict(list)
    for (d, pid, mk, _b), lb in raw.items():
        two = [(abs(v["over"] - 2.0), ln) for ln, v in lb.items() if "over" in v and "under" in v]
        if two:
            out[(d, pid, mk)].append(min(two)[1])
    return out


def opponent_context(rows_db, s, groups):
    """(opp, allowed, volume): gid -> {team: opponent}; (team, date) -> {group: {stat: per game}} that the team allowed
    this season before the date, and the league's per team-game; (team, date) -> its FGA + 0.44 FTA per game before."""
    by_game = defaultdict(lambda: defaultdict(list))
    for r in rows_db[s]:
        if r["min"]:
            by_game[(r["date"], r["gid"])][r["team"]].append(r)
    opp, allowed, volume = {}, {}, {}
    cum = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))    # team -> group -> stat (allowed)
    games = defaultdict(int)
    vol = defaultdict(float)
    league = defaultdict(lambda: defaultdict(float))
    lg_games = 0
    dates = sorted({d for d, _g in by_game})
    for d in dates:
        todays = [(g, t) for (dd, g), t in by_game.items() if dd == d]
        for g, teams in todays:
            if len(teams) != 2:
                continue
            a, b = tuple(teams)
            opp[g] = {a: b, b: a}
            for t in (a, b):
                allowed[(t, d)] = ({gr: {st: v / games[t] for st, v in sv.items()} for gr, sv in cum[t].items()}
                                   if games[t] >= 5 else None,
                                   {gr: {st: v / lg_games for st, v in sv.items()} for gr, sv in league.items()} if lg_games else None)
                volume[(t, d)] = vol[t] / games[t] if games[t] else None
        for g, teams in todays:
            if len(teams) != 2:
                continue
            for t, o in opp[g].items():
                for r in teams[t]:
                    gr = groups.get(r["pid"])
                    for st in ("pts", "reb", "ast"):
                        cum[o][gr][st] += r[st] or 0
                        league[gr][st] += r[st] or 0
                vol[t] += sum((r["fga"] or 0) + 0.44 * (r["fta"] or 0) for r in teams[t])
                games[t] += 1
                lg_games += 1
    return opp, allowed, volume


def bets_of(s, g, books, ctx):
    """Every UNDER20 flag 20%+ below (under -150 or better, not threes) in season s with its features and outcome."""
    seasons, rows, lines, T, BOOST = g["seasons"], g["rows"], g["lines"], g["T"], g["BOOST"]
    se = seasons[s]
    bd = se.bd
    opp, allowed, volume = ctx
    team_of = {(r["date"], r["pid"]): r["team"] for r in rows[s]}
    implied = defaultdict(float)
    for (d, pid, mk), ln in lines.items():
        if mk == "points" and (d, pid) in team_of:
            implied[(d, team_of[(d, pid)])] += ln[0]
    out = []
    for r in rows[s]:
        d, p, team = r["date"], r["pid"], r["team"]
        mine = bd.his(p, d)
        this = [x for x in mine if x["season"] == s]
        last10 = [x["min"] for x in mine[-10:]]
        o = opp.get(r["gid"], {}).get(team)
        base = None
        for mk in T.MARKETS:
            ln = lines.get((d, p, mk))
            if not ln or mk == "threes":
                continue
            line, _ov, under, q = ln
            parts = BOOST.PARTS[mk]
            proj = T.proj(r, mk)
            act = BOOST.stat_of(r["box"], mk)
            if act == line or under < 1 / 0.6 - 1e-9 or proj >= 0.8 * line:
                continue
            if base is None:
                played = {x for x, v in r["team_box"].items() if v["min"]}
                starters = bd.usual_five(team, d) or bd.starters(team, d)
                out_all = (bd.on_team_tonight(team, d) - played) & (bd.roster(team, d) | starters)
                capela = bool(r["new_starter"]) or any(bd.letters(x) & bd.letters(p) for x in out_all & starters)
                base = capela
            stat = lambda x: sum(x[st] or 0 for st in parts)
            rate = sum(r["rt"][st] for st in parts)
            l5 = mine[-5:]
            seas = this if len(this) >= 3 else [x for x in mine if x["season"] != s]
            l10 = mine[-10:]
            al = allowed.get((o, d)) if o else None
            grp = se.groups.get(p)
            e1 = math.nan
            if al and al[0] and al[1] and grp in al[0] and grp in al[1]:
                lg = sum(al[1][grp].get(st, 0) for st in parts if st in ("pts", "reb", "ast"))
                e1 = sum(al[0][grp].get(st, 0) for st in parts if st in ("pts", "reb", "ast")) / lg if lg else math.nan
            ob = books.get((d, p, mk))
            f = {
                "A1 V3 - last-10 min": r["ctx"]["min_change"],
                "A2 last game min - V3": mine[-1]["min"] - r["min"] if mine else math.nan,
                "A3 last-3 min - V3": float(np.mean([x["min"] for x in mine[-3:]])) - r["min"] if mine else math.nan,
                "A4 sd of last-10 min": float(np.std(last10)) if len(last10) >= 3 else math.nan,
                "A5 games this season": len(this),
                "A6 starts tonight": float(bool(r["box"].get("starter"))) if r["box"].get("starter") is not None else math.nan,
                "A7 Capela-type bump": float(base),
                "B1 this season's share of rate": (lambda tm: tm / (tm + 150.0))(sum(x["min"] for x in this)),
                "B2 last-5 per-min / our rate": (sum(stat(x) for x in l5) / sum(x["min"] for x in l5)) / rate
                if l5 and sum(x["min"] for x in l5) and rate else math.nan,
                "B3 line / season avg": line / float(np.mean([stat(x) for x in seas])) if seas and np.mean([stat(x) for x in seas]) else math.nan,
                "B4 line / last-5 avg": line / float(np.mean([stat(x) for x in l5])) if l5 and np.mean([stat(x) for x in l5]) else math.nan,
                "B5 under rate at this line, last 10": float(np.mean([stat(x) < line for x in l10])) if len(l10) >= 3 else math.nan,
                "C1 under price": under, "C2 book no-vig over": q,
                "C3 MGM/Caesars line - ours": float(np.mean(ob)) - line if ob else math.nan,
                "C4 % below the line": 1 - proj / line, "C5 line": line,
                "D1 team implied points": implied.get((d, team), math.nan),
                "D2 implied spread": implied.get((d, team), math.nan) - implied.get((d, o), math.nan) if o else math.nan,
                "D4 rest days": r["ctx"]["rest"], "D4 back-to-back": r["ctx"]["b2b"], "D5 team game index": r["ctx"]["game_index"],
                "E1 opp allowed to his group / league": e1,
                "E2 both teams' shot volume": (volume.get((team, d)) or math.nan) + (volume.get((o, d)) or math.nan) if o else math.nan,
            }
            f["D3 implied spread size"] = abs(f["D2 implied spread"])
            out.append({"f": f, "mk": mk, "u": under - 1 if act < line else -1.0, "win": int(act < line),
                        "ping": 0.30 <= 1 - proj / line < 0.50,
                        "min_miss": r["box"]["min"] - r["min"],
                        "rate_miss": (act / r["box"]["min"]) / rate if r["box"]["min"] and rate else math.nan})
    return out


def roi(bs):
    return float(np.mean([b["u"] for b in bs])) if bs else math.nan


def boot_gap(bad, rest, n=1000):
    a, b = np.array([x["u"] for x in bad]), np.array([x["u"] for x in rest])
    gaps = [rng.choice(b, len(b)).mean() - rng.choice(a, len(a)).mean() for _ in range(n)]
    return float(np.mean(np.array(gaps) > 0))


def bins(disc, name):
    """[(label, test(value) -> in bin)] from the discovery set: terciles for numeric, values for binary, the market."""
    if name == "C6 market":
        return [(m, (lambda m: lambda b: b["mk"] == m)(m)) for m in sorted({b["mk"] for b in disc})]
    vals = np.array([b["f"][name] for b in disc if b["f"][name] == b["f"][name]])
    if name in BINARY:
        return [(f"= {v:g}", (lambda v: lambda b: b["f"][name] == v)(v)) for v in sorted(set(vals))]
    lo, hi = np.quantile(vals, [1 / 3, 2 / 3])
    return [(f"<= {lo:.3g}", lambda b: b["f"][name] <= lo), (f"{lo:.3g} to {hi:.3g}", lambda b: lo < b["f"][name] <= hi),
            (f"> {hi:.3g}", lambda b: b["f"][name] > hi)]


def main():
    sys.path.insert(0, ".")
    g = {}
    exec(open("nba_tests4_checks.py").read().split("NAMES = [")[0], g)
    books = other_books(g["M"], g["MR"], g["BOOST"])
    data = {}
    for s in ("2023-24", "2024-25"):
        ctx = opponent_context(g["rows_db"], s, g["seasons"][s].groups)
        data[s] = bets_of(s, g, books, ctx)
    disc, test = data["2023-24"], data["2024-25"]
    res = {"n": {s: len(v) for s, v in data.items()}, "roi": {s: roi(v) for s, v in data.items()}}
    print(f"discovery 2023-24: {len(disc)} bets ROI {roi(disc):+.3f} (ping set {sum(b['ping'] for b in disc)}, "
          f"{roi([b for b in disc if b['ping']]):+.3f}); test 2024-25: {len(test)} ROI {roi(test):+.3f} "
          f"(ping set {sum(b['ping'] for b in test)}, {roi([b for b in test if b['ping']]):+.3f})")

    print("\n== why they lose (information, both seasons)")
    for s, bs in data.items():
        lost = [b for b in bs if not b["win"]]
        won = [b for b in bs if b["win"]]
        for lab, grp in (("lost", lost), ("won", won)):
            mm = np.array([b["min_miss"] for b in grp]); rm = np.array([b["rate_miss"] for b in grp if b["rate_miss"] == b["rate_miss"]])
            print(f"  {s} {lab:4s} n {len(grp):4d}: minutes vs V3 {mm.mean():+.1f} (5+ over: {(mm >= 5).mean():.0%}); "
                  f"per-min vs our rate x{np.median(rm):.2f} median (25%+ over: {(rm >= 1.25).mean():.0%}); "
                  f"both: {np.mean([(b['min_miss'] >= 5) and (b['rate_miss'] >= 1.25) for b in grp]):.0%}")

    print("\n== discovery (2023-24): ROI by bin")
    cands, table = [], {}
    for name in NUMERIC + BINARY + ("C6 market",):
        rows_ = []
        for lab, inb in bins(disc, name):
            bad = [b for b in disc if (name == "C6 market" or b["f"][name] == b["f"][name]) and inb(b)]
            ids = {id(x) for x in bad}
            rest = [b for b in disc if id(b) not in ids]
            if len(bad) < 50 or not rest:
                continue
            gap = roi(rest) - roi(bad)
            sure = boot_gap(bad, rest) if gap >= GAP else None
            rows_.append((lab, len(bad), roi(bad), gap, sure))
            if gap >= GAP and sure >= SURE:
                cands.append((gap, name, lab, inb))
        table[name] = rows_
        print(f"  {name:38s} " + " | ".join(f"{lab} n {n} {r:+.3f}" for lab, n, r, _g, _s in rows_))
    cands.sort(key=lambda c: -c[0])
    print("\ncandidates (gap >= 8 points, bootstrap >= 95%): " + ("; ".join(f"{n} {l} (gap {g_:+.3f})" for g_, n, l, _f in cands) or "none"))
    picked = cands[:TOP]

    # the combined model
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    names = NUMERIC + BINARY
    mks = sorted({b["mk"] for b in disc})
    X = {s: np.array([[b["f"][n] for n in names] + [float(b["mk"] == m) for m in mks] for b in data[s]], dtype=float) for s in data}
    y = np.array([b["win"] for b in disc])
    med = np.nanmedian(X["2023-24"], axis=0)
    Xf = {s: np.where(np.isnan(X[s]), med, X[s]) for s in X}
    sc = StandardScaler().fit(Xf["2023-24"])
    lr = LogisticRegression(C=1.0, max_iter=3000).fit(sc.transform(Xf["2023-24"]), y)
    p = {s: lr.predict_proba(sc.transform(Xf[s]))[:, 1] for s in X}
    cut = float(np.quantile(p["2023-24"], 1 / 3))
    for s in data:
        for b, pp in zip(data[s], p[s]):
            b["p"] = float(pp)
    coefs = sorted(zip(list(names) + [f"mk {m}" for m in mks], lr.coef_[0]), key=lambda kv: -abs(kv[1]))[:8]
    print("combined model, largest standardized coefficients (+ = under more likely to win): " +
          ", ".join(f"{n} {c:+.2f}" for n, c in coefs))
    picked.append((None, "combined model", f"predicted win < {cut:.3f}", lambda b: b["p"] < cut))

    print("\n== held-out test (2024-25): drop the bin")
    res["tests"] = []
    for _g, name, lab, inb in picked:
        out = {"feature": name, "bin": lab}
        for setname, bs in (("ping", [b for b in test if b["ping"]]), ("20%+", test)):
            ok_ = (lambda b: name in ("C6 market", "combined model") or b["f"][name] == b["f"][name])
            drop = [b for b in bs if ok_(b) and inb(b)]
            ids = {id(x) for x in drop}
            keep = [b for b in bs if id(b) not in ids]
            out[setname] = {"all": (len(bs), roi(bs)), "kept": (len(keep), roi(keep)), "dropped": (len(drop), roi(drop))}
        pg, wd = out["ping"], out["20%+"]
        out["pass"] = bool(pg["kept"][1] >= pg["all"][1] + PASS_KEPT and pg["kept"][1] - pg["dropped"][1] >= PASS_PING
                           and wd["kept"][1] - wd["dropped"][1] >= PASS_WIDE)
        res["tests"].append(out)
        print(f"  {name} {lab}: ping set all {pg['all'][0]} {pg['all'][1]:+.3f} | kept {pg['kept'][0]} {pg['kept'][1]:+.3f} | "
              f"dropped {pg['dropped'][0]} {pg['dropped'][1]:+.3f};  20%+ kept {wd['kept'][1]:+.3f} dropped {wd['dropped'][0]} "
              f"{wd['dropped'][1]:+.3f} -> {'PASS' if out['pass'] else 'FAIL'}")
    res["table"] = {k: [(l, n, r, gp, su) for l, n, r, gp, su in v] for k, v in table.items()}
    OUT.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
