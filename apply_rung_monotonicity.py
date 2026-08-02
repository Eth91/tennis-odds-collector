"""Drop rungs that violate the ladder's own arithmetic. 17% of ladders currently do.

THE BUG. Every WNBA player's `points` ladder carries a bogus 2.5 and 4.5 rung:

    Carleton  o2.5 @3.85   o4.5 @11.2   o9.5 @1.27   o13.5 @1.91  o14.5 @2.20 ...
    Boston    o2.5 @3.50   o4.5 @10.8   o9.5 @1.095  o14.5 @1.53  o16.5 @1.91 ...
    Clark     o2.5 @3.20   o4.5 @9.30   o14.5 @1.151 o19.5 @1.61  o20.5 @1.77 ...

A HIGHER threshold cannot be EASIER to hit. "5+ points" paying 11.2 while "10+ points" pays 1.27
is not a soft line, it is a different market wearing the points label — almost certainly a threes
or assists milestone leaking into the points key during collection. Measured across the live
board: 45 of 269 ladders (17%) violate it.

WHY IT MATTERS MORE THAN IT LOOKS. These rungs are not merely wrong, they are wrong in the most
dangerous direction: a fat price on an easy threshold reads as an enormous edge. Anything that
ladders mechanically — which is exactly what was proposed today — would target them FIRST and
hardest, on every player, every night. A projection of 18.4 points against "o4.5 @ 11.2" computes
as roughly +1000% EV.

THE FIX IS THE INVARIANT, NOT THE ROOT CAUSE. Rather than guess which market is leaking (which
would need the collector's raw payload and would break again the next time a book adds a market),
this enforces the property every real ladder has: as the line rises, the over price must not fall.
Walk the rungs from the HIGHEST line down, tracking the cheapest price seen above; any rung
quoting MORE than something already harder to hit is discarded. That is book-agnostic and survives
whatever the upstream mislabel turns out to be.

TOLERANCE, because a strict test would over-fire. Rungs are collected at slightly different
instants inside the freshness window, so a genuine ladder can show a 1-2% inversion from timing
alone (Atkins pts_ast o12.5 @1.758 vs o13.5 @1.735). 5% keeps those and still removes the real
breakage, which is off by 5-10x rather than 2%.

Applied in posted_props, so EVERY consumer — pricing, the board's live-line filter, the ladder
section, the newly-captured `rungs` telemetry — sees the same cleaned ladder. Fixing it in one
place is the whole point: a second copy of this rule would drift, as two copies of a gate already
did in this repo.
"""
import ast
import io
import shutil

P = "wnba_tonight.py"
s = io.open(P, encoding="utf-8").read()

if "_drop_inverted" in s:
    print("  = already applied")
    raise SystemExit(0)

HELPER = '''
# A ladder's own arithmetic: a HIGHER line cannot be CHEAPER. Violations are not soft lines, they
# are foreign markets wearing this stat's label (measured 2026-08-02: 45 of 269 live WNBA ladders,
# every player carrying a bogus points 2.5/4.5 priced 5-10x too long). They are dangerous rather
# than merely wrong — a fat price on an easy threshold reads as an enormous edge, so anything that
# ladders mechanically attacks them first, on every player, every night.
RUNG_INVERSION_TOL = 0.05     # rungs are collected at slightly different instants inside the
                              # freshness window, so 1-2% inversions are timing noise, not breakage


def _drop_inverted(byline):
    """{line: [over, under]} -> the same with arithmetically impossible rungs removed.

    Walks from the HIGHEST line down keeping the cheapest over-price seen above; any rung quoting
    more than something already harder to hit is discarded. Book-agnostic on purpose: it survives
    whatever the upstream mislabel turns out to be, instead of hard-coding which market leaked.
    """
    if len(byline) < 2:
        return byline
    out, cheapest = {}, None
    for ln in sorted(byline, reverse=True):
        ov = byline[ln][0]
        if not ov:                                   # under-only rung: nothing to test
            out[ln] = byline[ln]
            continue
        if cheapest is not None and ov > cheapest * (1.0 + RUNG_INVERSION_TOL):
            continue                                 # easier line, longer price -> not this market
        out[ln] = byline[ln]
        cheapest = ov if cheapest is None else min(cheapest, ov)
    return out

'''

OLD = "def posted_props(player):"
assert OLD in s, "posted_props anchor"
s = s.replace(OLD, HELPER + "\ndef posted_props(player):", 1)

OLD2 = ("    return {s: {k: tuple(v) for k, v in d.items()} for s, d in best.items()}")
NEW2 = ("    # strip arithmetically impossible rungs before ANY consumer sees them — pricing, the\n"
        "    # board's live-line filter, the ladder section and the `rungs` telemetry all read this\n"
        "    return {st: {k: tuple(v) for k, v in _drop_inverted(\n"
        "                {k2: list(v2) for k2, v2 in d.items()}).items()}\n"
        "            for st, d in best.items()}")
assert OLD2 in s, "return anchor"
s = s.replace(OLD2, NEW2, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_tonight.premono.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + posted_props drops rungs that violate ladder monotonicity")
