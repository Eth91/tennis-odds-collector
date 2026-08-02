"""Record by n_without — how many games the team had played without the star WHEN THE BET WAS MADE.

CRITICAL: n_without must be computed AS OF pred_date, not today. ESPN game logs keep growing, so a
bet placed at n_without=1 would look like n_without=6 now, and every bucket would be contaminated
with hindsight. Every log below is truncated to games strictly BEFORE the bet's own date.

Why this matters right now: Carleton and DiLeo BOTH sit at n_without=2 tonight. If the n=2 cell is
weak, the interesting question stops being "which of the two" and becomes "either of them at all".

Reported on the raw graded overs AND on the post-selection universe (current_selection + role gate),
because those answer different questions and the house rule is to judge on what the bot actually
bets. Day-clustered intervals throughout.
"""
import random
import sqlite3
from collections import defaultdict

import wnba_wowy as W

con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
ALL = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()
ALL = [r for r in ALL if r.get("result") in ("over", "under") and r.get("odds")]
OV = [r for r in ALL if (r.get("side") or "over") == "over"]

ids = W.roster_ids() or {}
_cache = {}


def log_of(name):
    if name not in _cache:
        pid = ids.get(name)
        try:
            _cache[name] = W.game_log(pid) if pid else []
        except Exception:                                          # noqa: BLE001
            _cache[name] = []
    return _cache[name]


def before(log, date):
    return [g for g in log if (g.get("date") or "")[:10] < date[:10]]


def n_without_asof(r):
    """Games the beneficiary played that the out player(s) MISSED, counting only games before the
    bet. Multiple outs -> the combined-absence count, matching wowy_multi in the live path."""
    pl = r.get("player")
    outs = [x.strip() for x in str(r.get("out_player") or "").split(",") if x.strip()]
    d = str(r.get("pred_date"))[:10]
    blog = before(log_of(pl), d)
    if not blog or not outs:
        return None
    ologs = [before(log_of(o), d) for o in outs]
    ologs = [o for o in ologs if o]
    if not ologs:
        return None
    try:
        w = W.wowy_multi(blog, ologs) if len(ologs) > 1 else W.wowy(blog, ologs[0])
    except Exception:                                              # noqa: BLE001
        return None
    return w.get("n_without")


for r in OV:
    r["_nw"] = n_without_asof(r)

try:
    import wnba_slip as S
    SEL, _ = S.current_selection(OV, commit=False)
except Exception as e:                                             # noqa: BLE001
    print("  current_selection failed (%r)" % (e,))
    SEL = OV
UNI = [r for r in SEL if str(r.get("confidence")) in {"confirmed", "likely"}]

res = sum(1 for r in OV if r["_nw"] is None)
print("  graded overs %d (n_without resolved for %d, unresolved %d)" % (len(OV), len(OV) - res, res))


def ret(r):
    return (float(r["odds"]) - 1) if r["result"] == "over" else -1.0


def boot(rows, iters=2000):
    byd = defaultdict(list)
    for r in rows:
        byd[str(r.get("pred_date"))[:10]].append(ret(r))
    ks = list(byd)
    if len(ks) < 2:
        return None
    rng = random.Random(7)
    sims = []
    for _ in range(iters):
        s = [x for k in rng.choices(ks, k=len(ks)) for x in byd[k]]
        if s:
            sims.append(sum(s) / len(s))
    sims.sort()
    return sims[int(.025 * len(sims))], sims[int(.975 * len(sims))]


def show(label, rows):
    if not rows:
        print("  %-24s (none)" % label)
        return
    n = len(rows)
    w = sum(1 for r in rows if r["result"] == "over")
    u = sum(ret(r) for r in rows)
    ci = boot(rows)
    print("  %-24s %4d %5d-%-4d %6.1f%% %+8.2fu %+7.1f%%  %s"
          % (label, n, w, n - w, 100 * w / n, u, 100 * u / n,
             ("CI %+.0f%%..%+.0f%%" % (100 * ci[0], 100 * ci[1])) if ci else "CI n/a"))


def bucket(nw):
    if nw is None:
        return "unresolved"
    if nw <= 0:
        return "n=0 (cold)"
    if nw == 1:
        return "n=1"
    if nw == 2:
        return "n=2"
    return "n>=3"


ORDER = ["n=0 (cold)", "n=1", "n=2", "n>=3", "unresolved"]
for title, pool in (("ALL graded overs", OV),
                    ("POST-SELECTION + role gate (what the bot bets)", UNI)):
    print("\n=== %s, by n_without AS OF the bet ===" % title)
    print("  %-24s %4s %10s %7s %9s %8s" % ("bucket", "n", "record", "hit%", "units", "ROI"))
    byb = defaultdict(list)
    for r in pool:
        byb[bucket(r.get("_nw"))].append(r)
    for k in ORDER:
        if k in byb:
            show(k, byb[k])
    show("-- ALL --", pool)

print("\n=== n=2 split by stat family (the memory note says n=1 was ALL rebounds) ===")
for title, pool in (("ALL graded overs", OV), ("POST-SELECTION", UNI)):
    print("  -- %s" % title)
    for nwv in (1, 2):
        sub = [r for r in pool if r.get("_nw") == nwv]
        pts = [r for r in sub if r.get("stat") == "points"]
        reb = [r for r in sub if "reb" in str(r.get("stat"))]
        oth = [r for r in sub if r not in pts and r not in reb]
        show("  n=%d points" % nwv, pts)
        show("  n=%d rebounds-family" % nwv, reb)
        show("  n=%d other" % nwv, oth)

print("\n  Tonight both Carleton and DiLeo sit at n_without=2, so the n=2 row is the one that")
print("  decides whether EITHER play belongs on the card.")
