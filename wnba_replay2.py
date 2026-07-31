"""Replay the real WOWY for Carleton vs DiLeo using the pids the loop itself logged.

Decisive question: DiLeo's points went to the USG shadow, which fires ONLY at n_without in (1,2).
If her +4.2 minute bump is measured on 1-2 games, shadowing it is CORRECT — the n=1/n=2 points cell
is documented as a coin flip that FAILED its own test. If n_without is healthy, shadowing it is a
real bug and the better play is being suppressed.
"""
import sqlite3

import wnba_tonight as T
import wnba_wowy as W

CARLETON, DILEO = 3906972, 3934218
OUT_NAME = "Sarah Ashlee Barker"

# resolve the out player's pid from whatever store names him/her alongside a pid
oid = None
for db, tab, pc, nc in (("wnba_proj_log.sqlite", "projections", "pid", "player"),):
    try:
        c = sqlite3.connect(db)
        r = c.execute("SELECT pid FROM %s WHERE %s LIKE ? LIMIT 1" % (tab, nc),
                      ("%Ashlee Barker%",)).fetchone()
        if r:
            oid = r[0]
        c.close()
    except sqlite3.Error:
        pass
if oid is None:                                   # fall back to the roster ESPN gives us
    for nm, pid in (W.roster_ids() or {}).items():
        if nm == OUT_NAME:
            oid = pid
            print("  resolved via roster:", nm, oid)
            break
oid = oid or 4703794          # Sarah Ashlee Barker, pinned
print("  out_player pid:", oid)
out_log = W.game_log(oid) if oid else []
print("  out_player games:", len(out_log))
if out_log:
    miss = [g for g in out_log if (g.get("min") or 0) == 0]
    print("  ...of which DNP/0-min:", len(miss))

for name, pid in (("Bridget Carleton", CARLETON), ("Megan DiLeo", DILEO)):
    bl = W.game_log(pid)
    w = W.wowy(bl, out_log)
    print("\n=== %s (pid %s) ===" % (name, pid))
    print("  games=%d   n_without=%s   n_with=%s"
          % (len(bl), w.get("n_without"), (w.get("with") or {}).get("n")))
    for k in ("min", "pts", "fga", "fta", "reb", "ast"):
        a = ((w["with"].get(k) or {}) or {}).get("mean")
        b = ((w["without"].get(k) or {}) or {}).get("mean")
        if a is not None and b is not None:
            print("    %-4s  with %6.2f   without %6.2f   delta %+.2f" % (k, a, b, b - a))
    nw = w.get("n_without") or 0
    engine = ("COLD n=0 (RotoWire-named starters only)" if nw < 1 else
              "n1 SPEED PILOT (pings, tier n1, never firm record)" if nw == 1 else
              "USG SHADOW ONLY — elevated basis needs n>=3, so the firm engine is BLIND here"
              if nw == 2 else "FIRM elevated basis")
    print("  -> engine: %s" % engine)
    props = T.posted_props(name)
    print("  posted props: %s" % (sorted((props or {}).keys()) if props else "NONE"))
    if props and props.get("points"):
        print("     points ladder: %s" % sorted(props["points"].keys()))

print("\n=== the documented verdict on the cell DiLeo landed in ===")
print("  n=1 speed pilot: +25.4% ALL from REBOUNDS; points was a coin flip")
print("  n=2 (tested 2026-07-29): FAILED, 8-8; the FGA/FTA usage split did NOT rescue points")
print("  => a POINTS over on a 1-2 game without-sample is the exact cell that already failed.")
