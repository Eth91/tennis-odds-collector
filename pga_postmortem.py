"""Why did the in-play R1 bets lose? Calibration first, then the mechanism.

Hypothesis worth testing before any other: a "Total Birdies or Better ROUND 1" market priced 4 hours
into the round has only the REMAINING holes left to play, but our lambda is an 18-hole rate. If the
model prices a full round against a market that knows only 6 holes remain, it will systematically
overestimate OVERS — and the book's price, which has adjusted, will look like an edge to us.
"""
import sqlite3
import pga_tee_gate as G
import datetime as dt

c = sqlite3.connect("pga_paper.sqlite"); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT market,runner,odds,p_bet,p_fair,result,pnl,snapshot_ts,lam,n_lines "
    "FROM flags WHERE result IN ('W','L') ORDER BY snapshot_ts")]
c.close()

print("  %-30s %-16s %6s %7s %7s %5s %6s %s" %
      ("player", "runner", "odds", "p_bet", "p_fair", "res", "lam", "min after tee"))
for r in rows:
    dl, _ = G.deadline("PGA Rocket Classic 2026", r["market"])
    snap = dt.datetime.fromisoformat(str(r["snapshot_ts"]).replace("Z", ""))
    mins = (snap - dl).total_seconds() / 60 if dl else None
    print("  %-30s %-16s %6s %7.3f %7.3f %5s %6s %+.0f"
          % (str(r["market"]).replace(" Total Birdies or Better Round 1", "")[:30],
             str(r["runner"])[:16], r["odds"], r["p_bet"] or 0, r["p_fair"] or 0,
             r["result"], r["lam"], mins if mins is not None else 0))

n = len(rows)
w = sum(1 for r in rows if r["result"] == "W")
pb = sum(r["p_bet"] or 0 for r in rows) / n
pf = sum(r["p_fair"] or 0 for r in rows) / n
print("\n  === calibration ===")
print("    model said     %.1f%%" % (100 * pb))
print("    market said    %.1f%%" % (100 * pf))
print("    actually hit   %.1f%%  (%d of %d)" % (100 * w / n, w, n))
print("    model overshoot vs reality : %+.1f pts" % (100 * (pb - w / n)))
print("    market overshoot vs reality: %+.1f pts" % (100 * (pf - w / n)))

print("\n  === split by side ===")
for side in ("over", "under"):
    s = [r for r in rows if side in str(r["runner"]).lower()]
    if s:
        ww = sum(1 for r in s if r["result"] == "W")
        print("    %-6s %d bets %d-%d  model said %.1f%%  hit %.1f%%  %+.2fu"
              % (side, len(s), ww, len(s) - ww,
                 100 * sum(r["p_bet"] or 0 for r in s) / len(s), 100 * ww / len(s),
                 sum(float(r["pnl"] or 0) for r in s)))

print("\n  === the mechanism check ===")
print("    lam is the model's birdie rate. If it is a FULL-ROUND rate while the market has only")
print("    the remaining holes left, overs are systematically overpriced by us.")
lams = {r["lam"] for r in rows if r["lam"] is not None}
print("    distinct lam values across bets placed 150-295 min apart: %s" % sorted(lams))
print("    -> a single course-level lam that does NOT vary with holes remaining is the tell.")
