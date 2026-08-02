"""THE FIRST REAL PRICE-VS-OUTCOME BACKTEST THIS MODEL HAS EVER HAD.

Historical FanDuel/DraftKings outright CLOSES from The Odds API (18 major championships,
2021-2026, 2,351 priced runners) against actual results, with ratings fit strictly AS-OF each
event's start date.

Read the caveats before the numbers:
  MARKET   outrights only — the market our own reliability work ranks WORST for this model. The
           Odds API serves no matchups for golf (h2h returns 422), so the market ranked BEST is
           untouchable here.
  FIELDS   majors only: the sharpest, most-liquid, most-modelled golf markets on earth, with
           elite-only fields. Hardest possible test, and not representative of a Rocket Classic.
  POWER    one winner per event, so ~10 settleable events means ~10 positive outcomes. Log-loss
           uses all ~1,500 observations and has real power; ROI on flagged bets does not.
  VIG      measured overround on these closes is a MEDIAN 39.5% (range 15-55%). Matchups run
           ~4.5%. Any edge has to clear that first.

So: a fail here is meaningful, a pass here is weak evidence, and neither settles the matchup
question. Reporting it as such.
"""
import math
import os
import shutil
import sqlite3
import statistics as st
from collections import defaultdict

import pga_ruler as RU

_SNAP = os.path.expanduser("~/pga_model_oa.sqlite")
shutil.copyfile(str(RU.DB), _SNAP)
RU.DB = _SNAP

OA = "oa_golf.sqlite"
oa = sqlite3.connect(OA)
events = list(oa.execute(
    "SELECT e.sport, e.event_id, e.commence, "
    "(SELECT c.book FROM closes c WHERE c.event_id=e.event_id LIMIT 1) "
    "FROM events e ORDER BY e.commence"))

con = sqlite3.connect(RU.DB)
results = list(con.execute(
    "SELECT event_id, event, MIN(date) d, COUNT(*) FROM rounds GROUP BY event_id"))
con.close()

NAME = {"masters": "masters", "pga_championship": "pga championship",
        "us_open": "u.s. open", "the_open_championship": "open championship"}


def settle(sport, commence):
    """Match an Odds API event to our results table by tournament name + date proximity."""
    key = NAME.get(sport.replace("golf_", "").replace("_winner", "").replace("_tournament", ""))
    if not key:
        return None, None
    d0 = commence[:10]
    best = None
    for eid, evn, d, _n in results:
        if key not in str(evn or "").lower():
            continue
        try:
            gap = abs((__import__("datetime").date.fromisoformat(str(d)[:10])
                       - __import__("datetime").date.fromisoformat(d0)).days)
        except ValueError:
            continue
        if gap <= 5 and (best is None or gap < best[1]):
            best = (eid, gap)
    return (best[0], d0) if best else (None, None)


rows_all = RU.all_rows()
obs = []              # (p_model, p_book_fair, won, odds, event)
skipped = []
for sport, eid_oa, commence, book in events:
    reid, d0 = settle(sport, commence)
    if not reid:
        skipped.append((sport, commence[:10], "no result in rounds"))
        continue
    con = sqlite3.connect(RU.DB)
    tot = {RU.norm(p): (t, n) for p, t, n in con.execute(
        "SELECT player, SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND score>0 "
        "GROUP BY player", (reid,))}
    con.close()
    full = {p: t for p, (t, n) in tot.items() if n == 4}
    if len(full) < 30:
        skipped.append((sport, commence[:10], "results incomplete"))
        continue
    winner = min(full, key=full.get)
    quotes = {RU.norm(p): o for p, o in oa.execute(
        "SELECT player, odds FROM closes WHERE event_id=?", (eid_oa,))}
    R, _ = RU.fit(asof=d0, rows=rows_all)
    Rn = {RU.norm(k): v for k, v in R.items()}
    field = [p for p in quotes if p in Rn]
    if len(field) < 40:
        skipped.append((sport, commence[:10], "only %d rated runners" % len(field)))
        continue
    sim = RU.simulate(Rn, field, n_sims=20000, seed=11, reps=1)
    if not sim:
        skipped.append((sport, commence[:10], "sim empty"))
        continue
    inv = sum(1.0 / quotes[p] for p in field)
    hit = 1 if winner in field else 0
    for p in field:
        pm = (sim.get(p) or {}).get("win")
        if pm is None:
            continue
        obs.append((pm, (1.0 / quotes[p]) / inv, 1.0 if p == winner else 0.0,
                    quotes[p], commence[:10]))
    print("  %-24s %s  %3d rated runners  overround %.3f  winner %s"
          % (sport.replace("golf_", "").replace("_winner", ""), commence[:10], len(field),
             inv, winner if hit else "%s NOT PRICED" % winner))
oa.close()

print()
for s in skipped:
    print("  skipped %-24s %s  (%s)" % (s[0].replace("golf_", "").replace("_winner", ""),
                                        s[1], s[2]))
print()
n_ev = len(set(o[4] for o in obs))
print("=== BACKTEST: %d events, %d priced+rated runners, %d winners ===" %
      (n_ev, len(obs), int(sum(o[2] for o in obs))))
if len(obs) < 200:
    raise SystemExit("too few observations")

EPS = 1e-9
ll_m = [-(y * math.log(max(pm, EPS)) + (1 - y) * math.log(max(1 - pm, EPS)))
        for pm, _pb, y, _o, _e in obs]
ll_b = [-(y * math.log(max(pb, EPS)) + (1 - y) * math.log(max(1 - pb, EPS)))
        for _pm, pb, y, _o, _e in obs]
d = [a - b for a, b in zip(ll_m, ll_b)]
gap = st.mean(d) * 100
se = (st.pstdev(d) / math.sqrt(len(d))) * 100
print("  log-loss  model %.5f   book(devigged) %.5f" % (st.mean(ll_m), st.mean(ll_b)))
print("  gap %+.2f pts  (SE %.2f)  -> %s"
      % (gap, se, "model WORSE than the close" if gap > 0 else "model BETTER than the close"))
print("  z = %+.2f" % (gap / se if se else 0))
print()
print("  calibration of our win probs vs realized, by predicted quintile:")
srt = sorted(obs)
q = len(srt) // 5
for i in range(5):
    ch = srt[i * q:(i + 1) * q] if i < 4 else srt[i * q:]
    if ch:
        print("     q%d  ours %.4f  book-fair %.4f  realized %.4f  n=%d"
              % (i + 1, st.mean(c[0] for c in ch), st.mean(c[1] for c in ch),
                 st.mean(c[2] for c in ch), len(ch)))
print()
print("  BETTING at the real close (our threshold: ratio>=1.3 AND EV>=+15%, the live E3 rule):")
bets = [(pm, pb, y, od) for pm, pb, y, od, _e in obs
        if pm >= 1.3 * pb and pm * od - 1 >= 0.15]
if bets:
    pnl = sum((od - 1) if y else -1.0 for _pm, _pb, y, od in bets)
    print("     %d bets, %d winners, PnL %+.2f units, ROI %+.1f%%"
          % (len(bets), int(sum(b[2] for b in bets)), pnl, 100 * pnl / len(bets)))
    print("     mean odds %.1f, mean our-prob %.4f vs book-fair %.4f"
          % (st.mean(b[3] for b in bets), st.mean(b[0] for b in bets),
             st.mean(b[1] for b in bets)))
    print("     NOTE: %d winners is far too few for the ROI to mean anything; the log-loss"
          % int(sum(b[2] for b in bets)))
    print("     comparison above is the number with actual power.")
else:
    print("     no bets cleared the live threshold")
