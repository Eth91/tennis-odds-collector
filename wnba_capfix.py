"""What would fixing the correlation cap do to the 33-15 record?

THE FIX. The cap ranks (oob, odds, -ev) with oob = d_min<0 or >8 (the SHADOW band). Selection's gkey
uses 3<=d_min<=8 (the A-band). Where both legs sit inside 0-8 the cap's band term is a no-op and a
hair of odds decides — which is how Carleton (0.3) beat DiLeo (4.2). The fix is to rank the cap on
the A-band, matching selection.

RECONSTRUCTION, and its limits stated up front. Capped legs are deleted before the ledger write, so
they have no stored result — but wnba_capped_legs.csv records BOTH sides of every contest with
line/odds/ev/d_min, and the ESPN game log supplies the actual stat, so the loser of each contest can
be graded after the fact. That is the whole reason the breadcrumb exists.

Three honest caveats:
  * the capped leg's odds are those at cap time, which may not be what we would have got;
  * swapping a leg changes which plays compete for the TOP-2 slots downstream, so this is a
    first-order estimate, not a full replay of the season;
  * the capped leg's role comes from wnba_proj_log (which logs every beneficiary's confidence),
    since capped legs never reach the predictions table — the role gate is applied to it too, so
    the swap cannot smuggle in a play the bot would refuse.
"""
import csv
import os
import random
import sqlite3
from collections import defaultdict

import wnba_slip as SL
import wnba_wowy as W

BET_ROLES = {"confirmed", "likely"}

# ── the record as the board now counts it ──────────────────────────────────────
con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
g = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()
overs = [r for r in g if r["result"] in ("over", "under") and (r["side"] or "over") == "over"
         and (r.get("tier") or "firm") != "n1"]
dec, _ = SL.current_selection(overs)
BASE = [r for r in dec if str(r.get("confidence")) in BET_ROLES or r.get("played")]

# ── roles for capped legs, from the projection log ─────────────────────────────
role = {}
if os.path.exists("wnba_proj_log.sqlite"):
    pc = sqlite3.connect("wnba_proj_log.sqlite")
    for d_, p_, c_ in pc.execute("SELECT date, player, confidence FROM projections"):
        role[(str(d_)[:10], p_)] = str(c_)
    pc.close()

# ── the contests ───────────────────────────────────────────────────────────────
seen = {}
with open("wnba_capped_legs.csv") as f:
    for r in csv.reader(f):
        if len(r) < 9:
            continue
        try:
            k = (r[0], r[1], r[2], r[3], r[4], float(r[5]))
            seen[k] = {"date": r[0], "team": r[1], "kept": r[2], "capped": r[3], "stat": r[4],
                       "line": float(r[5]), "odds": float(r[6] or 0), "ev": float(r[7] or 0),
                       "d_min": float(r[8]) if r[8] not in ("", "None") else None}
        except ValueError:
            continue
contests = list(seen.values())

ids = W.roster_ids() or {}
_c = {}


def actual(name, date, stat):
    if name not in _c:
        pid = ids.get(name)
        try:
            _c[name] = W.game_log(pid) if pid else []
        except Exception:                                          # noqa: BLE001
            _c[name] = []
    for gm in _c[name]:
        if (gm.get("date") or "")[:10] != date[:10]:
            continue
        p, rb, a = gm.get("pts"), gm.get("reb"), gm.get("ast")
        if p is None:
            return None
        return {"points": p, "rebounds": rb, "assists": a,
                "pra": (p or 0) + (rb or 0) + (a or 0),
                "pts_reb": (p or 0) + (rb or 0), "pts_ast": (p or 0) + (a or 0),
                "reb_ast": (rb or 0) + (a or 0)}.get(stat)
    return None


def aband(x):
    return 0 if (x is not None and 3 <= x <= 8) else 1


bykey = {(r["pred_date"], r["player"], r["stat"]): r for r in BASE}
swaps, blocked = [], []
stat = {"contests": len(contests), "kept_in_record": 0, "same_pick": 0, "would_flip": 0}
band_pairs = []
for c in contests:
    kr = bykey.get((c["date"], c["kept"], c["stat"]))
    if kr is None:
        continue                                   # the kept leg isn't in the counted record
    stat["kept_in_record"] += 1
    band_pairs.append((kr.get("d_min"), c["d_min"]))
    # would the A-BAND rule have preferred the capped leg?
    kept_key = (aband(kr.get("d_min")), float(kr.get("odds") or 99), -(kr.get("ev") or 0))
    cap_key = (aband(c["d_min"]), c["odds"], -c["ev"])
    if kept_key <= cap_key:
        stat["same_pick"] += 1
        continue                                   # fix keeps the same leg -> no change
    stat["would_flip"] += 1
    cr = role.get((c["date"], c["capped"]))
    if cr is not None and cr not in BET_ROLES:
        blocked.append((c, cr))
        continue                                   # the swap-in fails the role gate
    ca = actual(c["capped"], c["date"], c["stat"])
    if ca is None:
        blocked.append((c, "ungradeable"))
        continue
    swaps.append((kr, c, 1 if ca > c["line"] else 0))


