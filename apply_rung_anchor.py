"""`_drop_inverted` is being poisoned by the exact rungs it was written to kill. My regression.

WHAT IT DOES TODAY. It walks the ladder from the HIGHEST line down, keeps the cheapest over-price
seen so far, and discards any rung quoting longer than something already harder to hit. That encodes
a true invariant — a higher line cannot be cheaper — but it anchors on the wrong end, because on
these ladders the corruption LIVES at the top:

    Olivia Miles points, raw
        2.5   over 3.5      <- junk (a 2.5 line cannot pay 3.5)
        4.5   over 10.0     <- junk
        9.5   over 1.0333
       14.5   over 1.2778
       18.5   over 1.8475  under 1.9091   <- TWO-SIDED: the genuine FanDuel main market
       19.5   over 2.08
       24.5   over 4.4
       29.5   over 1.6452   <- junk: a 29.5 line priced SHORTER than the 18.5
       34.5   over 2.95
       39.5   over 6.0

Top-down anchors `cheapest` on 29.5 @ 1.6452 and then discards 24.5, 19.5 **and 18.5** for quoting
longer than it. The one rung we are most certain about — the only two-sided one, the real market —
is deleted by the corrupt rung. Nneka Ogwumike loses her 18.5 the same way. Measured across
tonight's board: 95 of 1,913 rungs removed, 22 of 373 ladders had their anchor or rung count
changed, and 2 ladders lost their true main line outright.

That matters beyond display: `_main_line` anchors on the rung nearest even money, so a destroyed
18.5 means the model prices a different bet, or none.

WHY BOTTOM-UP IS NOT THE FIX EITHER. The low end is corrupt too (2.5 @ 3.5, 4.5 @ 10.0). Anchoring
there would keep the junk and delete 9.5 @ 1.0333 for being "cheaper than" a lower line. Neither end
of this ladder is trustworthy, so no greedy walk from an end can work. The mislabelled rungs are not
noise on one side — they are a DIFFERENT MARKET interleaved with the real one.

THE ANCHOR IS THE TWO-SIDED RUNG. Books post both sides only on the genuine line; alt and milestone
rungs are one-sided. That is ground truth about which market we are looking at, and it does not
depend on trusting any price. Rungs are then kept only if they are consistent with it (lower lines
must not price longer, higher lines must not price shorter), and the survivors are reduced to their
LONGEST monotone chain rather than a greedy walk — so a single bad rung can no longer take a
correct one down with it.

With no two-sided rung anywhere, it falls back to the longest monotone chain alone. That is still
strictly better than the greedy version: it maximises rungs kept instead of trusting whichever end
happens to be scanned first.
"""
import ast
import io
import shutil

P = "wnba_tonight.py"
s = io.open(P, encoding="utf-8").read()

if "_longest_monotone" in s:
    print("  = already applied")
    raise SystemExit(0)

OLD = '''def _drop_inverted(byline):
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
    return out'''

NEW = '''def _longest_monotone(pairs):
    """Largest subset of (line, over) keeping over-price non-decreasing as the line rises.

    A greedy walk lets ONE bad rung veto every correct rung after it — which is exactly how the real
    main line was being destroyed. Taking the longest valid chain instead means a lone corrupt rung
    is outvoted by the rungs that agree with each other, so the failure mode is bounded.
    """
    if not pairs:
        return []
    n = len(pairs)
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if pairs[j][1] <= pairs[i][1] * (1.0 + RUNG_INVERSION_TOL) and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(n), key=lambda k: best[k])
    chain = []
    while i >= 0:
        chain.append(pairs[i][0])
        i = prev[i]
    return chain[::-1]


def _drop_inverted(byline):
    """{line: [over, under]} -> the same with arithmetically impossible rungs removed.

    A higher line cannot be cheaper than a lower one. The hard part is not the invariant, it is
    knowing WHICH rung breaks it, because these ladders arrive with a second market mislabelled into
    them and the junk sits at BOTH ends (a 2.5-point line quoted at 3.5, and a 29.5 quoted shorter
    than the 18.5). Any greedy walk from an end anchors on that junk and deletes the real rungs:
    the previous top-down version destroyed the genuine two-sided 18.5 for Ogwumike and Miles.

    THE TWO-SIDED RUNG IS THE ANCHOR. Books post both sides only on the real market; alt and
    milestone rungs are one-sided. That identifies which market we are in without trusting any
    price. Everything is then judged against it, and the survivors reduced to their longest monotone
    chain so one bad rung cannot veto the rest. No two-sided rung -> longest chain alone.
    """
    if len(byline) < 2:
        return byline
    priced = sorted((ln, byline[ln][0]) for ln in byline if byline[ln][0])
    unpriced = {ln: byline[ln] for ln in byline if not byline[ln][0]}   # under-only: nothing to test
    if not priced:
        return byline

    twosided = [ln for ln in sorted(byline) if byline[ln][0] and byline[ln][1]]
    if twosided:
        # If a book posts several two-sided rungs, the real main line is the one nearest even money.
        anchor = min(twosided, key=lambda ln: abs(byline[ln][0] - 2.0))
        aov = byline[anchor][0]
        priced = [(ln, ov) for ln, ov in priced
                  if ln == anchor
                  or (ov <= aov * (1.0 + RUNG_INVERSION_TOL) if ln < anchor
                      else ov >= aov / (1.0 + RUNG_INVERSION_TOL))]

    keep = set(_longest_monotone(priced))
    out = {ln: byline[ln] for ln in byline if ln in keep}
    out.update(unpriced)
    return out'''
assert OLD in s, "_drop_inverted anchor"
s = s.replace(OLD, NEW, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_tonight.preanchor.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + _drop_inverted anchors on the two-sided rung and keeps the longest monotone chain")
