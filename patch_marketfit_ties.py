"""Add the ties-inclusive markets to the per-market calibration run.

They were previously unmeasurable: the sim had no ties, so there was nothing to compare a
ties-inclusive price against. Now that scores are integers, both variants exist and the realized
side must be defined to match each one — STRICT rank for the exact products, and
1+(count strictly better) for the "(Incl. Ties)" products.
"""
import ast, io
p = "market_fit.py"
s = io.open(p).read()
old = '''    order = sorted(full.items(), key=lambda kv: (kv[1], kv[0]))
    pos = {p: i + 1 for i, (p, t) in enumerate(order)}'''
new = '''    order = sorted(full.items(), key=lambda kv: (kv[1], kv[0]))
    pos = {p: i + 1 for i, (p, t) in enumerate(order)}          # strict, ties broken arbitrarily
    # ties-inclusive realized position: 1 + how many are STRICTLY better, so a tie shares the
    # better rank — the definition the "(Incl. Ties)" products settle on
    tpos = {p: 1 + sum(1 for _q, tq in full.items() if tq < t) for p, t in full.items()}'''
assert old in s
if "tpos" not in s:
    s = s.replace(old, new, 1)
    old_b = '''        buckets["outright"].append((v["win"], 1.0 if pp == 1 else 0.0))'''
    new_b = '''        buckets["outright"].append((v["win"], 1.0 if pp == 1 else 0.0))
        tp = tpos.get(p, 10 ** 6)
        if "top20_ties" in v:
            buckets["top20_ties"].append((v["top20_ties"], 1.0 if tp <= 20 else 0.0))
            buckets["top10_ties"].append((v["top10_ties"], 1.0 if tp <= 10 else 0.0))
            buckets["top5_ties"].append((v["top5_ties"], 1.0 if tp <= 5 else 0.0))
            buckets["win_ties"].append((v["win_ties"], 1.0 if tp == 1 else 0.0))'''
    assert old_b in s
    s = s.replace(old_b, new_b, 1)
    s = s.replace('''ORDER = ["matchup_72h", "matchup_r1", "make_cut", "top20", "top10", "top5", "outright"]''',
                  '''ORDER = ["matchup_72h", "matchup_r1", "make_cut", "top20", "top10", "top5", "outright",
         "top20_ties", "top10_ties", "top5_ties", "win_ties"]''')
    ast.parse(s)
    io.open(p, "w").write(s)
    print("  + market_fit now measures the ties-inclusive markets too")
else:
    print("  = already patched")
