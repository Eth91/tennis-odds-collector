"""Two rows in the PropsCash centre sample look like data errors, and both push the hit rate down.

  B. Griner  CON 7/22  result 0  vs line 13.5
  D. Malonga SEA 7/28  result 0  vs line 33.5

A 33.5 POINTS line does not exist in the WNBA — that is a combo market mislabelled as points. And a
0 from Griner against a 13.5 line is far more likely a DNP than a scoreless game. If DNPs are being
scored as unders, a 25% positional hit rate is measuring availability, not defence.

Check both against the game logs.
"""
import wnba_wowy as W
ids = W.roster_ids() or {}
for who, date in (("Brittney Griner", "2026-07-22"), ("Dominique Malonga", "2026-07-28"),
                  ("Aliyah Boston", "2026-07-22")):
    pid = ids.get(who)
    if not pid:
        cand = [n for n in ids if who.split()[-1] in n]
        print("  %-22s not found exactly; near matches: %s" % (who, cand[:3]))
        pid = ids.get(cand[0]) if cand else None
        who = cand[0] if cand else who
    if not pid:
        continue
    log = W.game_log(pid)
    hit = [g for g in log if (g.get("date") or "")[:10] == date]
    if not hit:
        print("  %-22s %s: NO GAME in the log -> did not play" % (who, date))
        continue
    for g in hit:
        print("  %-22s %s: min=%-5s pts=%-4s fga=%-4s  %s"
              % (who, date, g.get("min"), g.get("pts"), g.get("fga"),
                 "DNP / zero minutes" if (g.get("min") or 0) == 0 else "played"))
