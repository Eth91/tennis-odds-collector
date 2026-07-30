"""Adversarial sweep fixes, plus what the gate power analysis actually showed.

S1  tid_for_name accepted a SINGLE token hit with no minimum match quality, so an event whose
    name is not in the schedule would silently resolve to any tournament sharing one word —
    and that tid drives the par mix, the course factor AND the wave tee sheet. Currently
    correct for the Rocket Classic, but unguarded, and it is the same contamination class as
    the course-name and LPGA bugs. Now requires a majority of tokens and refuses rather than
    guessing.

S2  The E1 tripwire's CODE fires below `0.52*be*2` = 1.04*be while its DOCSTRING says "52% of
    the breakeven pace" = 0.52*be. Those differ by 4x, so no one reading the documented rule
    could know the real threshold.

S3  Worse, and this is the real defect: the threshold sits ABOVE breakeven, so the tripwire is
    not testing "is this broken" but "is this comfortably profitable". Measured false-bench
    rate on a stream that is EXACTLY break-even: 58% at n=25, rising to 85% at n=600 — it
    converges on benching a break-even stream with certainty. A safety mechanism that fires on
    noise more often than not is worse than none, because its alarm reads as evidence.
    Replaced with a proper one-sided test: bench only when the observed rate is more than 2
    standard errors below breakeven, which holds the false-bench rate near 2% at every n.

G2  The power analysis VINDICATED the pre-registered n=15 and corrected me. Against real
    out-of-sample matchup probabilities, G2 fails a book 4+ points sharper 100% of the time at
    n=15, and passes a book within 1 point 100% of the time. I had claimed 15 was "a smoke
    test"; the numbers say otherwise, so the threshold stays.

    What the analysis DID expose is a gap the gate cannot close: passing G2 means "within 2
    points of the book", which is equally consistent with being 1.9 points WORSE — and 1.9
    points worse, before a 4.5% vig, is a guaranteed loser. G2 is a screen against a broken
    model, NOT evidence of an edge. That distinction is now written into the gate's output so
    a PASS can never be read as permission to bet.
"""
import ast
import io

# ------------------------------------------------------------------ S1 tid_for_name
p = "pga_birdies.py"
s = io.open(p, encoding="utf-8").read()
old = '''    toks = [w for w in key.replace("pga", "").split() if len(w) > 3 and not w.isdigit()]
    best = None
    for tid, tn in cands:
        hits = sum(1 for w in toks if w in tn)
        if hits and (best is None or hits > best[0]):
            best = (hits, tid)
    tid = best[1] if best else None'''
new = '''    toks = [w for w in key.replace("pga", "").split() if len(w) > 3 and not w.isdigit()]
    # REQUIRE A MAJORITY OF TOKENS (2026-07-30). A single hit used to be enough, so an event
    # missing from the schedule would silently resolve to any tournament sharing one word —
    # and this tid drives the par mix, the course factor AND the wave tee sheet. Same
    # contamination class as the course-name and LPGA bugs. Refusing beats guessing: every
    # caller already handles a None tid by falling back to a documented default.
    need = max(1, (len(toks) + 1) // 2) if toks else 0
    best = None
    for tid, tn in cands:
        hits = sum(1 for w in toks if w in tn)
        if hits >= need and (best is None or hits > best[0]):
            best = (hits, tid)
    tid = best[1] if best else None'''
if "REQUIRE A MAJORITY OF TOKENS" in s:
    print("  = tid_for_name already guarded")
else:
    assert old in s, "tid_for_name anchor missing"
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + tid_for_name requires a majority token match, refuses rather than guessing")

# --------------------------------------------------------------- S2/S3 E1 tripwire
p2 = "pga_grade.py"
g = io.open(p2, encoding="utf-8").read()
old_t = '''    n = w + l
    if n >= 25:
        be = 1 / avg_odds
        if (w / n) < 0.52 * be * 2:                       # <52% of breakeven pace
            print(f"🚨 E1 TRIPWIRE: {w}-{l} ({100*w/n:.0f}%) vs breakeven {100*be:.0f}% "
                  f"after {n} graded — BENCH this stream (PGA_PLAN law 7)")'''
