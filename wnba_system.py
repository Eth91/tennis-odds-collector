#!/usr/bin/env python3
"""SYSTEM PLAYS: does defence-vs-position/skill exist, and is it priced?

WHY NOT TEST CELLS ONE AT A TIME
    A cell ("good rebounding big vs DAL") holds a median of 28 player-games, ~14 per half.
    Nothing can be concluded from one of those, and with 117 cells the best-looking one is
    guaranteed to look great by chance. Reporting it would be the winner's curse in pure form.

THE WELL-POWERED VERSION OF THE SAME QUESTION
    Do not ask "is THIS cell hot?" Ask "do hot cells STAY hot?" -- i.e. SPLIT-HALF RELIABILITY
    across all 117 cells at once. That is 117 paired observations instead of 14, and it is the
    same instrument that showed a TT player's match-length tendency is real (r = +0.440).
      r ~ 0      -> the cells are noise, system plays do not exist, done.
      r > 0      -> the effect is REAL and persistent; only then is it worth asking about price.

TWO SEPARATE QUESTIONS, DELIBERATELY NOT MIXED
    A. IS IT REAL?    cell metric = production RELATIVE TO THE PLAYER'S OWN SEASON BASELINE.
       De-conditioned on purpose: a raw cell average mostly reflects WHICH players happened to
       draw that opponent, not how the opponent defends. Comparing each player to himself
       removes that. (Round-only de-conditioning once faked a +0.152 effect in PGA whose true
       value was +0.012 -- de-condition at the level the claim is made.)
    B. IS IT PRICED?  cell metric = hit rate against the REAL posted line.
       A can be strongly true while B is exactly zero -- that is what "the market already knows"
       looks like, and it is the most likely outcome given defence-vs-position is published
       publicly by every fantasy site.
Only if B survives is a betting test warranted.
"""
import sqlite3, collections, statistics as st

BOX = "/home/ubuntu/tennis-odds-collector/wnba_boxscores.sqlite"
P25 = "/home/ubuntu/tennis-odds-collector/wnba_props_2025.sqlite"
PH = "/home/ubuntu/tennis-odds-collector/wnba_props_hist.sqlite"

TEAMS = {"LV", "IND", "PHX", "MIN", "ATL", "NY", "SEA", "GS", "DAL", "CON", "LA", "CHI", "WSH"}
MK = {"player_points": ("pts", "rpts"), "player_rebounds": ("reb", "rreb"),
      "player_assists": ("ast", "rast")}


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
rows = [r for r in c.execute(
    "SELECT game_id,game_date,team,player,min,pts,reb,ast FROM box")]
gt = collections.defaultdict(set)
for gid, gd, team, pl, mn, pts, reb, ast in rows:
    gt[gid].add(team)
c.close()
opp = {}
for gid, v in gt.items():
    if len(v) == 2:
        a, b = list(v)
        opp[(gid, a)] = b; opp[(gid, b)] = a

lines = collections.defaultdict(dict)
for db in (P25, PH):
    cc = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    for gd, mk, pl, sd, ln in cc.execute(
            "SELECT game_date,market,player,side,line FROM props WHERE line IS NOT NULL"):
        if str(sd).lower() == "over":
            lines[(norm(pl), str(gd)[:10])][mk] = float(ln)
    cc.close()

# season baselines per player (their own average -- the de-conditioning reference)
per = collections.defaultdict(lambda: collections.defaultdict(float))
for gid, gd, team, pl, mn, pts, reb, ast in rows:
    if not mn or mn < 5:
        continue
    p = per[norm(pl)]
    p["min"] += mn; p["pts"] += pts or 0; p["reb"] += reb or 0; p["ast"] += ast or 0; p["g"] += 1
pool = {k: v for k, v in per.items() if v["g"] >= 10 and v["min"] >= 150}
for v in pool.values():
    for r, s in (("rpts", "pts"), ("rreb", "reb"), ("rast", "ast")):
        v[r] = 36.0 * v[s] / v["min"]
    v["tilt"] = v["rreb"] - v["rast"]
