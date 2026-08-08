#!/usr/bin/env python3
"""SYSTEM PLAYS on 3 seasons, with EXPLICIT position-specific "good at it" thresholds.

WHAT CHANGED
  1. 2023 + 2024 box scores backfilled: 320 -> 848 games (2.65x). Sample, not position
     resolution, was the binding constraint -- the 5-slot re-run made reliability WORSE
     (+0.323 -> +0.232) purely because finer cells are thinner.
  2. EXPLICIT THRESHOLDS printed as real per-36 numbers, so "a good rebounding forward" is an
     inspectable bar rather than a hidden tercile, and swept at 33/25/20% so no conclusion rests
     on one arbitrary cut.
  3. BOTH granularities (3-group G/F/C and 5-slot) so the data decides rather than me.

POSITIONS come from the box table's own row order: ESPN lists starters first in position order
and the scraper preserved it. Verified: first five average 27.7 min vs 13.4; median player takes
90% of starts in one slot; direction is bigs-first (slot 0 reb/36 8.60 -> slot 4 ast/36 5.17).
`dvp_backtest.positions()` was NOT used -- it returns only CURRENT rosters keyed by ESPN
player-id, so it cannot label 2023-24 players who have since left.

⚠️ PRIOR ART: DvP as a GATE on existing bets was tested 2026-07-31 and was WORSE AT EVERY
THRESHOLD. That is a different question (filter on chosen bets vs source of plays), but if
anything here survives, port it onto `dvp_backtest.fit_dvp` -- ridge, opponent+pace-adjusted --
which is better machinery than naive cell means.
"""
import sqlite3, collections, statistics as st

BOX = "/home/ubuntu/tennis-odds-collector/wnba_boxscores.sqlite"
P25 = "/home/ubuntu/tennis-odds-collector/wnba_props_2025.sqlite"
PH = "/home/ubuntu/tennis-odds-collector/wnba_props_hist.sqlite"
MK = {"player_points": ("pts", "rpts"), "player_rebounds": ("reb", "rreb"),
      "player_assists": ("ast", "rast")}
SLOT5 = {0: "F1", 1: "C", 2: "F2", 3: "G1", 4: "G2"}
SLOT3 = {0: "F", 1: "C", 2: "F", 3: "G", 4: "G"}


def norm(s):
    return " ".join(str(s or "").lower().replace(".", "").replace("'", "").split())


def corr(pairs):
    if len(pairs) < 8:
        return None, len(pairs)
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in pairs)
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    return (num / den if den else 0.0), len(pairs)


c = sqlite3.connect("file:%s?mode=ro" % BOX, uri=True)
rows = list(c.execute("SELECT rowid,game_id,game_date,team,player,min,pts,reb,ast "
                      "FROM box ORDER BY rowid"))
c.close()
print("box rows %d | seasons %s"
      % (len(rows), dict(sorted(collections.Counter(str(r[2])[:4] for r in rows).items()))))

by = collections.defaultdict(list)
for rid, gid, gd, team, pl, mn, pts, reb, ast in rows:
    by[(gid, team)].append((norm(pl), mn or 0, pts or 0, reb or 0, ast or 0))
gt = collections.defaultdict(set)
for (gid, team) in by:
    gt[gid].add(team)
opp = {}
for gid, v in gt.items():
    if len(v) == 2:
        a, b = list(v)
        opp[(gid, a)] = b; opp[(gid, b)] = a
tc = collections.Counter(t for (_g, t) in by)
TEAMS = {t for t, n in tc.items() if n >= 40}
print("teams with >=40 team-games: %d" % len(TEAMS))

slots = collections.defaultdict(collections.Counter)
for v in by.values():
    for i, (pl, mn, pts, reb, ast) in enumerate(v[:5]):
        slots[pl][i] += 1
modal = {pl: cnt.most_common(1)[0][0] for pl, cnt in slots.items() if sum(cnt.values()) >= 5}

flat = []
per = collections.defaultdict(lambda: collections.defaultdict(float))
for rid, gid, gd, team, pl, mn, pts, reb, ast in rows:
    pl = norm(pl); gd = str(gd)[:10]
    flat.append((gid, gd, team, pl, mn or 0, pts or 0, reb or 0, ast or 0))
    if mn and mn >= 5:
        p = per[pl]
        p["min"] += mn; p["pts"] += pts or 0; p["reb"] += reb or 0
        p["ast"] += ast or 0; p["g"] += 1
