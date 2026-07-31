"""The 9 Round 2 flags in full, plus what the model's own probabilities imply."""
import sqlite3
c = sqlite3.connect("pga_paper.sqlite"); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    "SELECT market,runner,odds,p_bet,p_fair,stream,snapshot_ts,lam,n_lines,result "
    "FROM flags WHERE market LIKE '%Round 2%' ORDER BY p_bet DESC")]
c.close()
print("  %-22s %-18s %7s %7s %7s %7s %s" % ("player", "bet", "odds", "p_bet", "p_fair", "edge", "res"))
tot_p = tot_ev = 0.0
for r in rows:
    p, f, o = r["p_bet"] or 0, r["p_fair"] or 0, float(r["odds"] or 0)
    ev = p * o - 1
    tot_p += p; tot_ev += ev
    print("  %-22s %-18s %7.4f %7.3f %7.3f %+7.3f %s"
          % (str(r["market"]).replace(" Total Birdies or Better Round 2", "")[:22],
             str(r["runner"]).split(None, 2)[-1][:18] if r["runner"] else "?",
             o, p, f, p - f, r["result"] or "pending"))
n = len(rows)
print("\n  n=%d | mean p_bet %.3f | mean p_fair %.3f | mean EV %+.1f%%"
      % (n, tot_p / n, sum((r["p_fair"] or 0) for r in rows) / n, 100 * tot_ev / n))
print("  the MODEL expects %.1f of %d to win (%.0f%%)" % (tot_p, n, 100 * tot_p / n))
print("  the MARKET implies %.1f of %d (%.0f%%)"
      % (sum(r["p_fair"] or 0 for r in rows), n, 100 * sum(r["p_fair"] or 0 for r in rows) / n))
be = sum(1 / float(r["odds"]) for r in rows) / n
print("  break-even at these prices: %.0f%%  -> need %.1f of %d just to flatten" % (100*be, be*n, n))
print("\n  sides:")
for s in ("over", "under"):
    g = [r for r in rows if s in str(r["runner"]).lower()]
    if g:
        print("    %-6s %d bets, mean p_bet %.3f, mean odds %.2f"
              % (s, len(g), sum(r["p_bet"] or 0 for r in g) / len(g),
                 sum(float(r["odds"]) for r in g) / len(g)))