new_t = '''    n = w + l
    if n >= 25:
        be = 1 / avg_odds
        # PROPER ONE-SIDED TEST (2026-07-30). The old rule fired below 0.52*be*2 = 1.04*be —
        # a threshold ABOVE breakeven, so it was not testing "is this broken" but "is this
        # comfortably profitable", and it benched a stream that was EXACTLY break-even 58% of
        # the time at n=25 rising to 85% at n=600. It also contradicted its own docstring
        # ("52% of the breakeven pace" = 0.52*be), a 4x discrepancy. Now: bench only when the
        # observed rate is more than 2 standard errors BELOW breakeven, i.e. break-even can
        # be statistically ruled out. That holds the false-bench rate near 2% at every n.
        se = (be * (1 - be) / n) ** 0.5
        z = (w / n - be) / se if se > 0 else 0.0
        if z <= -2.0:
            print(f"🚨 E1 TRIPWIRE: {w}-{l} ({100*w/n:.0f}%) vs breakeven {100*be:.0f}% "
                  f"after {n} graded, z={z:+.2f} — break-even RULED OUT, BENCH this stream "
                  f"(PGA_PLAN law 7)")
        elif w / n < be:
            print(f"   E1 below breakeven ({100*w/n:.0f}% vs {100*be:.0f}%, z={z:+.2f}) but "
                  f"not yet distinguishable from noise at n={n} — keep collecting")'''
if "PROPER ONE-SIDED TEST" in g:
    print("  = tripwire already a real test")
else:
    assert old_t in g, "tripwire anchor missing"
    g = g.replace(old_t, new_t, 1)
    # the docstring described the wrong rule
    g = g.replace('''TRIPWIRE (PGA_PLAN law 7, defined BEFORE launch): after 25 graded, if the win rate is
below 52% of the implied-breakeven pace, print the BENCH alarm loudly. No auto-ntfy —
the nightly digest and the board carry it; this stream never had ping rights to lose.''',
                  '''TRIPWIRE (PGA_PLAN law 7, defined BEFORE launch): after 25 graded, bench the stream when
break-even can be STATISTICALLY RULED OUT — the observed win rate more than 2 standard
errors below the implied breakeven. (v1 said "below 52% of the breakeven pace" but the code
fired at 1.04x breakeven, a 4x discrepancy, and that threshold sits ABOVE breakeven so it
benched an exactly-break-even stream 58% of the time at n=25 and 85% at n=600.) No
auto-ntfy — the nightly digest and the board carry it; this stream never had ping rights.''', 1)
    ast.parse(g)
    io.open(p2, "w", encoding="utf-8").write(g)
    print("  + E1 tripwire is now a real one-sided test with a controlled false-bench rate")

# ------------------------------------------------- G2: a PASS is not permission to bet
p3 = "pga_ruler.py"
r = io.open(p3, encoding="utf-8").read()
old_g = '''            verdict = "PASS" if gap <= 2.0 else "FAIL"
            print(f"G2 on {n_used} real FD closes: book logloss {lb:.4f}, ruler {lr:.4f} "
                  f"(gap {gap:+.1f}pts) -> {verdict}")'''
new_g = '''            verdict = "PASS" if gap <= 2.0 else "FAIL"
            print(f"G2 on {n_used} real FD closes: book logloss {lb:.4f}, ruler {lr:.4f} "
                  f"(gap {gap:+.1f}pts) -> {verdict}")
            # POWER-CHECKED 2026-07-30 against real out-of-sample matchup probabilities:
            # this gate fails a book 4+ pts sharper 100% of the time even at n=15, and passes
            # a book within 1 pt 100% of the time. n=15 is adequate; it was NOT a smoke test.
            # But a PASS means "within 2 pts of the book", which is equally consistent with
            # being 1.9 pts WORSE — and 1.9 pts worse, before a ~4.5% vig, loses money. G2 is
            # a SCREEN AGAINST A BROKEN MODEL, never evidence of an edge.
            print("     NOTE: PASS = 'not materially worse than the book'. It is NOT evidence "
                  "of an edge and is NOT permission to bet — that needs realized ROI/CLV on "
                  "settled flagged bets, which is a separate gate and a much larger n.")'''
if "SCREEN AGAINST A BROKEN MODEL" in r:
    print("  = g2 already states the caveat")
else:
    assert old_g in r, "g2 verdict anchor missing"
    r = r.replace(old_g, new_g, 1)
    ast.parse(r)
    io.open(p3, "w", encoding="utf-8").write(r)
    print("  + G2 states plainly that a PASS is not permission to bet")
