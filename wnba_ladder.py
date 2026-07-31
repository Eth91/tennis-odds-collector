"""Is laddering earning its money? Split the record into base rungs and reach rungs.

A ladder is 2+ lines on the same player+stat: the base (lowest line, best chance) plus reaches at
longer prices. Staking is 1u on the base then declining rungs (0.5 / 0.25 / ...), capped 2.5u per
player-stat, so a ladder risks up to 2.5x a single bet on one player's night.

The question the record can answer: do the REACH rungs pay for themselves, or is the base carrying
them? Reported at the real ladder stakes, because a rung's hit rate is meaningless without the size
it was bet at — a 30% rung at +250 on 0.25u is fine, the same rung flat-staked is not.

Also the counterfactual that matters: what would the record be if we had bet ONLY the base rung of
every ladder and skipped every reach? That is the actual decision — laddering versus not.

Universe = the board's record as it now counts it (current_selection + role gate, n1 excluded).
"""
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
SM = SL.ladder_stake_map(U)


def stake(r):
    return SM.get((r["pred_date"], r["player"], r["stat"], r["line"]), 1.0)


def won(r):
    return r["result"] == (r["side"] or "over")


def pnl(r, st=None):
    st = stake(r) if st is None else st
    return st * (float(r.get("odds") or 0) - 1) if won(r) else -st


# group into ladders
grp = defaultdict(list)
for r in U:
    grp[(r["pred_date"], r["player"], r["stat"])].append(r)
for k in grp:
    grp[k].sort(key=lambda r: r["line"])
    for i, r in enumerate(grp[k]):
        r["_rung"] = i
        r["_nrung"] = len(grp[k])

singles = [r for r in U if r["_nrung"] == 1]
lad = [r for r in U if r["_nrung"] > 1]


def boot(rows, iters=2000, unit=False):
    byd = defaultdict(list)
    for r in rows:
        byd[str(r.get("pred_date"))[:10]].append(pnl(r) / (stake(r) if unit else 1.0))
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
        print("  %-30s (none)" % lab)
        return
    w = sum(1 for r in rows if won(r))
    st = sum(stake(r) for r in rows)
    u = sum(pnl(r) for r in rows)
    ci = boot(rows)
    print("  %-30s %3d %2d-%-2d %6.1f%% %6.2fu %+8.2fu %+7.1f%%  %s"
          % (lab, n, w, n - w, 100 * w / n, st, u, 100 * u / st if st else 0,
             ("CI %+.0f%%..%+.0f%%" % (100 * ci[0], 100 * ci[1])) if ci else "CI n/a"))


print("  %-30s %3s %6s %7s %7s %9s %8s" % ("bucket", "n", "record", "hit%", "risked", "units", "ROI"))
show("SINGLE bets (no ladder)", singles)
show("LADDERED bets (all rungs)", lad)
print()
show("  ladder rung 1 (the base)", [r for r in lad if r["_rung"] == 0])
show("  ladder rung 2", [r for r in lad if r["_rung"] == 1])
show("  ladder rung 3+", [r for r in lad if r["_rung"] >= 2])
print()
show("  ALL reach rungs (2+)", [r for r in lad if r["_rung"] >= 1])

print("\n=== the actual decision: ladder, or just bet the base? ===")
base_only = singles + [r for r in lad if r["_rung"] == 0]
full = U
for lab, rows in (("bet EVERYTHING (what we do)", full),
                  ("bet BASE RUNGS ONLY", base_only)):
    n = len(rows)
    w = sum(1 for r in rows if won(r))
    st = sum(stake(r) for r in rows)
    u = sum(pnl(r) for r in rows)
    print("  %-30s %3d bets  %2d-%-2d  %6.1f%%  risked %5.2fu  %+8.2fu  ROI %+.1f%%"
          % (lab, n, w, n - w, 100 * w / n, st, u, 100 * u / st if st else 0))
d = sum(pnl(r) for r in lad if r["_rung"] >= 1)
ds = sum(stake(r) for r in lad if r["_rung"] >= 1)
print("  -> the reach rungs alone: %+.2fu on %.2fu risked (%+.1f%%)" % (d, ds, 100 * d / ds if ds else 0))

print("\n=== how far past the line do the reaches sit? (the Carleton question) ===")
print("  Carleton tonight: base o12.5, reach o14.5 — projection 16.1, but her two")
print("  games without Barker were 13 and 12 points.")
rows = []
for r in lad:
    if r["_rung"] == 0:
        continue
    base = grp[(r["pred_date"], r["player"], r["stat"])][0]
    rows.append((r["line"] - base["line"], won(r)))
for lo, hi, lab in ((0, 2.001, "reach +0 to +2"), (2.001, 4.001, "reach +2 to +4"),
                    (4.001, 99, "reach +4 or more")):
    sub = [x for x in rows if lo <= x[0] < hi]
    if sub:
        w = sum(1 for x in sub if x[1])
        print("  %-18s %3d rungs  %2d-%-2d  %5.1f%%" % (lab, len(sub), w, len(sub) - w,
                                                        100 * w / len(sub)))
