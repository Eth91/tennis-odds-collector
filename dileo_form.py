"""Recency done properly (game_log order is not guaranteed), plus a FRESH board read for 13.5."""
import wnba_tonight as T, wnba_wowy as W
NAME, PID, OUT_PID = "Megan DiLeo", 3934218, 4703794

log = sorted(W.game_log(PID, max_age_h=0), key=lambda g: g.get("date") or "")
print("  raw log order is %s" % ("OLDEST-first" if (W.game_log(PID)[0].get("date","") <
      W.game_log(PID)[-1].get("date","")) else "NEWEST-first"))
print("  %d games, %s .. %s" % (len(log), log[0]["date"][:10], log[-1]["date"][:10]))

print("\n  chronological, most recent LAST:")
for g in log[-12:]:
    print("     %s %-14s min=%-5s pts=%-4s fga=%-4s" % (g["date"][:10], (g.get("matchup") or "")[:14],
                                                        g.get("min"), g.get("pts"), g.get("fga")))

def over(games, line):
    v = [g for g in games if g.get("pts") is not None]
    o = sum(1 for g in v if g["pts"] > line)
    return o, len(v), (100 * o / len(v) if v else 0)

for line in (13.5, 14.5):
    print("\n  === over %g ===" % line)
    for lab, sub in (("last 5 (true recency)", log[-5:]), ("last 8", log[-8:]),
                     ("last 8 with 20+ min", [g for g in log if (g.get("min") or 0) >= 20][-8:]),
                     ("season, 20+ min", [g for g in log if (g.get("min") or 0) >= 20]),
                     ("all season", log)):
        o, n, p = over(sub, line)
        print("     %-24s %2d/%-2d = %5.1f%%" % (lab, o, n, p))

print("\n  === FRESH FanDuel board ===")
try:
    T._MEM = {} if hasattr(T, "_MEM") else None
except Exception:
    pass
p = T.posted_props(NAME)
print("   ", sorted((p or {}).get("points", {}).items()) if p else "no props")
