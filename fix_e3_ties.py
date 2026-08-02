"""Wire E3 to actually PRICE the ties-inclusive top-N products.

simulate() now produces tie-aware probabilities, but E3 still skipped these markets with
"simulator has no ties" — the capability was added and never connected.

Two things a ties-inclusive product needs, and both now come from the model rather than being
assumed:
  THE PROBABILITY  top20_ties, not top20. Measured calibration on 2026: top5_ties 1.092 and
                   win_ties 0.988 sit inside the band; top20_ties 1.221 and top10_ties 1.181 are
                   mildly timid, same direction as their strict counterparts.
  THE NORMALISER   these products pay 22-26 players, not 20, so devigging them against N=20 was
                   what inflated edge. The sim's OWN expected qualifier count (sum of the *_ties
                   probability across the field, ~22.4 for top-20) is the right target, and it
                   moves with the field rather than being hard-coded.
"""
import ast, io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

old = '''        if "TIE" in str(mt).upper():
            print(f"  skip {mt}: ties-inclusive product, simulator has no ties "
                  f"(pool implies {sum(1 / od for _, od in rr):.1f} vs nominal {N})")
            continue'''
new = '''        # TIES-INCLUSIVE PRODUCTS ARE NOW PRICEABLE. simulate() returns tie-aware probabilities
        # (integer scores), so use the *_ties key AND replace the nominal N with the model's own
        # expected qualifier count — these products pay 22-26 players, not 20, and devigging
        # against 20 is exactly what inflated the edge before.
        is_ties = "TIE" in str(mt).upper()
        if is_ties:
            tkey = {1: "win_ties", 5: "top5_ties", 10: "top10_ties", 20: "top20_ties"}[N]
            if not any(tkey in (v or {}) for v in sim.values()):
                print(f"  skip {mt}: sim has no {tkey}")
                continue
            N_eff = sum((v or {}).get(tkey, 0.0) for v in sim.values())
            if N_eff <= 0:
                continue
            print(f"  {mt}: ties-inclusive -> pricing on {tkey}, expected qualifiers "
                  f"{N_eff:.1f} (nominal {N})")
        else:
            N_eff = float(N)'''
assert old in s, "ties-skip anchor missing"
if "TIES-INCLUSIVE PRODUCTS ARE NOW PRICEABLE" in s:
    print("  = already wired")
else:
    s = s.replace(old, new, 1)
    # the guard and the devig must use N_eff, and the probability must use the ties key
    s = s.replace('''        inv = sum(1 / od for _, od in rr)
        if inv > N * 3 or inv < N * 0.4:''',
                  '''        inv = sum(1 / od for _, od in rr)
        if inv > N_eff * 3 or inv < N_eff * 0.4:''', 1)
    s = s.replace('''        key = {1: "win", 5: "top5", 10: "top10", 20: "top20"}[N]''',
                  '''        key = ({1: "win_ties", 5: "top5_ties", 10: "top10_ties", 20: "top20_ties"}[N]
               if is_ties else {1: "win", 5: "top5", 10: "top10", 20: "top20"}[N])''', 1)
    s = s.replace('''            fair = (1 / od) * N / inv''',
                  '''            fair = (1 / od) * N_eff / inv''', 1)
    # the skip message referenced N
    s = s.replace('''            print(f"  skip {mt}: pool implies {inv:.1f} qualifiers, expected ~{N} "
                      f"({len(rr)} runners)")''',
                  '''            print(f"  skip {mt}: pool implies {inv:.1f} qualifiers, expected ~{N_eff:.1f} "
                      f"({len(rr)} runners)")''', 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + E3 prices ties-inclusive top-N on *_ties with a model-derived normaliser")
