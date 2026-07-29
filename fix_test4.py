"""Test 4 was selecting the wrong players after the progress dicts became realistic.

prog3 now holds every posted round, so a missed-cut player appears in it with two rounds.
The check must count players who actually have a THIRD round, and it should also assert the
other half of the same fact: an eliminated player's cut probability must be 0, not 1.
"""
import ast, io
p = "test_inplay.py"
s = io.open(p, encoding="utf-8").read()
old = '''cuts = [aft3[p]["cut"] for p in prog3 if p in aft3]
print("    %d players with R3 posted: min cut prob %.3f (must be 1.000)"
      % (len(cuts), min(cuts) if cuts else -1))
print("    -> %s" % ("OK" if cuts and min(cuts) > 0.999 else "FAIL"))'''
new = '''made3 = [p for p in prog3 if len(prog3[p]) >= 3 and p in aft3]
missed = [p for p in prog3 if len(prog3[p]) < 3 and p in aft3]
cuts = [aft3[p]["cut"] for p in made3]
elim = [aft3[p]["cut"] for p in missed]
print("    %d players WITH an R3: min cut prob %.3f (must be 1.000)"
      % (len(cuts), min(cuts) if cuts else -1))
print("    %d players WITHOUT an R3: max cut prob %.3f (must be 0.000)"
      % (len(elim), max(elim) if elim else -1))
ok4 = bool(cuts) and min(cuts) > 0.999 and (not elim or max(elim) < 0.001)
print("    -> %s" % ("OK" if ok4 else "FAIL"))'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("test 4 selector fixed")
