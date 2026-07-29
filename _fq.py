"""PERIOD-MARKET CONTAMINATION: "Qtr" was never filtered, and it silently killed real bets.

The guard rejects period markets so they cannot hijack full-game main-line detection:
    if re.search(r"\\b(quarter|half|period)\\b", low): return rows
FanDuel names the PLAYER version "Megan DiLeo - 1st Qtr Points" -- abbreviated "Qtr", which
that pattern does not match. So a 1st-quarter 2.5 line at 1.8333 landed in her FULL-GAME
points ladder.

The damage is not a stray row, it is total for the stat:
  1. _main_line picks the rung whose over price sits nearest even money. 2.5 @1.8333 is
     0.1667 from 2.0; the REAL line 12.5 @1.8197 is 0.1803. The quarter line wins by 0.014
     and becomes orig_line.
  2. _select_player_bets requires a +EV spot AT orig_line, and there is none at 2.5.
  3. `if not anchor: continue` -> the WHOLE stat is dropped.

So DiLeo's points o12.5 @1.82, +19.8% EV, stale=True -- the exact play the user bet -- was
computed correctly and then silently discarded, along with o14.5 @2.46 (+21.3%). Any player
whose quarter rung happens to price nearer 2.0 than their full-game line loses that stat
entirely, with no log line.

Fix the pattern, then purge the already-banked contaminated rows so the anchor is correct on
the very next scan instead of waiting for them to age out.
"""
import ast
import io
import re
import sqlite3
import sys

p = "fd_collect.py"
s = io.open(p, encoding="utf-8").read()
OLD = 'if re.search(r"\\b(quarter|half|period)\\b", low):'
NEW = ('# "Qtr" is FanDuel\'s abbreviation in the PLAYER markets ("Megan DiLeo - 1st Qtr\n'
       '        # Points") and was never matched by the spelled-out pattern -- 2026-07-29.\n'
       '        if re.search(r"\\b(quarter|qtr|half|period|[1-4]q|q[1-4])\\b", low):')
if OLD not in s:
    sys.exit("ANCHOR MISSING")
if s.count(OLD) != 1:
    sys.exit("ANCHOR AMBIGUOUS (%d)" % s.count(OLD))
s = s.replace(OLD, NEW.lstrip())
ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("fd_collect.py: period filter now catches 'Qtr'")

# ---- blast radius + purge ----
con = sqlite3.connect("fanduel_props.sqlite")
pat = re.compile(r"\b(quarter|qtr|half|period)\b", re.I)

# a quarter rung is identifiable as a line far below the player's full-game main line; but we
# banked no market name, so purge by the structural signature instead: two-way rungs whose
# line is <= 40% of that player's max two-way line for the same stat.
rows = con.execute(
    "SELECT player, stat, line, COUNT(*) FROM fd_lines WHERE sport='wnba' "
    "AND collected_at > datetime('now','-1 day') GROUP BY player, stat, line").fetchall()
main = {}
for pl, stat, line, _ in rows:
    main[(pl, stat)] = max(main.get((pl, stat), 0), line or 0)
suspect = [(pl, stat, line) for pl, stat, line, _ in rows
           if main.get((pl, stat), 0) >= 8 and (line or 0) <= 0.40 * main[(pl, stat)]]
print("\nsuspect quarter-rung (player,stat,line) combos in the last day: %d" % len(suspect))
for x in suspect[:12]:
    print("   %-24s %-9s line %-5g   (full-game main ~%g)" % (x[0], x[1], x[2], main[(x[0], x[1])]))

n = 0
for pl, stat, line in suspect:
    n += con.execute("DELETE FROM fd_lines WHERE sport='wnba' AND player=? AND stat=? "
                     "AND line=?", (pl, stat, line)).rowcount
con.commit()
con.close()
print("\npurged %d contaminated row(s) from fd_lines" % n)
