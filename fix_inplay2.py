"""In-play conditioning bug: eliminated players were still free-rolling.

Caught by the validation on the 2025 Rocket Classic. Aldrich Potgieter LED after 54 holes
(197, rank 1 of 86) and the conditional sim gave him a 1.5% win probability — lower than
his own 4.7% after 36 holes, which is impossible.

Cause: `progress` only carried players who had posted the round in question, so every
missed-cut player had NO known rounds and got all four rounds simulated. Seventy already-
eliminated players were therefore competing for the win with a full four-round free roll,
diluting each real contender's probability by roughly the ratio of phantom to real fields.

Fix: if the FIELD has completed round j and a player has no score for it, that player is
out of the event (missed cut or withdrew) and cannot win. This is inferred from the data
rather than passed in, so callers cannot forget it.
"""
import ast
import io

p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()

old = '''        tot2 = r_all[:, :, :2].sum(2)
        rest = r_all[:, :, 2:].sum(2)
        # a third round on the board is proof the cut was made
        forced = np.array([kmask[i, 2] > 0 for i in range(k)])'''
new = '''        tot2 = r_all[:, :, :2].sum(2)
        rest = r_all[:, :, 2:].sum(2)
        # a third round on the board is proof the cut was made
        forced = np.array([kmask[i, 2] > 0 for i in range(k)])
        # ELIMINATED PLAYERS CANNOT WIN. If the field has completed round j and a player has
        # no score for it, they missed the cut or withdrew. Without this they keep every
        # unplayed round as a simulated draw and free-roll a whole tournament: on the 2025
        # Rocket Classic that handed 70 eliminated players a 4-round run and pushed the
        # actual 54-hole leader down to a 1.5% win probability.
        maxj = max(means) if means else -1
        gone = np.array([any(kmask[i, j] <= 0 for j in range(maxj + 1)) for i in range(k)])'''
assert old in s
if "ELIMINATED PLAYERS CANNOT WIN" not in s:
    s = s.replace(old, new, 1)

old2 = '''    cutline = np.sort(tot2, axis=1)[:, min(69, k - 1)][:, None]
    made = tot2 <= cutline
    if forced is not None and forced.any():
        made = made | forced[None, :]
    tot4 = tot2 + np.where(made, rest, 1e6)'''
new2 = '''    cutline = np.sort(tot2, axis=1)[:, min(69, k - 1)][:, None]
    made = tot2 <= cutline
    if forced is not None and forced.any():
        made = made | forced[None, :]
    if gone is not None and gone.any():
        made = made & ~gone[None, :]
    tot4 = tot2 + np.where(made, rest, 1e6)'''
assert old2 in s
if "made & ~gone" not in s:
    s = s.replace(old2, new2, 1)

# `gone` must exist on the pre-tournament path too
old3 = '''    forced = None
    if not progress:'''
new3 = '''    forced = gone = None
    if not progress:'''
assert old3 in s
if "forced = gone = None" not in s:
    s = s.replace(old3, new3, 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_ruler.py  eliminated players excluded from in-play sims")

# the test should pass what a LIVE caller passes: every round a player has posted
p2 = "test_inplay.py"
t = io.open(p2, encoding="utf-8").read()
t = t.replace('''prog2 = {p: [d.get(1), d.get(2)] for p, d in scores.items() if d.get(1) and d.get(2)}''',
              '''# a live caller passes every posted round (this is what pga_field.round_scores gives),
# including the two rounds of players who went on to miss the cut
prog2 = {p: [d[r] for r in (1, 2) if d.get(r)] for p, d in scores.items()}
prog2 = {p: v for p, v in prog2.items() if v}''', 1)
t = t.replace('''prog3 = {p: [d.get(1), d.get(2), d.get(3)] for p, d in scores.items()
         if d.get(1) and d.get(2) and d.get(3)}''',
              '''prog3 = {p: [d[r] for r in (1, 2, 3) if d.get(r)] for p, d in scores.items()}
prog3 = {p: v for p, v in prog3.items() if v}''', 1)
ast.parse(t)
io.open(p2, "w", encoding="utf-8").write(t)
print("  + test_inplay.py  passes all posted rounds, as a live caller would")
