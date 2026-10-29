"""A real ladder MUST be monotone: as the line rises, the over price rises. If prices are
non-monotone within a player-stat-day, the line<->odds pairing is corrupted and every calibration
number built on it is meaningless."""
import sqlite3
from collections import defaultdict
c = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_lines.sqlite?mode=ro", uri=True, timeout=90)
rows = c.execute("SELECT substr(collected_at,1,16) t, player, stat, line, odds FROM fd_lines "
                 "WHERE side='over' AND (live IS NULL OR live=0) AND odds IS NOT NULL "
                 "AND stat='points' AND collected_at > datetime('now','-2 days')").fetchall()
g = defaultdict(list)
for t, p, s, l, o in rows:
    g[(t, p, s)].append((float(l), float(o)))
bad = ok = 0
examples = []
for k, v in g.items():
    if len(v) < 3: continue
    v.sort()
    mono = all(v[i][1] <= v[i+1][1] + 1e-9 for i in range(len(v)-1))
    if mono: ok += 1
    else:
        bad += 1
        if len(examples) < 4: examples.append((k, v))
print(f"player-stat-snapshots with >=3 rungs: {ok+bad}")
print(f"  MONOTONE (valid ladder): {ok}  ({ok/max(ok+bad,1)*100:.1f}%)")
print(f"  NON-MONOTONE (broken):   {bad}  ({bad/max(ok+bad,1)*100:.1f}%)")
for k, v in examples:
    print(f"\n  {k[1]} {k[2]} @ {k[0]}:")
    print("     " + "  ".join(f"{l}@{o:.2f}" for l, o in v))
