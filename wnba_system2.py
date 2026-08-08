#!/usr/bin/env python3
"""SYSTEM PLAYS, re-run with REAL positional slots instead of a 3-way statistical proxy.

WHERE THE POSITIONS CAME FROM -- and the mistake worth recording
    ESPN lists starters first, in position order, and the scraper preserved that order, so
    position is already in `rowid`. My first probe declared "NOT positional -- must scrape",
    but it had HARD-CODED the direction (assuming PG first). The order is the other way round:
        slot 0  reb/36 8.60  ast/36 3.23   forward
        slot 1  reb/36 8.27  ast/36 2.95   center
        slot 2  reb/36 6.03  ast/36 3.80   wing
        slot 3  reb/36 3.99  ast/36 4.34   guard
        slot 4  reb/36 4.66  ast/36 5.17   point guard
    The gradient is strong and monotone; only my assumed sign was wrong. ⇒ A verdict computed
    from an assumed direction can call real signal "absent" -- check the magnitude before the sign.
    Starters-first is confirmed independently: first five average 27.7 min vs 13.4 for the rest.
    Each player is assigned their MODAL slot (median player takes 90% of starts in one slot).

WHAT CHANGES vs the first run: 5 positions instead of 3 size classes -- finer and grounded in the
actual lineup rather than a rebound/assist tilt. The tradeoff is FEWER observations per cell
(5 x 3 x 13 = 195 possible cells vs 117), so if the finer split is genuinely better the
split-half r must RISE despite thinner cells. That is the whole test.
Method is otherwise identical: split-half reliability first (117+ paired cells, not 14 games),
production measured against each player's OWN season rate, then a discovery/confirmation bet test.
"""
import sqlite3, collections, statistics as st

BOX = "/home/ubuntu/tennis-odds-collector/wnba_boxscores.sqlite"
P25 = "/home/ubuntu/tennis-odds-collector/wnba_props_2025.sqlite"
PH = "/home/ubuntu/tennis-odds-collector/wnba_props_hist.sqlite"
TEAMS = {"LV", "IND", "PHX", "MIN", "ATL", "NY", "SEA", "GS", "DAL", "CON", "LA", "CHI", "WSH"}
MK = {"player_points": ("pts", "rpts"), "player_rebounds": ("reb", "rreb"),
      "player_assists": ("ast", "rast")}
POS = {0: "F", 1: "C", 2: "W", 3: "G", 4: "PG"}


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

by = collections.defaultdict(list)
for rid, gid, gd, team, pl, mn, pts, reb, ast in rows:
    by[(gid, team)].append((pl, mn or 0, pts or 0, reb or 0, ast or 0))
gt = collections.defaultdict(set)
for (gid, team) in by:
    gt[gid].add(team)
opp = {}
for gid, v in gt.items():
    if len(v) == 2:
        a, b = list(v)
        opp[(gid, a)] = b; opp[(gid, b)] = a

# player -> modal starting slot
slots = collections.defaultdict(collections.Counter)
for v in by.values():
    for i, (pl, mn, pts, reb, ast) in enumerate(v[:5]):
        slots[norm(pl)][i] += 1
pos = {}
for pl, cnt in slots.items():
    if sum(cnt.values()) >= 5:
        pos[pl] = cnt.most_common(1)[0][0]
print("players with a stable starting slot (>=5 starts): %d   %s"
      % (len(pos), dict(collections.Counter(POS[v] for v in pos.values()))))

lines = collections.defaultdict(dict)
for db in (P25, PH):
    cc = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    for gd, mk, pl, sd, ln in cc.execute(
            "SELECT game_date,market,player,side,line FROM props WHERE line IS NOT NULL"):
        if str(sd).lower() == "over":
            lines[(norm(pl), str(gd)[:10])][mk] = float(ln)
    cc.close()

per = collections.defaultdict(lambda: collections.defaultdict(float))
flat = []
for rid, gid, gd, team, pl, mn, pts, reb, ast in rows:
    gd = str(gd)[:10]
    flat.append((gid, gd, team, norm(pl), mn or 0, pts or 0, reb or 0, ast or 0))
    if mn and mn >= 5:
        p = per[norm(pl)]
        p["min"] += mn; p["pts"] += pts or 0; p["reb"] += reb or 0
        p["ast"] += ast or 0; p["g"] += 1
pool = {k: v for k, v in per.items() if v["g"] >= 10 and v["min"] >= 150 and k in pos}
for v in pool.values():
    for r, s in (("rpts", "pts"), ("rreb", "reb"), ("rast", "ast")):
        v[r] = 36.0 * v[s] / v["min"]