def ret_row(r):
    return (float(r.get("odds") or 0) - 1) if r["result"] == (r["side"] or "over") else -1.0


def rec(rows, extra=()):
    n = len(rows) + len(extra)
    w = sum(1 for r in rows if r["result"] == (r["side"] or "over")) + sum(x[0] for x in extra)
    u = sum(ret_row(r) for r in rows) + sum(x[1] for x in extra)
    return n, w, u


print("\n=== is the 0 meaningful, or is the population empty? ===")
print("  logged cap contests                    %d" % stat["contests"])
print("  ...whose KEPT leg is in the 48-bet record  %d" % stat["kept_in_record"])
print("  ...where the A-band rule agrees            %d" % stat["same_pick"])
print("  ...where it would FLIP                     %d" % stat["would_flip"])
if band_pairs:
    both_in = sum(1 for a,b in band_pairs if (a is not None and 3<=a<=8) and (b is not None and 3<=b<=8))
    both_out= sum(1 for a,b in band_pairs if not(a is not None and 3<=a<=8) and not(b is not None and 3<=b<=8))
    split   = len(band_pairs)-both_in-both_out
    print("  band composition of those contests: both IN 3-8 = %d, both OUT = %d, SPLIT = %d"
          % (both_in, both_out, split))
    print("  (only a SPLIT contest can ever flip — that is the Carleton/DiLeo shape)")
    for a,b in band_pairs[:12]:
        print("      kept d_min=%-6s vs capped d_min=%-6s  %s" % (a,b,
              "SPLIT" if ((a is not None and 3<=a<=8) != (b is not None and 3<=b<=8)) else ""))

n0, w0, u0 = rec(BASE)
print("  BASE (the board's record today)      %d bets  %d-%d  %.1f%%  %+.2fu"
      % (n0, w0, n0 - w0, 100 * w0 / n0, u0))
print("\n=== contests the A-band fix would flip: %d ===" % len(swaps))
print("  %-11s %-4s %-8s %-26s %-26s" % ("date", "tm", "stat", "OUT (kept today)", "IN (capped today)"))
drop_keys = set()
add = []
for kr, c, cw in swaps:
    drop_keys.add((kr["pred_date"], kr["player"], kr["stat"], kr["line"]))
    dec_odds = c["odds"] if c["odds"] > 1 else 2.0
    add.append((cw, (dec_odds - 1) if cw else -1.0))
    kw = kr["result"] == (kr["side"] or "over")
    print("  %-11s %-4s %-8s %-26s %-26s"
          % (c["date"], c["team"], c["stat"],
             "%s dm%s %s" % (kr["player"][:14], kr.get("d_min"), "W" if kw else "L"),
             "%s dm%s %s" % (c["capped"][:14], c["d_min"], "W" if cw else "L")))
if blocked:
    print("\n  swaps BLOCKED (role gate or ungradeable): %d" % len(blocked))
    for c, why in blocked:
        print("    %-11s %-16s -> %s" % (c["date"], c["capped"][:16], why))

kept_rows = [r for r in BASE
             if (r["pred_date"], r["player"], r["stat"], r["line"]) not in drop_keys]
n1_, w1_, u1_ = rec(kept_rows, add)
print("\n=== effect on the record ===")
print("  before  %d bets  %d-%d  %.1f%%  %+.2fu" % (n0, w0, n0 - w0, 100 * w0 / n0, u0))
print("  after   %d bets  %d-%d  %.1f%%  %+.2fu" % (n1_, w1_, n1_ - w1_, 100 * w1_ / max(n1_, 1), u1_))
print("  delta   %+d bets, %+.1f pts of hit rate, %+.2fu"
      % (n1_ - n0, 100 * w1_ / max(n1_, 1) - 100 * w0 / n0, u1_ - u0))
print("\n  First-order only: swapping a leg also changes which plays win the TOP-2 slots on that")
print("  team-game, which this does not re-run. Treat the direction as informative, the")
print("  magnitude as approximate.")
