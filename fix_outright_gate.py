"""Gate the OUTRIGHT stream off, on real-price evidence.

First real price-vs-outcome backtest (9 major championships, 955 priced+rated runners, real
FanDuel/DraftKings CLOSES from The Odds API, as-of ratings):

  log-loss   model 0.03817 vs devigged close 0.03562  -> +0.26 pts worse, z=+1.33 (NOT significant)
  quintiles  ours vs book-fair vs realized:
               q1 .0021 / .0015 / .0000     q2 .0048 / .0027 / .0052
               q3 .0067 / .0034 / .0000     q4 .0096 / .0073 / .0000
               q5 .0240 / .0322 / .0366
             We over-rate longshots by 1.4-2x across q1-q4 and UNDER-rate favourites in q5.
             The book is right at both ends.
  betting    the LIVE rule (OUT_RATIO 1.3 and OUT_EV +15%) flagged 528 of 955 runners — 55% of
             the field — at mean odds 1058. Result: 1 winner, -85.6% ROI. The book's fair prices
             predicted 1.1 winners from those 528. It was almost exactly right; we expected 3.6.

This confirms, against real money, the longshot over-prediction the top-20 decile curve already
showed. And it exposes a LIVE misconfiguration: a threshold that fires on over half the field is
not a threshold. Combined with a measured 39.5% median overround on these markets (vs ~4.5% on
matchups), outrights are the worst possible place for this model.

Gated off the same way birdies were: measured, in code, with the reason printed.
"""
import ast, io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()
old = '''            if N == 1:
                if ours >= OUT_RATIO * fair and ours * od - 1 >= OUT_EV:'''
new = '''            if N == 1:
                # OUTRIGHT STREAM GATED OFF (2026-07-30) on real-price evidence. Backtested on 9
                # majors / 955 priced+rated runners against actual FanDuel+DraftKings CLOSES:
                # the live rule below flagged 528 of 955 runners (55% of the field!) at mean odds
                # 1058, returning 1 winner and -85.6% ROI. The book's fair prices predicted 1.1
                # winners from that set and were almost exactly right; we predicted 3.6. Our
                # longshot probabilities run 1.4-2x the book's across the bottom four quintiles
                # while realized is ~0 — the same over-prediction the top-20 decile curve showed,
                # now confirmed with money prices. Measured overround here is a median 39.5%
                # against ~4.5% on matchups, so this is the worst market for this model on both
                # calibration AND cost. Preview still prints; it just cannot arm.
                if not OUTRIGHT_ARMABLE:
                    pass
                elif ours >= OUT_RATIO * fair and ours * od - 1 >= OUT_EV:'''
if "OUTRIGHT STREAM GATED OFF" in s:
    print("  = already gated")
else:
    assert old in s, "outright anchor missing"
    s = s.replace(old, new, 1)
    # declare the flag next to the other thresholds
    import re as _re
    m = _re.search(r"^OUT_RATIO\s*=.*$", s, _re.M)
    assert m, "OUT_RATIO declaration not found"
    s = s[:m.end()] + ("\n# Gated off 2026-07-30 by the real-price backtest above: 55% of the field\n"
                       "# flagged, -85.6% ROI on 528 bets, and a 39.5% median overround.\n"
                       "OUTRIGHT_ARMABLE = False") + s[m.end():]
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_e3: outright stream gated off (OUTRIGHT_ARMABLE=False)")
