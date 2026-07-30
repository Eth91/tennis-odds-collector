"""Birdie one-sidedness: the level anchor was calibrated against the VIG, not against fair.

MEASURED: all 24 posted birdie lines carry both sides, and the overround is 6.04% (very tight:
1.0567-1.0618). So the raw Over implied probability sits +3.02 points ABOVE fair.

LAM was bisected so that mean(model P(over)) == mean(1/odds_over) — i.e. anchored to the
vig-inflated Over price. Consequences, all forced:

    over edge  = p_over - raw_over            ~= 0        (should be -3.02: you must beat vig)
    under edge = (1 - p_over) - raw_under     ~= -6.04

Unders therefore start six points in the hole while overs start level, which is exactly the
10-overs / 1-under split the audit flagged. And it is not merely cosmetic: every flagged over
was over-valued by ~3 points, so a "+5% over" was really a +2% over.

FIX: pair each player's Over and Under quote for the same line, devig to a fair probability,
and anchor the model level to the mean FAIR probability. The EDGE stays measured against the
raw offered price — that part was always right, because you bet at the offered price and the
vig is exactly what has to be overcome. After this both sides start from the same -3.02 point
handicap, so any asymmetry that remains is real signal rather than an artefact.

Expect far fewer flags. At a 6% hold, clearing +5% NET requires the model to disagree with fair
by more than 8 points. That is the honest bar, and flags disappearing is the correct outcome
rather than a regression.
"""
import ast
import io

# ============================================================== pga_e3: the anchor
p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

old = '''            overs = [x for x in parsed if x[1] == "over"]
            LAM = 1.0
            if len(overs) >= 8:
                # bisect LAM so mean model P(over) == mean market implied P(over)
                tgt = sum(1 / x[3] for x in overs) / len(overs)'''
new = '''            overs = [x for x in parsed if x[1] == "over"]
            # DEVIG BEFORE ANCHORING (2026-07-30). The anchor used to target
            # mean(1/odds_over), i.e. the Over price WITH the vig in it. Measured overround on
            # these lines is 6.04%, so that target sat +3.02 points above fair — which forced
            # over-edges to average 0 (they should average -3.02) and under-edges to average
            # -6.04. Unders could then never clear a +5% threshold: the 10-over / 1-under
            # split the audit caught. Worse, every flagged over was over-valued by ~3 points.
            # Pair each player's two quotes and anchor to the FAIR probability instead.
            _q = {}
            for _pl, _sd, _ln, _od, _mk, _rr in parsed:
                _q.setdefault((RU.norm(_pl), _ln), {})[_sd] = _od
            fair_over = {}
            for _k, _v in _q.items():
                if "over" in _v and "under" in _v:
                    _io, _iu = 1.0 / _v["over"], 1.0 / _v["under"]
                    if _io + _iu > 0:
                        fair_over[_k] = _io / (_io + _iu)
            _pairs = [x for x in overs if (RU.norm(x[0]), x[2]) in fair_over]
            if _pairs:
                _rawm = sum(1 / x[3] for x in _pairs) / len(_pairs)
                _fairm = sum(fair_over[(RU.norm(x[0]), x[2])] for x in _pairs) / len(_pairs)
                print("  birdies: devig on %d/%d two-sided lines — raw Over %.4f vs FAIR "
                      "%.4f (vig %.2f pts)"
                      % (len(_pairs), len(overs), _rawm, _fairm, 100 * (_rawm - _fairm)))
            LAM = 1.0
            if len(_pairs) >= 8:
                # bisect LAM so mean model P(over) == mean FAIR P(over)
                overs = _pairs
                tgt = sum(fair_over[(RU.norm(x[0]), x[2])] for x in overs) / len(overs)'''
if "DEVIG BEFORE ANCHORING" in s:
    print("  = pga_e3 already devigs the anchor")
else:
    assert old in s, "e3 anchor anchor missing"
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_e3: LAM anchored to the devigged fair probability")

# report the two-sidedness of what we actually flag
s = io.open(p, encoding="utf-8").read()
old2 = '''            seen_b = set()
            for player, side, line, od, mkt, rr in parsed:'''
new2 = '''            seen_b = set()
            _nb = {"over": 0, "under": 0}
            for player, side, line, od, mkt, rr in parsed:'''
if '_nb = {"over": 0, "under": 0}' not in s:
    assert old2 in s
    s = s.replace(old2, new2, 1)
old3 = '''                if edge >= 0.05 and key not in seen_b:
                    seen_b.add(key)
                    preview.append({"stream": "E3-birdies",'''
new3 = '''                if edge >= 0.05 and key not in seen_b:
                    seen_b.add(key)
                    _nb[side] = _nb.get(side, 0) + 1
                    preview.append({"stream": "E3-birdies",'''
if "_nb[side] = _nb.get(side, 0) + 1" not in s:
    assert old3 in s
    s = s.replace(old3, new3, 1)
old4 = '''    except Exception as _be:
        print(f"  birdie pricing skipped: {str(_be)[:70]}")'''
