"""Validate the in-play conditioning (blind spot #4) on a COMPLETED event.

A conditional simulator is easy to get subtly wrong, so this asserts things that can only
hold if the conditioning is real:
  1. probabilities still sum to 1/5/10/20 across the field (calibration must survive)
  2. the eventual winner's win probability must RISE once their first two rounds are known
  3. a player already 10+ strokes back after 36 holes must have their win prob collapse
  4. anyone with a 3rd round posted must show cut prob 1.0 (it is a fact, not a forecast)
  5. a partially played round must land between "not started" and "finished"
"""
import sqlite3
import pga_ruler as RU

EVENT_LIKE = "%rocket classic%"

con = sqlite3.connect(RU.DB)
row = con.execute("SELECT event_id, event, MIN(date) FROM rounds WHERE LOWER(event) LIKE ? "
                  "GROUP BY event_id ORDER BY MIN(date) DESC LIMIT 1", (EVENT_LIKE,)).fetchone()
eid, evn, edate = row
scores = {}
for pl, rnd, sc in con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=? "
                               "AND score > 0 ORDER BY rnd", (eid,)):
    scores.setdefault(pl, {})[rnd] = sc
con.close()
print("event: %s (%s)  %d players with rounds" % (evn, edate, len(scores)))

field = list(scores)
R, _gsd = RU.fit(asof=edate)          # as-of, so no result leaks into the ratings

# the actual winner = lowest 72-hole total among those who played 4
fin = {p: sum(d[r] for r in (1, 2, 3, 4)) for p, d in scores.items() if len(d) >= 4}
winner = min(fin, key=fin.get)
print("actual winner: %s (%d)" % (winner, fin[winner]))

pre = RU.simulate(R, field, n_sims=6000, seed=3)
# a live caller passes every posted round (this is what pga_field.round_scores gives),
# including the two rounds of players who went on to miss the cut
prog2 = {p: [d[r] for r in (1, 2) if d.get(r)] for p, d in scores.items()}
prog2 = {p: v for p, v in prog2.items() if v}
mid = RU.simulate(R, field, n_sims=6000, seed=3, progress=prog2)
prog3 = {p: [d[r] for r in (1, 2, 3) if d.get(r)] for p, d in scores.items()}
prog3 = {p: v for p, v in prog3.items() if v}
aft3 = RU.simulate(R, field, n_sims=6000, seed=3, progress=prog3)

print("\n[1] CALIBRATION SURVIVES CONDITIONING")
ok = True
for label, sim in (("pre-tournament", pre), ("after 36 holes", mid), ("after 54", aft3)):
    if not sim:
        print("    %-16s EMPTY" % label)
        ok = False
        continue
    line = "    %-16s" % label
    for k, tgt in (("win", 1), ("top5", 5), ("top10", 10), ("top20", 20)):
        tot = sum(v[k] for v in sim.values())
        good = abs(tot - tgt) < 0.5
        ok &= good
        line += "  %s=%.2f%s" % (k, tot, "" if good else "!!")
    print(line)
print("    -> %s" % ("OK" if ok else "FAIL"))

print("\n[2] WINNER'S WIN PROBABILITY MUST RISE AS THEIR SCORES LAND")
w = winner
seq = [(l, s.get(w, {}).get("win")) for l, s in
       (("pre", pre), ("after 36", mid), ("after 54", aft3))]
print("    %s: %s" % (w, "  ->  ".join("%s %.1f%%" % (l, 100 * (v or 0)) for l, v in seq)))
rising = all(seq[i][1] is not None and seq[i + 1][1] is not None
             and seq[i + 1][1] >= seq[i][1] for i in range(len(seq) - 1))
print("    -> %s" % ("OK (monotone)" if rising else "CHECK — not monotone"))

print("\n[3] A PLAYER FAR BACK AT 36 HOLES MUST COLLAPSE")
t36 = {p: v[0] + v[1] for p, v in prog2.items()}
lead = min(t36.values())
back = sorted([p for p in t36 if t36[p] - lead >= 10], key=lambda p: -t36[p])[:1]
for p in back:
    a, b = pre.get(p, {}).get("win"), mid.get(p, {}).get("win")
    if a is None or b is None:
        print("    %s not rated" % p)
        continue
    print("    %-24s %+d strokes back: win %.2f%% -> %.3f%%  %s"
          % (p, t36[p] - lead, 100 * a, 100 * b, "OK" if b < a else "FAIL"))

print("\n[4] A POSTED THIRD ROUND IS A FACT, NOT A FORECAST")
made3 = [p for p in prog3 if len(prog3[p]) >= 3 and p in aft3]
missed = [p for p in prog3 if len(prog3[p]) < 3 and p in aft3]
cuts = [aft3[p]["cut"] for p in made3]
elim = [aft3[p]["cut"] for p in missed]
print("    %d players WITH an R3: min cut prob %.3f (must be 1.000)"
      % (len(cuts), min(cuts) if cuts else -1))
print("    %d players WITHOUT an R3: max cut prob %.3f (must be 0.000)"
      % (len(elim), max(elim) if elim else -1))
ok4 = bool(cuts) and min(cuts) > 0.999 and (not elim or max(elim) < 0.001)
print("    -> %s" % ("OK" if ok4 else "FAIL"))

print("\n[5] A PARTIAL ROUND LANDS BETWEEN NOT-STARTED AND FINISHED")
# give the winner a hot 9 holes of round 3 (relative to field pace) and check ordering
lead_p = winner
r3rel = None
r3 = {p: d[3] for p, d in scores.items() if d.get(3)}
if r3:
    m3 = sum(r3.values()) / len(r3)
    r3rel = (r3.get(lead_p, m3) - m3) / 2.0        # half the round's edge, 9 holes in
mid_part = RU.simulate(R, field, n_sims=6000, seed=3, progress=prog2,
                       partial={lead_p: (9, r3rel)}) if r3rel is not None else {}
a = mid.get(lead_p, {}).get("win")
b = mid_part.get(lead_p, {}).get("win")
c = aft3.get(lead_p, {}).get("win")
print("    %s win%%: 36 holes %.1f%% | +9 holes of R3 %.1f%% | R3 complete %.1f%%"
      % (lead_p, 100 * (a or 0), 100 * (b or 0), 100 * (c or 0)))
print("    -> %s" % ("OK (ordered)" if None not in (a, b, c) and a <= b <= c
                     else "CHECK — ordering not monotone (fine if R3 was a bad round)"))