cut = {}
for sl in range(5):
    for _mk, (_s, r) in MK.items():
        vals = sorted(v[r] for k, v in pool.items() if pos[k] == sl)
        if vals:
            cut[(sl, r)] = vals[2 * len(vals) // 3]

dates = sorted({f[1] for f in flat})
mid = dates[len(dates) // 2]
print("pool (>=10 g, >=150 min, stable slot): %d players | split at %s\n" % (len(pool), mid))

cellA, cellB = collections.defaultdict(list), collections.defaultdict(list)
hitA, hitB = collections.defaultdict(list), collections.defaultdict(list)
for gid, gd, team, pl, mn, pts, reb, ast in flat:
    p = pool.get(pl)
    o = opp.get((gid, team))
    if not p or o not in TEAMS or mn < 5:
        continue
    sl = pos[pl]
    got = {"pts": pts, "reb": reb, "ast": ast}
    for mk, (s, r) in MK.items():
        if (sl, r) not in cut or p[r] < cut[(sl, r)]:
            continue
        key = (POS[sl], mk, o)
        rel = (36.0 * got[s] / mn) - p[r]
        (cellA if gd <= mid else cellB)[key].append(rel)
        L = lines.get((pl, gd), {}).get(mk)
        if L is not None and got[s] != L:
            (hitA if gd <= mid else hitB)[key].append(1 if got[s] > L else 0)

print("=== A. IS IT REAL? split-half reliability (production vs own baseline) ===")
print("  %-24s %-10s %-8s | %s" % ("market", "r (SLOT)", "cells", "r from the 3-way proxy run"))
prev = {"player_points": "+0.420", "player_rebounds": "+0.015", "player_assists": "+0.206"}
allp = []
for mk in MK:
    pairs = [(st.mean(cellA[k]), st.mean(cellB[k])) for k in set(cellA) & set(cellB)
             if k[1] == mk and len(cellA[k]) >= 6 and len(cellB[k]) >= 6]
    allp += pairs
    r, n = corr(pairs)
    print("  %-24s %-10s %-8d | %s" % (mk, ("%+.3f" % r) if r is not None else "n/a", n, prev[mk]))
r, n = corr(allp)
print("  %-24s %-10s %-8d | %s   <-- headline"
      % ("ALL POOLED", ("%+.3f" % r) if r is not None else "n/a", n, "+0.323"))

print("\n=== B. IS IT PRICED? split-half of the cell's HIT RATE vs the real line ===")
allh = []
prevb = {"player_points": "+0.033", "player_rebounds": "+0.187", "player_assists": "+0.204"}
for mk in MK:
    pairs = [(st.mean(hitA[k]), st.mean(hitB[k])) for k in set(hitA) & set(hitB)
             if k[1] == mk and len(hitA[k]) >= 5 and len(hitB[k]) >= 5]
    allh += pairs
    r, n = corr(pairs)
    print("  %-24s %-10s %-8d | %s" % (mk, ("%+.3f" % r) if r is not None else "n/a", n, prevb[mk]))
r, n = corr(allh)
print("  %-24s %-10s %-8d | %s   <-- headline"
      % ("ALL POOLED", ("%+.3f" % r) if r is not None else "n/a", n, "+0.139"))

print("\n=== C. THE BET: hot cells in half 1, bet them in half 2 ===")
for thr in (0.60, 0.65):
    picks = [k for k in hitA if len(hitA[k]) >= 5 and st.mean(hitA[k]) >= thr]
    bets = [x for k in picks for x in hitB.get(k, [])]
    if len(bets) >= 25:
        w = sum(bets)
        print("  cells >=%.0f%% in half 1: %-3d -> half 2: %d-%d = %.1f%%"
              % (100 * thr, len(picks), w, len(bets) - w, 100 * w / len(bets)))
    else:
        print("  cells >=%.0f%% in half 1: %-3d -> only %d bets in half 2 (thin)"
              % (100 * thr, len(picks), len(bets)))
base = [x for v in hitB.values() for x in v]
if base:
    print("  baseline: all qualifying plays in half 2 = %.1f%% over (n=%d)"
          % (100 * st.mean(base), len(base)))
print("  need 52.4%% at -110, 51.0%% at the best-of-8 shopped price")
print("  3-way proxy run got: 50.6%% / 51.1%% vs a 48.0%% baseline")

print("\n=== the strongest surviving cells (BOTH halves >=55%, n>=5 each) ===")
surv = []
for k in set(hitA) & set(hitB):
    if len(hitA[k]) >= 5 and len(hitB[k]) >= 5:
        a, b = st.mean(hitA[k]), st.mean(hitB[k])
        if a >= 0.55 and b >= 0.55:
            surv.append((a, b, k, len(hitA[k]) + len(hitB[k])))
surv.sort(key=lambda x: -(x[0] + x[1]))
for a, b, k, n in surv[:10]:
    print("   %-3s %-24s vs %-4s   half1 %.0f%%  half2 %.0f%%  (n=%d)"
          % (k[0], k[1], k[2], 100 * a, 100 * b, n))
if not surv:
    print("   none")
print("   ^ shown for texture only -- these were SELECTED for surviving, so their rates are")
print("     inflated by construction. The honest number is the half-2 result in section C.")
