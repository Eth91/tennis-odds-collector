"""How are the 11 R2 flags doing? Score them live off the scorecards, not off the grader."""
import sqlite3
import pga_birdies as B

TID, TNAME = "R2026524", "PGA Rocket Classic 2026"

c = sqlite3.connect("pga_paper.sqlite"); c.row_factory = sqlite3.Row
flags = [dict(r) for r in c.execute(
    "SELECT market,runner,odds,p_bet,p_fair,result,pnl FROM flags "
    "WHERE market LIKE '%Round 2%' ORDER BY p_bet DESC")]
c.close()

# birdies-or-better per player for R2, straight from the scorecards
got = {}
for pid, pname in B.players_of(TID):
    try:
        for row in B.scorecard_rows(TID, TNAME, pid, pname):
            if int(row[3] or 0) == 2:
                _t, _tn, pn, _r, p3h, p3b, p4h, p4b, p5h, p5b = row
                got[pn] = (p3h + p4h + p5h, p3b + p4b + p5b)
    except Exception:
        continue
print("  players with a COMPLETED R2: %d" % len(got))

print("\n  %-20s %-12s %7s %8s %6s %s" % ("player", "bet", "odds", "birdies", "holes", "result"))
w = l = pend = 0
u = 0.0
for f in flags:
    name = str(f["market"]).replace(" Total Birdies or Better Round 2", "").strip()
    side = "over" if "over" in str(f["runner"]).lower() else "under"
    try:
        line = float(str(f["runner"]).split()[-1])
    except ValueError:
        line = None
    g = got.get(name)
    if not g or line is None:
        print("  %-20s %-12s %7s %8s %6s %s"
              % (name[:20], "%s %s" % (side, line), f["odds"], "-", "-", "still on the course"))
        pend += 1
        continue
    holes, b = g
    hit = (b > line) if side == "over" else (b < line)
    w, l = (w + 1, l) if hit else (w, l + 1)
    u += (float(f["odds"]) - 1) if hit else -1.0
    print("  %-20s %-12s %7s %8d %6d %s"
          % (name[:20], "%s %s" % (side, line), f["odds"], b, holes, "WIN " if hit else "loss"))
n = w + l
print("\n  settled %d of %d:  %d-%d  (%.0f%%)  %+.2fu at 1u flat" % (n, len(flags), w, l,
      100 * w / n if n else 0, u))
if pend:
    print("  %d still playing" % pend)
