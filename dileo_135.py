"""Price DiLeo's over 13.5 at 1.78 — the line actually on the board, not the 14.5 the ledger has."""
import wnba_tonight as T, wnba_wowy as W

NAME, PID, OUT_PID = "Megan DiLeo", 3934218, 4703794
LINE, DEC = 13.5, 1.78

props = T.posted_props(NAME)
print("  FanDuel points ladder right now: %s"
      % (sorted((props or {}).get("points", {}).items()) if props else "none"))

log = W.game_log(PID, max_age_h=0)
out = W.game_log(OUT_PID, max_age_h=0)
out_dates = {g["date"][:10] for g in out}
wo = [g for g in log if g["date"][:10] not in out_dates]

print("\n  break-even at %.2f = %.1f%%" % (DEC, 100 / DEC))

def rate(games, line, lab):
    v = [g for g in games if g.get("pts") is not None]
    if not v:
        print("  %-34s (none)" % lab); return
    o = sum(1 for g in v if g["pts"] > line)
    print("  %-34s %2d/%-2d = %5.1f%%   pts: %s"
          % (lab, o, len(v), 100 * o / len(v), sorted((int(g["pts"]) for g in v), reverse=True)[:12]))

rate(log, LINE, "ALL games over %g" % LINE)
rate([g for g in log if (g.get("min") or 0) >= 20], LINE, "games with 20+ min")
rate(wo, LINE, "WITHOUT Barker (the relevant set)")
rate(log[-8:], LINE, "last 8 games")

print("\n  the two without-Barker games in full:")
for g in wo:
    print("     %s %-14s min=%-5s pts=%-4s fga=%s" % (g["date"][:10], (g.get("matchup") or "")[:14],
                                                      g.get("min"), g.get("pts"), g.get("fga")))

# what does the model itself make of 13.5?
w = W.wowy(log, out)
edges = []
try:
    edges = list(T.prop_edges(NAME, log, 27.0, w=w, vacated=None, ctx=None,
                              out_logs=[{g["date"][:10]: g["min"] for g in out}], opp="IND", pos="C"))
except Exception as e:
    print("\n  prop_edges failed: %r" % e)
print("\n  model edges on the live board:")
for e in sorted(edges, key=lambda x: -(x.get("ev") or 0)):
    if e.get("stat") != "points":
        continue
    print("     o%-6g dec=%-7s hit=%-6s ev=%+.3f  elev_avg=%s"
          % (e["line"], e["dec"], round(e.get("hit") or 0, 3), e.get("ev") or 0, e.get("elev_avg")))
