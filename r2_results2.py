"""Score the R2 flags CORRECTLY: a partial round is only settled when it can no longer change.

My first pass graded 15- and 16-hole cards as final, which is simply wrong — a player with 4
birdies through 16 can still lose an under 4.5. A birdie count only moves UP, so:

    over  X.5  -> WIN  the moment birdies > X          (cannot be taken back)
                 LOSS  only at 18 holes
    under X.5  -> LOSS the moment birdies > X
                 WIN  only at 18 holes

Anything else is still live and is reported as such rather than guessed.
"""
import sqlite3
import pga_birdies as B

TID, TNAME = "R2026524", "PGA Rocket Classic 2026"
c = sqlite3.connect("pga_paper.sqlite"); c.row_factory = sqlite3.Row
flags = [dict(r) for r in c.execute(
    "SELECT market,runner,odds,p_bet,p_fair FROM flags WHERE market LIKE '%Round 2%' "
    "ORDER BY p_bet DESC")]
c.close()

got = {}
for pid, pname in B.players_of(TID):
    try:
        for row in B.scorecard_rows(TID, TNAME, pid, pname):
            if int(row[3] or 0) == 2:
                _t, _tn, pn, _r, p3h, p3b, p4h, p4b, p5h, p5b = row
                got[pn] = (p3h + p4h + p5h, p3b + p4b + p5b)
    except Exception:
        continue

print("  %-20s %-12s %7s %7s %6s  %s" % ("player", "bet", "odds", "birdies", "thru", "status"))
w = l = live = nostart = 0
u = 0.0
for f in flags:
    name = str(f["market"]).replace(" Total Birdies or Better Round 2", "").strip()
    rn = str(f["runner"]).lower()
    side = "over" if "over" in rn else "under"
    try:
        line = float(str(f["runner"]).split()[-1])
    except ValueError:
        line = None
    g = got.get(name)
    if not g or line is None:
        print("  %-20s %-12s %7s %7s %6s  not started / no card"
              % (name[:20], "%s %s" % (side, line), f["odds"], "-", "-"))
        nostart += 1
        continue
    holes, b = g
    done = holes >= 18
    if side == "over":
        res = "WIN" if b > line else ("loss" if done else None)
    else:
        res = "loss" if b > line else ("WIN" if done else None)
    if res is None:
        need = int(line - b) + 1 if side == "over" else None
        note = ("live — needs %d more in %d holes" % (need, 18 - holes)) if side == "over" \
            else "live — safe unless %d more birdies in %d holes" % (int(line - b) + 1, 18 - holes)
        print("  %-20s %-12s %7s %7d %6d  %s"
              % (name[:20], "%s %s" % (side, line), f["odds"], b, holes, note))
        live += 1
        continue
    if res == "WIN":
        w += 1
        u += float(f["odds"]) - 1
    else:
        l += 1
        u -= 1
    print("  %-20s %-12s %7s %7d %6d  %s%s"
          % (name[:20], "%s %s" % (side, line), f["odds"], b, holes, res,
             "" if done else "  (decided early — birdies only go up)"))

n = w + l
print("\n  DECIDED %d of %d:  %d-%d  (%.0f%%)  %+.2fu at 1u flat"
      % (n, len(flags), w, l, 100 * w / n if n else 0, u))
print("  %d still live, %d without a card yet" % (live, nostart))
print("\n  All of these are SHADOW (armed=False) — paper only, nothing staked.")
