#!/usr/bin/env python3
"""Independent 2025 holdout for the stint apart-rate rebound edge.

2026 gave rebounds 26-10 (72.2% vs 53.1% breakeven), and it survived every de-concentration
cut — 20 distinct beneficiaries, and the edge got STRONGER when repeats were capped. This is
the gate that killed several ideas tonight: does it hold on a season it was not found on?

Self-contained on 2025 data: wnba_boxscores (results + minutes), wnba_props_2025 (real book
lines), wnba_stints (on/off, now repaired). Positions come from the current roster map, so
players no longer listed are skipped — reported, not hidden.
"""
import sys, sqlite3, statistics as st
from collections import defaultdict, Counter

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_wowy as W

STINT = "wnba_stints.sqlite"
BOX = "wnba_boxscores.sqlite"
PROPS = "wnba_props_2025.sqlite"
MIN_APART, STARTER_MIN, MAX_NWO = 50.0, 25.0, 2
SPEC = {"rebounds": ("reb", "reb_with", "player_rebounds", "reb"),
        "assists":  ("ast", "ast_with", "player_assists",  "ast"),
        "points":   ("pts", "pts_with", "player_points",   "pts")}


def main():
    stat = sys.argv[1] if len(sys.argv) > 1 else "rebounds"
    tc, pc, mk, key = SPEC[stat]

    b = sqlite3.connect(f"file:{BOX}?mode=ro", uri=True)
    rows = b.execute("SELECT game_id,game_date,team,player,min,pts,reb,ast FROM box "
                     "WHERE min IS NOT NULL").fetchall()
    log, team_of, appeared, team_dates = defaultdict(list), {}, defaultdict(set), defaultdict(set)
    for gid, d, tm, pl, mn, pts, reb, ast in rows:
        log[pl].append({"d": d, "gid": gid, "min": mn or 0, "pts": pts or 0,
                        "reb": reb or 0, "ast": ast or 0})
        team_of[pl] = tm
        team_dates[tm].add(d)
        if (mn or 0) > 0:
            appeared[(d, tm)].add(pl)
    for k in log:
        log[k].sort(key=lambda x: x["d"])
    roster = defaultdict(set)
    for pl, tm in team_of.items():
        roster[tm].add(pl)

    p = sqlite3.connect(f"file:{PROPS}?mode=ro", uri=True)
    lines = defaultdict(dict)
    for d, pl, m, ln, side, pr in p.execute(
            "SELECT game_date,player,market,line,side,price FROM props WHERE market=?", (mk,)):
        if side in ("over", "under") and ln is not None and pr:
            lines[(d, pl)].setdefault(round(float(ln), 1), {})[side] = float(pr)

    s = sqlite3.connect(f"file:{STINT}?mode=ro", uri=True)
    ok = {e for (e,) in s.execute("SELECT event_id FROM games WHERE status='ok'")}
    on = defaultdict(list); pair = defaultdict(list)
    for e, d, pl, sec, v in s.execute(f"SELECT event_id,game_date,player,sec,{tc} FROM onfloor"):
        if e in ok and v is not None and d < "2026-01-01":
            on[pl].append((d, sec or 0.0, v or 0.0))
    for e, d, pl, m2, sec, v in s.execute(
            f"SELECT event_id,game_date,player,mate,sec,{pc} FROM pairs"):
        if e in ok and v is not None and d < "2026-01-01":
            pair[(pl, m2)].append((d, sec or 0.0, v or 0.0))

    pmap = W.players()
    nopos = set()

    def apart(a, bmate, before):
        ts = tv = 0.0
        for d, sec, v in on.get(a, []):
            if d < before:
                ts += sec; tv += v
        ws = wv = 0.0
        for d, sec, v in pair.get((a, bmate), []):
            if d < before:
                ws += sec; wv += v
        sd = ts - ws
        return ((tv - wv) / (sd / 60.0), sd / 60.0) if sd > 0 else None

    cand = []
    for tm, ros in roster.items():
        tds = sorted(team_dates[tm])
        for di, day in enumerate(tds):
            app = appeared.get((day, tm), set())
            if not app:
                continue
            prior = {pl: [x for x in log[pl] if x["d"] < day] for pl in ros}
            for out_name in ros:
                if out_name in app:
                    continue
                og = [x for x in prior.get(out_name, []) if x["min"] > 0]
                if len(og) < 5 or st.mean(x["min"] for x in og[-10:]) < 20:
                    continue
                ov = pmap.get(out_name)
                if not ov or not ov.get("position"):
                    nopos.add(out_name); continue
                opos = ov["position"]
                out_gids = {x["gid"] for x in og}
                for n in app:
                    if n == out_name:
                        continue
                    nv = pmap.get(n)
                    if not nv or nv.get("position") != opos:
                        if not nv:
                            nopos.add(n)
                        continue
                    g = [x for x in prior.get(n, []) if x["min"] > 0]
                    if len(g) < 6:
                        continue
                    wi = [x for x in g if x["gid"] in out_gids]
                    wo = [x for x in g if x["gid"] not in out_gids]
                    if len(wi) < 2 or len(wo) > MAX_NWO:
                        continue
                    if st.mean(x["min"] for x in wi) < STARTER_MIN:
                        continue
                    ar = apart(n, out_name, day)
                    if not ar:
                        continue
                    rate, mins = ar
                    if mins < MIN_APART:
                        continue
                    r5 = [x["min"] for x in g[-5:] if x["min"] > 8]
                    pm = st.median(r5) if r5 else st.mean(x["min"] for x in wi)
                    proj = rate * pm
                    lad = lines.get((day, n)) or {}
                    two = {k2: v2 for k2, v2 in lad.items() if "over" in v2 and "under" in v2}
                    if not two:
                        continue
                    line = min(two, key=lambda x: abs(two[x]["over"] - two[x]["under"]))
                    price = two[line]["over"]
                    act = [x for x in log[n] if x["d"] == day and x["min"] > 0]
                    if not act or abs(act[0][key] - line) < 1e-9:
                        continue
                    cand.append({"proj": proj, "line": line, "price": price,
                                 "hit": 1 if act[0][key] > line else 0,
                                 "player": n, "out": out_name, "date": day})

    print(f"2025 HOLDOUT — {stat}   {len(cand)} bets   "
          f"({len(nopos)} players skipped: no position in current roster map)")
    if not cand:
        print("  nothing to grade")
        return

    def rep(rows, label):
        if len(rows) < 5:
            print(f"  {label:<30} n={len(rows)} (too thin)"); return
        w_ = sum(r["hit"] for r in rows); l_ = len(rows) - w_
        u = sum((r["price"] - 1.0) if r["hit"] else -1.0 for r in rows)
        be = st.mean([1.0 / r["price"] for r in rows])
        hit = w_ / len(rows)
        print(f"  {label:<30} {w_}-{l_}  hit {100*hit:5.1f}%  be {100*be:5.1f}%  "
              f"edge {100*(hit-be):+6.1f}  {u:+7.2f}u")

    for m in (0.0, 0.5, 1.0):
        rep([c for c in cand if c["proj"] - c["line"] >= m], f"margin {m}")
    sel = [c for c in cand if c["proj"] - c["line"] >= 0.0]
    print(f"\n  distinct beneficiaries: {len(set(c['player'] for c in sel))}   "
          f"distinct pairs: {len(set((c['player'], c['out']) for c in sel))}")
    seen, first = set(), []
    for c in sorted(sel, key=lambda x: x["date"]):
        k = (c["player"], c["out"])
        if k not in seen:
            seen.add(k); first.append(c)
    rep(first, f"ONE per pair (n={len(first)})")


if __name__ == "__main__":
    main()
