"""n_without record on the FLAGGED/BET universe only — not every tracked row.

I reported n>=3 as 34-43 / -11.8u. That was ALL graded overs, which includes rows the gates already
threw away and the bot never bet. Profiling that set is the documented way to invent a finding here
(the "d_min>8 bleeds -8.79u" bucket turned out to be pre-gate legacy rows). The number that matters
is the one on bets that actually made the card.

Several definitions of "flagged" exist and they are not identical, so all are shown rather than
picking the flattering one:
  A. post-selection + role gate — the tracker's own universe
  B. bettable = 1                — the role gate's own flag on the row
  C. in the `selections` table   — what was actually carded that day
  D. played = 1                  — real money down

If the conclusion depends on which definition is used, that is itself the finding.
"""
import random
import sqlite3
from collections import defaultdict

import wnba_wowy as W

con = sqlite3.connect("wnba_ledger.sqlite")
con.row_factory = sqlite3.Row
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
ALL = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
selkeys = {(r["pred_date"], r["player"], r["stat"])
           for r in con.execute("SELECT pred_date, player, stat FROM selections")}
con.close()
ALL = [r for r in ALL if r.get("result") in ("over", "under") and r.get("odds")]
OV = [r for r in ALL if (r.get("side") or "over") == "over"]

ids = W.roster_ids() or {}
_c = {}


def log_of(n):
    if n not in _c:
        pid = ids.get(n)
        try:
            _c[n] = W.game_log(pid) if pid else []
        except Exception:                                          # noqa: BLE001
            _c[n] = []
    return _c[n]


def nw_asof(r):
    d = str(r.get("pred_date"))[:10]
    bl = [g for g in log_of(r.get("player")) if (g.get("date") or "")[:10] < d]
    outs = [x.strip() for x in str(r.get("out_player") or "").split(",") if x.strip()]
    ol = [[g for g in log_of(o) if (g.get("date") or "")[:10] < d] for o in outs]
    ol = [o for o in ol if o]
    if not bl or not ol:
        return None
    try:
        w = W.wowy_multi(bl, ol) if len(ol) > 1 else W.wowy(bl, ol[0])
    except Exception:                                              # noqa: BLE001
        return None
    return w.get("n_without")


for r in OV:
    r["_nw"] = nw_asof(r)

import wnba_slip as S
SEL, _ = S.current_selection(OV, commit=False)
A = [r for r in SEL if str(r.get("confidence")) in {"confirmed", "likely"}]
B = [r for r in OV if r.get("bettable") == 1]
C = [r for r in OV if (r.get("pred_date"), r.get("player"), r.get("stat")) in selkeys]
D = [r for r in OV if r.get("played") == 1]


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
    s2 = []
    for _ in range(iters):
        s = [x for k in rng.choices(ks, k=len(ks)) for x in byd[k]]
        if s:
            s2.append(sum(s) / len(s))
    s2.sort()
    return s2[int(.025 * len(s2))], s2[int(.975 * len(s2))]


def show(label, rows):
    if not rows:
        print("  %-22s (none)" % label)
        return
    n = len(rows)
    w = sum(1 for r in rows if r["result"] == "over")
    u = sum(ret(r) for r in rows)
    ci = boot(rows)
    print("  %-22s %4d %5d-%-4d %6.1f%% %+8.2fu %+7.1f%%  %s"
          % (label, n, w, n - w, 100 * w / n, u, 100 * u / n,
             ("CI %+.0f%%..%+.0f%%" % (100 * ci[0], 100 * ci[1])) if ci else "CI n/a"))


def bk(nw):
    return ("n=0" if (nw or 0) <= 0 else "n=1" if nw == 1 else "n=2" if nw == 2
            else "n>=3") if nw is not None else "unresolved"


for lab, pool in (("A. post-selection + role gate (tracker)", A),
                  ("B. bettable = 1", B),
                  ("C. in the selections table (carded)", C),
                  ("D. played = 1 (real money)", D)):
    print("\n=== %s  [%d bets] ===" % (lab, len(pool)))
    print("  %-22s %4s %10s %7s %9s %8s" % ("bucket", "n", "record", "hit%", "units", "ROI"))
    byb = defaultdict(list)
    for r in pool:
        byb[bk(r.get("_nw"))].append(r)
    for k in ("n=0", "n=1", "n=2", "n>=3", "unresolved"):
        if k in byb:
            show(k, byb[k])
    thin = [r for r in pool if r.get("_nw") is not None and r["_nw"] <= 2]
    deep = [r for r in pool if r.get("_nw") is not None and r["_nw"] >= 3]
    show("  n<=2 combined", thin)
    show("  n>=3 combined", deep)
    show("-- ALL --", pool)
    if thin and deep:
        import math
        p1 = sum(1 for r in thin if r["result"] == "over") / len(thin)
        p2 = sum(1 for r in deep if r["result"] == "over") / len(deep)
        pp = ((p1 * len(thin)) + (p2 * len(deep))) / (len(thin) + len(deep))
        se = math.sqrt(pp * (1 - pp) * (1 / len(thin) + 1 / len(deep))) or 1e-9
        print("    thin %.1f%% vs deep %.1f%%  ->  z = %+.2f" % (100 * p1, 100 * p2, (p1 - p2) / se))

print("\n  If n>=3 is PROFITABLE on the flagged set, the gates already remove the bad part of it")
print("  and 'cut n>=3' would be cutting winners. The all-rows table cannot tell you that.")
