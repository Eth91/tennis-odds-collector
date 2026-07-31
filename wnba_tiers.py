"""Do A bets really beat B bets? And what tier do tonight's two plays actually get?

The claim is testable, so test it rather than agree with it. Tier is the canonical function:
    A = d_min in 3-8  AND  cascade favourite  AND  single stat (points/rebounds/assists)
    B = the solid middle
    C = combos and marginal
Note the FAVOURITE term — a play can be in-band and single-stat and still be B if a teammate in the
same team cascade has shorter odds. That interaction matters tonight.

Measured on the board's record as it now counts it (current_selection + role gate, n1 excluded),
with a day-clustered interval and a two-proportion test, because "A looks better than B" on ~40 bets
can easily be noise.
"""
import math
import random
import sqlite3
from collections import defaultdict

import wnba_slip as SL

BET_ROLES = {"confirmed", "likely"}
con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
g = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()
overs = [r for r in g if r["result"] in ("over", "under") and (r["side"] or "over") == "over"
         and (r.get("tier") or "firm") != "n1"]
dec, _ = SL.current_selection(overs)
U = [r for r in dec if str(r.get("confidence")) in BET_ROLES or r.get("played")]

favs = SL.fav_keys(U)
for r in U:
    r["_t"] = SL.tier_of(r, (r["pred_date"], r["player"], r["stat"]) in favs)


def won(r):
    return r["result"] == (r["side"] or "over")


def ret(r):
    return (float(r.get("odds") or 0) - 1) if won(r) else -1.0


def boot(rows, iters=2000):
    byd = defaultdict(list)
    for r in rows:
        byd[str(r.get("pred_date"))[:10]].append(ret(r))
    ks = list(byd)
    if len(ks) < 2:
        return None
    rng = random.Random(7)
    s = []
    for _ in range(iters):
        v = [x for k in rng.choices(ks, k=len(ks)) for x in byd[k]]
        if v:
            s.append(sum(v) / len(v))
    s.sort()
    return s[int(.025 * len(s))], s[int(.975 * len(s))]


def show(lab, rows):
    n = len(rows)
    if not n:
        print("  %-22s (none)" % lab)
        return
    w = sum(1 for r in rows if won(r))
    u = sum(ret(r) for r in rows)
    ci = boot(rows)
    print("  %-22s %3d %2d-%-2d %6.1f%% %+8.2fu %+7.1f%%  %s"
          % (lab, n, w, n - w, 100 * w / n, u, 100 * u / n,
             ("CI %+.0f%%..%+.0f%%" % (100 * ci[0], 100 * ci[1])) if ci else "CI n/a"))


print("  %-22s %3s %6s %7s %9s %8s" % ("tier", "n", "record", "hit%", "units", "ROI"))
byt = defaultdict(list)
for r in U:
    byt[r["_t"]].append(r)
for t in ("A", "B", "C"):
    show("tier %s" % t, byt[t])
show("ALL", U)

A, B = byt["A"], byt["B"]
if A and B:
    p1 = sum(1 for r in A if won(r)) / len(A)
    p2 = sum(1 for r in B if won(r)) / len(B)
    pp = (sum(1 for r in A if won(r)) + sum(1 for r in B if won(r))) / (len(A) + len(B))
    se = math.sqrt(pp * (1 - pp) * (1 / len(A) + 1 / len(B))) or 1e-9
    z = (p1 - p2) / se
    print("\n  A %.1f%% vs B %.1f%%   difference %+.1f pts   z = %+.2f  (%s)"
          % (100 * p1, 100 * p2, 100 * (p1 - p2), z,
             "significant" if abs(z) >= 1.96 else "NOT significant — consistent with chance"))
    print("  units per bet: A %+.3fu   B %+.3fu"
          % (sum(ret(r) for r in A) / len(A), sum(ret(r) for r in B) / len(B)))

# ── what tier do tonight's plays get? ─────────────────────────────────────────
print("\n=== tonight (2026-07-31), tier computed the canonical way ===")
con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
T = [dict(zip(cols, r)) for r in con.execute(
    "SELECT * FROM predictions WHERE pred_date='2026-07-31'")]
con.close()
tf = SL.fav_keys(T)
for r in T:
    t = SL.tier_of(r, (r["pred_date"], r["player"], r["stat"]) in tf)
    print("  %-20s %-8s o%-6s odds=%-7s d_min=%-5s fav=%-5s -> tier %s"
          % (r["player"], r["stat"], r["line"], r["odds"], r.get("d_min"),
             (r["pred_date"], r["player"], r["stat"]) in tf, t))

print("\n  DiLeo is NOT in the ledger tonight (the correlation cap removed her). What tier")
print("  WOULD she be, if she were in the pool alongside Carleton?")
dl = {"pred_date": "2026-07-31", "player": "Megan DiLeo", "team": "POR", "stat": "points",
      "line": 14.5, "odds": 2.04, "ev": 0.267, "d_min": 4.2,
      "confidence": "likely", "side": "over"}
pool = [dict(r) for r in T] + [dl]
pf = SL.fav_keys(pool)
for r in pool:
    if r["team"] != "POR":
        continue
    t = SL.tier_of(r, (r["pred_date"], r["player"], r["stat"]) in pf)
    print("    %-20s odds=%-7s d_min=%-5s fav=%-5s -> tier %s"
          % (r["player"], r["odds"], r.get("d_min"),
             (r["pred_date"], r["player"], r["stat"]) in pf, t))
print("\n  The FAVOURITE term is decided by shortest odds in the team cascade, so whichever of")
print("  the two is priced shorter takes the A — the band alone does not confer it.")
