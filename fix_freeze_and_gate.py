"""Two corrections: a freeze that could not see new parameters, and a birdie stream that is
structurally miscalibrated.

(1) THE FREEZE GAVE FALSE ASSURANCE. It snapshotted a hard-coded list of constants, so when I
    added DISPERSION — a pricing parameter — the verifier reported "FREEZE INTACT" after the
    prices had changed. A freeze that cannot see a new parameter is not a freeze. It now
    enumerates every module-level constant dynamically, so an added or removed parameter shows
    up as drift.

(2) THE BIRDIE STREAM CANNOT BE FIXED BY A CONSTANT. Solving DISPERSION on the probability scale
    shows the reliability slope peaks at ~0.608 near D=0.55 and NEVER approaches 1.0 — at
    D=0.01, where every player gets the field rate, it is still 0.551. So the residual is not
    player over-dispersion: it is p_x_or_more treating 18 holes as INDEPENDENT Bernoulli trials
    when real birdie counts are correlated within a round (a hot day, or soft conditions, lifts
    every hole at once). No scalar can repair a wrong dependence structure; that needs a
    per-round random effect (beta-binomial). Until then the birdie tail probabilities are
    systematically wrong, and the tails are where every birdie edge sits.

    So the birdie stream gets its own pre-registered gate: it may not arm until its measured
    out-of-sample reliability slope reaches 0.85. Today it is 0.61. This is checked in code, not
    left to memory.
"""
import ast, io

# ------------------------------------------------------- (1) dynamic freeze capture
p = "pga_freeze.py"
s = io.open(p, encoding="utf-8").read()
old = '''    wind = C.fit_wind(verbose=False) or {}'''
new = '''    def _consts(mod):
        """Every module-level constant, discovered rather than listed.

        The first version enumerated a fixed list, so adding DISPERSION — a pricing parameter —
        left the verifier reporting "FREEZE INTACT" after prices had already moved. Anything
        upper-case and numeric (or a small numeric container) is a parameter and is captured.
        """
        out = {}
        for k in dir(mod):
            if not k.isupper() or k.startswith("_"):
                continue
            v = getattr(mod, k, None)
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                out[k] = v
            elif isinstance(v, dict) and v and len(v) <= 12 and all(
                    isinstance(x, (int, float)) or isinstance(x, dict) for x in v.values()):
                out[k] = {str(a): b for a, b in v.items()}
        return out

    wind = C.fit_wind(verbose=False) or {}'''
if "_consts(mod)" in s:
    print("  = freeze already dynamic")
else:
    assert old in s
    s = s.replace(old, new, 1)
    s = s.replace('''        "ruler": {"RHO": RU.RHO, "K_SHRINK": RU.K_SHRINK, "SIG_SHRINK": RU.SIG_SHRINK,
                  "MIN_ROUNDS": RU.MIN_ROUNDS, "HALF_LIFE_D": RU.HALF_LIFE_D},
        "context": {"K_COURSE": C.K_COURSE, "K_FIT": C.K_FIT, "WIND_REF": C.WIND_REF},
        "birdies": {"K_H": B.K_H, "K_H_PAR": B.K_H_PAR,
                    "PAR_MIX_RULE": {str(k): v for k, v in B.PAR_MIX_RULE.items()}},''',
                  '''        # discovered, not listed: a new pricing parameter must not be able to hide
        "ruler": _consts(RU),
        "context": _consts(C),
        "birdies": _consts(B),
        "wave": _consts(W),
        "e1": _consts(E1),
        "e3": _consts(E3),''', 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_freeze enumerates constants dynamically")

# --------------------------------------------- (2) birdie stream calibration gate
p2 = "pga_birdies.py"
b = io.open(p2, encoding="utf-8").read()
anchor = "def birdie_gate():"
new_g = '''# PRE-REGISTERED BIRDIE CALIBRATION GATE (2026-07-30). Measured out of sample on 19,942
# leak-free player-rounds, the reliability slope of realized on predicted P(>=4 birdies) is
# 0.61 — the model's tail probabilities are systematically too extreme. Solving DISPERSION on
# the probability scale showed the slope peaks at ~0.608 and NEVER reaches 1.0 even when every
# player is collapsed to the field rate, so this is NOT player over-dispersion: p_x_or_more
# assumes 18 INDEPENDENT holes while real birdie counts are correlated within a round. A scalar
# cannot repair a wrong dependence structure — that needs a per-round random effect
# (beta-binomial). Every birdie edge sits in exactly the tails this miscalibrates, so:
BIRDIE_RELIABILITY = 0.61        # measured; re-measure with test_reliability.py after any change
BIRDIE_RELIABILITY_MIN = 0.85    # the bar to arm this stream


def birdie_stream_armable():
    """(ok, reason) — whether the birdie stream may be bet at all, on calibration grounds.

    Deliberately independent of G2: G2 asks whether the RULER matches the book on matchups and
    says nothing about whether birdie TAIL probabilities are calibrated.
    """
    if BIRDIE_RELIABILITY < BIRDIE_RELIABILITY_MIN:
        return False, ("birdie reliability slope %.2f < %.2f — tail probabilities are too "
                       "extreme (18-hole independence assumption); needs a per-round random "
                       "effect before this stream can be bet"
                       % (BIRDIE_RELIABILITY, BIRDIE_RELIABILITY_MIN))
    return True, "birdie calibration ok"


def birdie_gate():'''
if "BIRDIE_RELIABILITY_MIN" in b:
    print("  = birdie gate already present")
else:
    assert anchor in b, "birdie_gate anchor missing"
    b = b.replace(anchor, new_g, 1)
    ast.parse(b)
    io.open(p2, "w", encoding="utf-8").write(b)
    print("  + pga_birdies: pre-registered birdie calibration gate (0.61 vs 0.85 needed)")

# e3 must respect it
p3 = "pga_e3.py"
e = io.open(p3, encoding="utf-8").read()
old_e = '''            seen_b = set()
            _nb = {"over": 0, "under": 0}'''
new_e = '''            # CALIBRATION GATE, separate from G2 (2026-07-30). G2 asks whether the ruler
            # matches the book on matchups; it says nothing about whether birdie TAIL
            # probabilities are calibrated, and they are not — measured reliability slope 0.61
            # against a 0.85 bar. Preview still prints so the numbers stay visible.
            _ok_b, _why_b = B.birdie_stream_armable()
            if not _ok_b:
                print("  birdies: NOT ARMABLE — %s" % _why_b)
            seen_b = set()
            _nb = {"over": 0, "under": 0}'''
if "CALIBRATION GATE, separate from G2" in e:
    print("  = e3 already checks the birdie gate")
else:
    assert old_e in e, "e3 birdie loop anchor missing"
    e = e.replace(old_e, new_e, 1)
    e = e.replace('''                                    "runner": f"{player} {side} {line:g}",''',
                  '''                                    "runner": f"{player} {side} {line:g}",
                                    "armable": _ok_b,''', 1)
    ast.parse(e)
    io.open(p3, "w", encoding="utf-8").write(e)
    print("  + pga_e3 marks birdie rows with armable=False and says why")
