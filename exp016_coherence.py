#!/usr/bin/env python3
"""EXP-016 — is the book internally COHERENT across its own related markets? No model at all.

Every edge tested so far has been "our number vs their number", and the book has won every time.
This asks a different question, one that needs no model and cannot be beaten by the book being
smarter than us: do FanDuel's own prices contradict each other?

Three orderings are forced by logic alone, for the same player in the same event:

  A  DOMINANCE.   "Top 20 (Incl. Ties)" pays in every case "Top 20" (dead heat) pays and MORE:
                  a five-way tie for 18th pays in full on incl.-ties and a fraction on dead heat.
                  So P(ties) >= P(dead heat), and therefore odds_ties <= odds_dh. A book offering
                  LONGER odds on the strictly-more-likely event is priced wrong, full stop --
                  whatever the true probability is, the dead-heat bet is dominated by it.
  B  NESTING.     top5 subset of top10 subset of top20, so odds must be non-increasing.
  C  WIN.         winning is a subset of top 5.

EXP-015 makes this worth asking: the same nominal market carries a 11.2% hold as dead-heat and a
~30% hold as incl.-ties. A 19-point spread on two products over the same event is where an
internal contradiction would hide.

WHAT COUNTS AS A FINDING. Violations are tested at the RAW OFFERED ODDS, not on devigged
probabilities. A devigged violation can be manufactured by the devig itself (EXP-015: proportional
vs Shin move the longshot end by 142 points). A raw-odds dominance violation cannot -- it is a
statement about two prices the book is actually offering, and no normalisation is involved.
"""
import re
import sqlite3
from collections import defaultdict

import numpy as np

import pga_ruler as RU

m = sqlite3.connect("file:golf_moves.sqlite?mode=ro", uri=True, timeout=60)
rows = m.execute("SELECT event, market, mtype, runner, close_odds, close_ts FROM moves "
                 "WHERE close_odds IS NOT NULL AND (mtype LIKE 'TOP_%' OR mtype='WIN_ONLY_IMG')"
                 ).fetchall()
m.close()

best = {}
for ev, mk, mt, run, od, ts in rows:
    k = (" ".join(str(ev).split()), mt, RU.norm(run))
    if k not in best or str(ts) > best[k][0]:
        best[k] = (str(ts), float(od))
print("field-market close rows: %d -> %d unique (event, mtype, runner)" % (len(rows), len(best)))

# (event, runner) -> {mtype: odds}
P = defaultdict(dict)
for (ev, mt, run), (_ts, od) in best.items():
    P[(ev, run)][mt] = od
print("player-events with at least one field price: %d" % len(P))

DH = {5: "TOP_5_FINISH_IMG", 10: "TOP_10_FINISH_IMG", 20: "TOP_20_FINISH_IMG"}
TI = {5: "TOP_5_FINISH_(INCL._TIES)", 10: "TOP_10_FINISH_(INCL._TIES)",
      20: "TOP_20_FINISH_(INCL._TIES)"}
have = defaultdict(int)
for v in P.values():
    for mt in v:
        have[mt] += 1
print("\navailable per mtype:")
for mt, c in sorted(have.items(), key=lambda x: -x[1]):
    print("   %-34s %4d" % (mt, c))

print("\n" + "=" * 92)
print("A — DOMINANCE: incl.-ties must be SHORTER than dead heat (it wins strictly more often)")
print("=" * 92)
tot = viol = 0
sizes, worst = [], []
for k, n_ in sorted(DH.items()):
    t_ = TI[k]
    pairs = [(kk, v[n_], v[t_]) for kk, v in P.items() if n_ in v and t_ in v]
    if not pairs:
        print("   top%-3d no overlapping pairs" % k)
        continue
    bad = [(kk, a, b) for kk, a, b in pairs if b > a + 1e-9]
    tot += len(pairs)
    viol += len(bad)
    rel = [100 * (b - a) / a for _kk, a, b in bad]
    sizes += rel
    worst += [(kk[1], kk[0], a, b, 100 * (b - a) / a) for kk, a, b in bad]
    print("   top%-3d pairs %4d   violations %4d (%.1f%%)   median size %s"
          % (k, len(pairs), len(bad), 100 * len(bad) / len(pairs),
             ("%+.1f%%" % np.median(rel)) if rel else "-"))
print("\n   TOTAL %d/%d pairs violate dominance (%.1f%%)"
      % (viol, tot, 100 * viol / tot if tot else 0))
if worst:
    print("   worst offenders (dead-heat price / incl.-ties price):")
    for run, ev, a, b, r in sorted(worst, key=lambda x: -x[4])[:8]:
        print("      %-22s %-30s dh %6.2f  ties %6.2f  %+.1f%%"
              % (run[:22], str(ev)[:30], a, b, r))

print("\n" + "=" * 92)
print("B — NESTING: top5 >= top10 >= top20 in odds, within each flavour")
print("=" * 92)
for lbl, tab in (("dead heat", DH), ("incl. ties", TI)):
    n_ok = n_bad = 0
    ex = []
    for kk, v in P.items():
        for a, b in ((5, 10), (10, 20)):
            if tab[a] in v and tab[b] in v:
                if v[tab[a]] + 1e-9 < v[tab[b]]:
                    n_bad += 1
                    ex.append((kk[1], a, b, v[tab[a]], v[tab[b]]))
                else:
                    n_ok += 1
    print("   %-11s ok %4d   violations %4d" % (lbl, n_ok, n_bad))
    for run, a, b, x, y in ex[:4]:
        print("      %-24s top%d %6.2f < top%d %6.2f" % (run[:24], a, x, b, y))

print("\n" + "=" * 92)
print("C — WIN must be LONGER than top 5")
print("=" * 92)
n_ok = n_bad = 0
ex = []
for kk, v in P.items():
    for tab in (DH, TI):
        if "WIN_ONLY_IMG" in v and tab[5] in v:
            if v["WIN_ONLY_IMG"] + 1e-9 < v[tab[5]]:
                n_bad += 1
                ex.append((kk[1], v["WIN_ONLY_IMG"], v[tab[5]]))
            else:
                n_ok += 1
print("   ok %4d   violations %4d" % (n_ok, n_bad))
for run, w, t in ex[:5]:
    print("      %-24s win %7.2f < top5 %7.2f" % (run[:24], w, t))

print("\n" + "=" * 92)
print("VERDICT")
print("=" * 92)
if tot and viol:
    print("   %d dominance violations at RAW offered odds (%.1f%%). These are not devig artifacts:"
          % (viol, 100 * viol / tot))
    print("   the dead-heat bet is strictly dominated by the incl.-ties bet on the same player,")
    print("   so wherever both are offered, the incl.-ties side is the only one worth taking.")
    print("   NOTE this is a RELATIVE statement. It does not make either side +EV -- EXP-015 put")
    print("   incl.-ties holds near 30%%. It says which product to prefer, not that to bet.")
elif tot:
    print("   NO dominance violations in %d pairs. The book is internally coherent on this axis;" % tot)
    print("   there is no model-free inconsistency to exploit here.")
else:
    print("   no overlapping pairs -- the two flavours are not quoted on the same events together.")