tl = sorted(v["tilt"] for v in pool.values())
lo, hi = tl[len(tl) // 3], tl[2 * len(tl) // 3]
for v in pool.values():
    v["size"] = "big" if v["tilt"] >= hi else ("guard" if v["tilt"] < lo else "wing")
cut = {}
for sz in ("big", "wing", "guard"):
    for _mk, (_s, r) in MK.items():
        vals = sorted(v[r] for v in pool.values() if v["size"] == sz)
        cut[(sz, r)] = vals[2 * len(vals) // 3]          # top tercile = "good at it"

dates = sorted({str(r[1])[:10] for r in rows})
mid = dates[len(dates) // 2]
print("season split: %s .. %s  |  %s .. %s" % (dates[0], mid, mid, dates[-1]))
print("players in pool: %d   (big/wing/guard %s)\n"
      % (len(pool), dict(collections.Counter(v["size"] for v in pool.values()))))

# build cell observations
cellA = collections.defaultdict(list)   # (size, market, opponent) -> [rel_production]
cellB = collections.defaultdict(list)
hitA = collections.defaultdict(list)    # -> [1/0 vs the line]
hitB = collections.defaultdict(list)
for gid, gd, team, pl, mn, pts, reb, ast in rows:
    gd = str(gd)[:10]
    p = pool.get(norm(pl))
    o = opp.get((gid, team))
    if not p or o not in TEAMS or not mn or mn < 5:
        continue
    got = {"pts": pts or 0, "reb": reb or 0, "ast": ast or 0}
    for mk, (s, r) in MK.items():
        if p[r] < cut[(p["size"], r)]:
            continue                                     # not "good at it"
        key = (p["size"], mk, o)
        rel = (36.0 * got[s] / mn) - p[r]                # vs the player's OWN season rate
        (cellA if gd <= mid else cellB)[key].append(rel)
        L = lines.get((norm(pl), gd), {}).get(mk)
        if L is not None and got[s] != L:
            (hitA if gd <= mid else hitB)[key].append(1 if got[s] > L else 0)

print("=== A. IS THE EFFECT REAL? split-half reliability of cell strength ===")
print("    (production relative to each player's OWN season rate, so it is the OPPONENT")
print("     being measured and not which players happened to face them)")
for mk in MK:
    pairs = []
    for k in set(cellA) & set(cellB):
        if k[1] != mk or len(cellA[k]) < 8 or len(cellB[k]) < 8:
            continue
        pairs.append((st.mean(cellA[k]), st.mean(cellB[k])))
    r, n = corr(pairs)
    print("  %-24s r = %s   over %d cells"
          % (mk, ("%+.3f" % r) if r is not None else " n/a ", n))
allp = []
for k in set(cellA) & set(cellB):
    if len(cellA[k]) >= 8 and len(cellB[k]) >= 8:
        allp.append((st.mean(cellA[k]), st.mean(cellB[k])))
r, n = corr(allp)
print("  %-24s r = %s   over %d cells   <-- the headline"
      % ("ALL MARKETS POOLED", ("%+.3f" % r) if r is not None else " n/a ", n))
print("   r near 0 => a hot cell in the first half tells you nothing about the second.")

print("\n=== B. IS IT PRICED? split-half reliability of the cell's HIT RATE vs the real line ===")
allh = []
for mk in MK:
    pairs = []
    for k in set(hitA) & set(hitB):
        if k[1] != mk or len(hitA[k]) < 6 or len(hitB[k]) < 6:
            continue
        pairs.append((st.mean(hitA[k]), st.mean(hitB[k])))
    allh += pairs
    r, n = corr(pairs)
    print("  %-24s r = %s   over %d cells"
          % (mk, ("%+.3f" % r) if r is not None else " n/a ", n))
r, n = corr(allh)
print("  %-24s r = %s   over %d cells   <-- the headline"
      % ("ALL MARKETS POOLED", ("%+.3f" % r) if r is not None else " n/a ", n))

print("\n=== C. THE ACTUAL BET: pick the hot cells in half 1, bet them in half 2 ===")
for thr in (0.60, 0.65):
    picks = [k for k in hitA if len(hitA[k]) >= 6 and st.mean(hitA[k]) >= thr]
    bets = [x for k in picks for x in hitB.get(k, [])]
    if len(bets) >= 25:
        w = sum(bets)
        print("  cells hitting >=%.0f%% in half 1: %-3d -> in half 2 they went %d-%d = %.1f%%"
              % (100 * thr, len(picks), w, len(bets) - w, 100 * w / len(bets)))
    else:
        print("  cells hitting >=%.0f%% in half 1: %-3d -> only %d bets in half 2 (thin)"
              % (100 * thr, len(picks), len(bets)))
base = [x for v in hitB.values() for x in v]
print("  baseline: ALL qualifying plays in half 2 went %.1f%% over (n=%d)"
      % (100 * st.mean(base), len(base)))
print("  (a real system beats that baseline; -110 needs 52.4%%)")
