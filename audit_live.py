#!/usr/bin/env python3
"""Full audit of the live harness. It has been patched seven times; assume something else is wrong.

Each check asserts a MAGNITUDE or an invariant, never truthiness - the rule earned across this
whole programme. Checks that can only pass vacuously are worthless.
"""
import datetime as dt
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
now = dt.datetime.utcnow().isoformat()
lg = sqlite3.connect("file:%s?mode=ro" % (HERE / "ml_ledger.sqlite"), uri=True)
fd = sqlite3.connect("file:%s?mode=ro" % (HERE / "tennis_fd.sqlite"), uri=True)
fails = []


def chk(name, ok, detail=""):
    print("   %-52s %s  %s" % (name, "PASS" if ok else "** FAIL **", detail))
    if not ok:
        fails.append(name)


print("=" * 92)
print("LIVE HARNESS AUDIT")
print("=" * 92)

bets = lg.execute("SELECT rowid,event,pick,opp,start_time,odds,p_model,edge,thin,result "
                  "FROM bets").fetchall()
n = len(bets)
print("   ledger: %d bets\n" % n)

# 1. every price must have been available PRE-MATCH
bad = 0
for _r, ev, pk, opp, stt, od, pm, eg, th, res in bets:
    m = fd.execute("""SELECT MAX(odds) FROM fd_tennis WHERE event_name=? AND runner_name=?
                      AND market_type='MATCH_BETTING' AND collected_at<=?""",
                   (ev, pk, stt)).fetchone()
    if not m or m[0] is None or od > m[0] + 1e-9:
        bad += 1
chk("every logged price existed pre-match", bad == 0, "%d violations" % bad)

# 2. one bet per match
d = [e for e, c in Counter(b[1] for b in bets).items() if c > 1]
chk("one bet per match", len(d) == 0, "%d matches with >1" % len(d))

# 3. never both sides of a match
sides = defaultdict(set)
for _r, ev, pk, opp, *_ in bets:
    sides[ev].add(pk)
both = [e for e, v in sides.items() if len(v) > 1]
chk("never both sides of the same match", len(both) == 0, "%d" % len(both))

# 4. no default-probability rows
z = sum(1 for b in bets if abs(b[6] - 0.5) < 1e-9)
chk("no 0.500 default probabilities", z == 0, "%d rows" % z)

# 5. edge must equal p*odds-1
mis = sum(1 for b in bets if abs((b[6] * b[5] - 1) - b[7]) > 1e-6)
chk("edge == p_model*odds - 1", mis == 0, "%d mismatched" % mis)

# 6. all edges within the sane band
oob = sum(1 for b in bets if b[7] < 0.03 - 1e-9 or b[7] > 0.50 + 1e-9)
chk("all edges within [3%, 50%]", oob == 0, "%d outside" % oob)

# 7. pick and opp must differ and both appear in the event name
badn = 0
for _r, ev, pk, opp, *_ in bets:
    if pk == opp or pk.split()[-1].lower() not in ev.lower() \
            or opp.split()[-1].lower() not in ev.lower():
        badn += 1
chk("pick/opp distinct and both named in the match", badn == 0, "%d bad" % badn)

# 8. odds sanity
oo = sum(1 for b in bets if not (1.01 < b[5] < 100))
chk("odds in a plausible range", oo == 0, "%d" % oo)

# 9. probabilities in (0,1)
pp = sum(1 for b in bets if not (0.0 < b[6] < 1.0))
chk("probabilities strictly inside (0,1)", pp == 0, "%d" % pp)

# 10. the portfolio should NOT be all-underdog by construction - report, do not assert
dogs = sum(1 for b in bets if b[5] > 2.0)
print("\n   composition: %d of %d picks priced above 2.00 (%.0f%% underdogs), mean odds %.2f"
      % (dogs, n, 100.0 * dogs / n, sum(b[5] for b in bets) / n))
print("   %d flagged THIN (little/no serve history)" % sum(1 for b in bets if b[8]))

print()
print("=" * 92)
print("VERDICT: %s" % ("all checks pass" if not fails else "FAILURES: %s" % ", ".join(fails)))
print("=" * 92)
