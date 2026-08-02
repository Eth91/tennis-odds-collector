"""Bug #10: we were pricing a product whose payout rule the simulator cannot represent.

Separating the pools (bug #8) made this visible. "Top 20 Finish (Incl. Ties)" implies 28.6
qualifiers not because the book is fat but because the product genuinely PAYS on more than 20
players — ties at the 20th position mean 22-26 winners. Two errors follow:

  N IS WRONG   the code assigns N=20, so fair = (1/od)*20/inv deflates every fair probability
               by roughly 20/23, inflating edge ~13%.
  THE MODEL CANNOT SEE TIES  simulate() draws continuous normals, so exact ties have
               probability zero and its top20 is strictly `rank < 20` — a ties-EXCLUSIVE
               quantity. There is no correct way to compare it to a ties-inclusive price.

Pricing ties-inclusive markets properly needs integer-score simulation (golf scores ARE
integers; the normal draws should be rounded and ranks computed with ties). Until that exists,
the honest move is to price only the EXACT products, where N is unambiguous and the simulator's
rank probability is the right quantity. Skipping a market is free; mispricing it is not.
"""
import ast, io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()
old = '''    for mt, rr in groups.items():
        N = _n_for(mt)
        if not N or len(rr) < 25 or not sim:
            continue'''
new = '''    for mt, rr in groups.items():
        N = _n_for(mt)
        if not N or len(rr) < 25 or not sim:
            continue
        # TIES-INCLUSIVE PRODUCTS ARE NOT PRICEABLE HERE (bug #10). "Top 20 Finish (Incl.
        # Ties)" pays on 22-26 players, not 20, so N is wrong AND simulate() draws continuous
        # normals — exact ties have probability zero and its top20 is strictly rank<20, a
        # ties-EXCLUSIVE quantity. Comparing that to a ties-inclusive price is a category
        # error in the direction that manufactures edge. Pricing these needs integer-score
        # simulation with tied ranks; until then, skip. Skipping a market is free.
        if "TIE" in str(mt).upper():
            print(f"  skip {mt}: ties-inclusive product, simulator has no ties "
                  f"(pool implies {sum(1 / od for _, od in rr):.1f} vs nominal {N})")
            continue'''
if "TIES-INCLUSIVE PRODUCTS ARE NOT PRICEABLE" in s:
    print("  = already skipping ties products")
else:
    assert old in s, "anchor missing"
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_e3: ties-inclusive top-N products skipped, with the reason printed")