pool = {k: v for k, v in per.items() if v["g"] >= 10 and v["min"] >= 150 and k in modal}
for v in pool.values():
    for r, s in (("rpts", "pts"), ("rreb", "reb"), ("rast", "ast")):
        v[r] = 36.0 * v[s] / v["min"]
print("pool: %d players" % len(pool))

lines = collections.defaultdict(dict)
for db in (P25, PH):
    cc = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    for gd, mk, pl, sd, ln in cc.execute(
            "SELECT game_date,market,player,side,line FROM props WHERE line IS NOT NULL"):
        if str(sd).lower() == "over":
            lines[(norm(pl), str(gd)[:10])][mk] = float(ln)
    cc.close()
lyr = collections.Counter(k[1][:4] for k in lines)
print("prop-lined player-games: %d | by season %s\n" % (len(lines), dict(sorted(lyr.items()))))

dates = sorted({f[1] for f in flat})
mid = dates[len(dates) // 2]


def run(posmap, label, pct, quiet=False):
    P = {pl: posmap[modal[pl]] for pl in pool}
    cut = {}
    for pos in set(P.values()):
        for mk, (_s, r) in MK.items():
            vals = sorted(v[r] for k, v in pool.items() if P[k] == pos)
            if len(vals) >= 6:
                cut[(pos, r)] = vals[int(len(vals) * (1 - pct))]
    cA, cB = collections.defaultdict(list), collections.defaultdict(list)
    hA, hB = collections.defaultdict(list), collections.defaultdict(list)
    for gid, gd, team, pl, mn, pts, reb, ast in flat:
        p = pool.get(pl); o = opp.get((gid, team))
        if not p or o not in TEAMS or mn < 5:
            continue
        pos = P[pl]
        got = {"pts": pts, "reb": reb, "ast": ast}
        for mk, (s, r) in MK.items():
            if (pos, r) not in cut or p[r] < cut[(pos, r)]:
                continue
            key = (pos, mk, o)
            (cA if gd <= mid else cB)[key].append((36.0 * got[s] / mn) - p[r])
            L = lines.get((pl, gd), {}).get(mk)
            if L is not None and got[s] != L:
                (hA if gd <= mid else hB)[key].append(1 if got[s] > L else 0)
    ra = corr([(st.mean(cA[k]), st.mean(cB[k])) for k in set(cA) & set(cB)
               if len(cA[k]) >= 8 and len(cB[k]) >= 8])
    rb = corr([(st.mean(hA[k]), st.mean(hB[k])) for k in set(hA) & set(hB)
               if len(hA[k]) >= 6 and len(hB[k]) >= 6])
    picks = [k for k in hA if len(hA[k]) >= 6 and st.mean(hA[k]) >= 0.60]
    bets = [x for k in picks for x in hB.get(k, [])]
    base = [x for v in hB.values() for x in v]
    bs = ("%d-%d = %5.1f%%" % (sum(bets), len(bets) - sum(bets), 100 * st.mean(bets))
          if len(bets) >= 30 else "thin (n=%d)" % len(bets))
    if not quiet:
        print("  %-16s real r=%-8s(%3d)  priced r=%-8s(%3d)  bet %-18s base %5.1f%%"
              % (label,
                 ("%+.3f" % ra[0]) if ra[0] is not None else "n/a", ra[1],
                 ("%+.3f" % rb[0]) if rb[0] is not None else "n/a", rb[1],
                 bs, 100 * st.mean(base) if base else 0))
    return cut


print("=== THRESHOLD SWEEP: 'good at it' = top X% within position ===")
for pct, tag in ((0.33, "top33"), (0.25, "top25"), (0.20, "top20")):
    for posmap, gl in ((SLOT3, "3grp"), (SLOT5, "5slot")):
        run(posmap, "%s %s" % (tag, gl), pct)
print("  need 52.4% at -110, 51.0% at the best-of-8 shopped price")
print("  1-season run gave: real +0.323 / priced +0.139 / bet 50.6% vs 48.0% base")

print("\n=== THE THRESHOLDS, in plain per-36 terms (top 25%, 3-group) ===")
cut = run(SLOT3, "", 0.25, quiet=True)
nm = {"rpts": "points", "rreb": "rebounds", "rast": "assists"}
for pos, word in (("G", "GUARD"), ("F", "FORWARD"), ("C", "CENTER")):
    bits = ["%s/36 >= %4.1f" % (nm[r], cut[(pos, r)]) for r in ("rpts", "rreb", "rast")
            if (pos, r) in cut]
    print("   a GOOD %-8s : %s" % (word, "   |   ".join(bits)))
