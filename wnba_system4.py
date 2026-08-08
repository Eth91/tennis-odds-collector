#!/usr/bin/env python3
"""SYSTEM PLAYS, separating two questions the 3-season run accidentally merged.

WHAT THE LAST RUN EXPOSED
    Reliability FELL when seasons were added (+0.323 on 2025 alone -> +0.209 across 2023-25).
    More data should not lower reliability, so the split itself was the problem: the median-date
    split put 2023+2024 in one half and 2025 in the other, i.e. it measured whether a team's
    defensive tendency SURVIVES A ROSTER TURNOVER. That is a different and much harder question
    than whether the tendency is real inside a season.

SO TEST BOTH, SEPARATELY:
  A. WITHIN-SEASON  -- split each season at its own midpoint, correlate. Is the tendency real?
  B. ACROSS-SEASON  -- correlate season N's cells with season N+1's. Does it carry over?
     This one decides usability: if a tendency does not survive the offseason, you cannot bet it
     early in a year, and every cell must be re-learned from scratch each season.
  C. THE BET        -- restricted to seasons that actually have posted lines. The prop archive
     covers 2025-2026 only, so the earlier "bet thin (n=0)" was a coverage artifact, not a result.

Thresholds are explicit and position-specific, printed in per-36 terms, swept at 33/25/20%.
"""
import sqlite3, collections, statistics as st

BOX = "/home/ubuntu/tennis-odds-collector/wnba_boxscores.sqlite"
P25 = "/home/ubuntu/tennis-odds-collector/wnba_props_2025.sqlite"
PH = "/home/ubuntu/tennis-odds-collector/wnba_props_hist.sqlite"
MK = {"player_points": ("pts", "rpts"), "player_rebounds": ("reb", "rreb"),
      "player_assists": ("ast", "rast")}
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
    by[(gid, team)].append((norm(pl), mn or 0))
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

slots = collections.defaultdict(collections.Counter)
for v in by.values():
    for i, (pl, mn) in enumerate(v[:5]):
        slots[pl][i] += 1
modal = {pl: cnt.most_common(1)[0][0] for pl, cnt in slots.items() if sum(cnt.values()) >= 5}

# per-SEASON player baselines: a player's rate changes year to year, so the de-conditioning
# reference must be their rate THAT season, not a career average.
flat, per = [], collections.defaultdict(lambda: collections.defaultdict(float))
for rid, gid, gd, team, pl, mn, pts, reb, ast in rows:
    pl = norm(pl); gd = str(gd)[:10]; yr = gd[:4]
    flat.append((gid, gd, yr, team, pl, mn or 0, pts or 0, reb or 0, ast or 0))
    if mn and mn >= 5:
        p = per[(pl, yr)]
        p["min"] += mn; p["pts"] += pts or 0; p["reb"] += reb or 0
        p["ast"] += ast or 0; p["g"] += 1
pool = {k: v for k, v in per.items() if v["g"] >= 8 and v["min"] >= 120 and k[0] in modal}
for v in pool.values():
    for r, s in (("rpts", "pts"), ("rreb", "reb"), ("rast", "ast")):
        v[r] = 36.0 * v[s] / v["min"]
print("player-seasons in pool: %d" % len(pool))

lines = collections.defaultdict(dict)
for db in (P25, PH):
    cc = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    for gd, mk, pl, sd, ln in cc.execute(
            "SELECT game_date,market,player,side,line FROM props WHERE line IS NOT NULL"):
        if str(sd).lower() == "over":
            lines[(norm(pl), str(gd)[:10])][mk] = float(ln)
    cc.close()