new4 = '''            # ONE-SIDEDNESS IS A LEVEL ALARM. With a devigged anchor both sides start
            # from the same handicap, so a persistent all-one-way split means the LEVEL is
            # wrong again — which is exactly how the v1 par-72 bug first showed itself.
            print("  birdies: flags %d over / %d under%s"
                  % (_nb.get("over", 0), _nb.get("under", 0),
                     "  <-- ONE-SIDED, recheck the level" if
                     (_nb.get("over", 0) + _nb.get("under", 0)) >= 6 and
                     min(_nb.get("over", 0), _nb.get("under", 0)) == 0 else ""))
    except Exception as _be:
        print(f"  birdie pricing skipped: {str(_be)[:70]}")'''
if "ONE-SIDEDNESS IS A LEVEL ALARM" not in s:
    assert old4 in s
    s = s.replace(old4, new4, 1)
ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_e3: flag split reported with a one-sidedness alarm")

# ============================================== pga_audit: measure bias against FAIR
p2 = "pga_audit.py"
a = io.open(p2, encoding="utf-8").read()
old_b = '''def bias(parsed, mx, lam=1.0):
    ov = [x for x in parsed if x[1] == "over"]
    if not ov:
        return None, None, 0
    m = st.mean(B.p_x_or_more({a: min(b * lam, .95) for a, b in rr.items()},
                              int(ln + .5), mx) for _p, _s, ln, _o, rr in ov)
    k = st.mean(1 / x[3] for x in ov)
    return m, k, len(ov)'''
new_b = '''def _fair_map(parsed):
    """(player, line) -> devigged fair P(over), from the two paired quotes.

    The audit used to compare the model to mean(1/odds_over), i.e. the Over price WITH the vig
    in it. On these lines the overround is 6.04%, so that reference sat +3.02 points above
    fair and every "bias" number this section has ever printed was low by about that much.
    """
    q = {}
    for pl, sd, ln, od, _rr in parsed:
        q.setdefault((RU.norm(pl), ln), {})[sd] = od
    out = {}
    for k, v in q.items():
        if "over" in v and "under" in v:
            io_, iu = 1.0 / v["over"], 1.0 / v["under"]
            if io_ + iu > 0:
                out[k] = io_ / (io_ + iu)
    return out


def bias(parsed, mx, lam=1.0, fair=None):
    """Model vs market on the Over side. Compares to FAIR when the paired quote exists."""
    ov = [x for x in parsed if x[1] == "over"]
    if fair is not None:
        ov = [x for x in ov if (RU.norm(x[0]), x[2]) in fair]
    if not ov:
        return None, None, 0
    m = st.mean(B.p_x_or_more({a: min(b * lam, .95) for a, b in rr.items()},
                              int(ln + .5), mx) for _p, _s, ln, _o, rr in ov)
    if fair is not None:
        k = st.mean(fair[(RU.norm(x[0]), x[2])] for x in ov)
    else:
        k = st.mean(1 / x[3] for x in ov)
    return m, k, len(ov)'''
if "_fair_map" in a:
    print("  = pga_audit already devigs")
else:
    assert old_b in a, "audit bias anchor missing"
    a = a.replace(old_b, new_b, 1)
    # thread `fair` through the three call sites
    a = a.replace('''p_naive = parse({})
m1, k1, n1 = bias(p_naive, B.DEFAULT_MIX)''',
                  '''p_naive = parse({})
FAIR = _fair_map(p_naive)
m1, k1, n1 = bias(p_naive, B.DEFAULT_MIX, fair=FAIR)''', 1)
    a = a.replace('''p_ctx = parse({"course_factor": cf, "wind_kmh": wind})
m2, k2, n2 = bias(p_ctx, mix)''',
                  '''p_ctx = parse({"course_factor": cf, "wind_kmh": wind})
m2, k2, n2 = bias(p_ctx, mix, fair=FAIR)''', 1)
    a = a.replace('''    mm, _, _ = bias(p_ctx, mix, L)''',
                  '''    mm, _, _ = bias(p_ctx, mix, L, fair=FAIR)''', 1)
    a = a.replace('''print("    market anchor now only corrects %.1f%% (was 12%% when blind)" % abs(100 * (L - 1)))''',
                  '''print("    market anchor now only corrects %.1f%% (was 12%% when blind)" % abs(100 * (L - 1)))
print("    reference is the DEVIGGED fair price on %d two-sided lines; the raw Over price "
      "sits %.2f pts above it, and comparing to raw understated every earlier bias figure "
      "by that much" % (len(FAIR), 100 * (st.mean(1 / x[3] for x in p_ctx if x[1] == "over"
                                                  and (RU.norm(x[0]), x[2]) in FAIR)
                                          - st.mean(FAIR[(RU.norm(x[0]), x[2])]
                                                    for x in p_ctx if x[1] == "over"
                                                    and (RU.norm(x[0]), x[2]) in FAIR))))''', 1)
    ast.parse(a)
    io.open(p2, "w", encoding="utf-8").write(a)
    print("  + pga_audit: bias now measured against the devigged fair price")