SEASONS = sorted({f[2] for f in flat})
mids = {}
for y in SEASONS:
    d = sorted({f[1] for f in flat if f[2] == y})
    mids[y] = d[len(d) // 2] if d else None


def build(pct):
    """-> cells[(season, half)][key] = [rel], hits[(season, half)][key] = [1/0]"""
    cut = {}
    for pos in ("G", "F", "C"):
        for mk, (_s, r) in MK.items():
            vals = sorted(v[r] for k, v in pool.items() if SLOT3[modal[k[0]]] == pos)
            if len(vals) >= 8:
                cut[(pos, r)] = vals[int(len(vals) * (1 - pct))]
    cells = collections.defaultdict(lambda: collections.defaultdict(list))
    hits = collections.defaultdict(lambda: collections.defaultdict(list))
    for gid, gd, yr, team, pl, mn, pts, reb, ast in flat:
        p = pool.get((pl, yr)); o = opp.get((gid, team))
        if not p or o not in TEAMS or mn < 5:
            continue
        pos = SLOT3[modal[pl]]
        got = {"pts": pts, "reb": reb, "ast": ast}
        half = 0 if gd <= mids[yr] else 1
        for mk, (s, r) in MK.items():
            if (pos, r) not in cut or p[r] < cut[(pos, r)]:
                continue
            key = (pos, mk, o)
            cells[(yr, half)][key].append((36.0 * got[s] / mn) - p[r])
            L = lines.get((pl, gd), {}).get(mk)
            if L is not None and got[s] != L:
                hits[(yr, half)][key].append(1 if got[s] > L else 0)
    return cells, hits, cut


for pct, tag in ((0.33, "top33"), (0.25, "top25")):
    cells, hits, cut = build(pct)
    print("\n" + "=" * 74)
    print("THRESHOLD = %s (top %d%% within position)" % (tag, 100 * pct))
    print("=" * 74)

    print("A. WITHIN-SEASON reliability (is the tendency real inside a year?)")
    for y in SEASONS:
        a, b = cells.get((y, 0), {}), cells.get((y, 1), {})
        r, n = corr([(st.mean(a[k]), st.mean(b[k])) for k in set(a) & set(b)
                     if len(a[k]) >= 6 and len(b[k]) >= 6])
        print("   %s   r = %-8s over %3d cells" % (y, ("%+.3f" % r) if r is not None else "n/a", n))

    print("B. ACROSS-SEASON persistence (does it survive the offseason?)")
    for i in range(len(SEASONS) - 1):
        y1, y2 = SEASONS[i], SEASONS[i + 1]
        A = collections.defaultdict(list); B = collections.defaultdict(list)
        for h in (0, 1):
            for k, v in cells.get((y1, h), {}).items():
                A[k] += v
            for k, v in cells.get((y2, h), {}).items():
                B[k] += v
        r, n = corr([(st.mean(A[k]), st.mean(B[k])) for k in set(A) & set(B)
                     if len(A[k]) >= 10 and len(B[k]) >= 10])
        print("   %s -> %s   r = %-8s over %3d cells"
              % (y1, y2, ("%+.3f" % r) if r is not None else "n/a", n))

    print("C. THE BET, within each season that has posted lines")
    for y in SEASONS:
        hA, hB = hits.get((y, 0), {}), hits.get((y, 1), {})
        if not hA or not hB:
            continue
        picks = [k for k in hA if len(hA[k]) >= 5 and st.mean(hA[k]) >= 0.60]
        bets = [x for k in picks for x in hB.get(k, [])]
        base = [x for v in hB.values() for x in v]
        if len(bets) >= 30:
            w = sum(bets)
            print("   %s  %d hot cells -> %d-%d = %5.1f%%   (baseline %5.1f%%, n=%d)"
                  % (y, len(picks), w, len(bets) - w, 100 * w / len(bets),
                     100 * st.mean(base), len(base)))
        elif base:
            print("   %s  only %d bets in half 2 (thin); baseline %5.1f%% n=%d"
                  % (y, len(bets), 100 * st.mean(base), len(base)))
    print("   need 52.4% at -110 | 51.0% at the best-of-8 shopped price")

print("\n=== THE THRESHOLDS in plain terms (top 25%) ===")
_c, _h, cut = build(0.25)
nm = {"rpts": "points", "rreb": "rebounds", "rast": "assists"}
for pos, word in (("G", "GUARD"), ("F", "FORWARD"), ("C", "CENTER")):
    print("   a GOOD %-8s: %s" % (word, "   |   ".join(
        "%s/36 >= %4.1f" % (nm[r], cut[(pos, r)]) for r in ("rpts", "rreb", "rast")
        if (pos, r) in cut)))
