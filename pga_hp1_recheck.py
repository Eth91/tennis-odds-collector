"""Is H-P1 real, or is it "this WEEK is easy" rather than "this PLAYER is hot"?

The learning engine's null shuffles the feature WITHIN an event, breaking player identity while
preserving everything about the event. It came back at +0.145 against a true +0.152 — i.e. almost
the whole correlation survives when player identity is destroyed. That is the signature of an
EVENT-level artefact, not form.

Why the original test missed it: it de-conditioned at the ROUND level (field rate that round /
field rate that EVENT), which removes round-to-round differences INSIDE an event but says nothing
about the event's overall level against each player's history. If a week plays 20% easier than the
courses in a player's past, every one of their rounds that week carries a positive residual, and R1
will "predict" R2 for a reason that has nothing to do with form.

Its cross-event null (-0.005) could not catch this: pairing across events destroys the shared event
level as well as player identity, so it tests a weaker claim than it appears to.

This re-tests with the event level removed too:

    expected = player_baseline * event_factor * round_factor
    event_factor = field rate this event / field rate overall

If the correlation collapses toward the within-event null, H-P1 is an artefact and v1.2 must be
reverted.
"""
import math
import random
import statistics as st
from collections import defaultdict

import pga_learn as L

rows = L._rounds()
rate = {(t, p, int(r)): b / h for t, _tn, p, r, h, b, *_ in rows}
print("  %d player-rounds, %d events" % (len(rate), len({k[0] for k in rate})))

# ── field levels ─────────────────────────────────────────────────────────────
by_ev_rnd, by_ev, allv = defaultdict(list), defaultdict(list), []
for (t, p, r), v in rate.items():
    by_ev_rnd[(t, r)].append(v)
    by_ev[t].append(v)
    allv.append(v)
grand = st.mean(allv)
efac = {t: (st.mean(v) / grand if grand else 1.0) for t, v in by_ev.items()}
rfac = {}
for (t, r), v in by_ev_rnd.items():
    base = st.mean(by_ev[t]) or 1e-9
    rfac[(t, r)] = st.mean(v) / base
sp = sorted(efac.values())
print("  EVENT factors: 10th %.3f, median %.3f, 90th %.3f  (1.0 = an average week)"
      % (sp[int(.1 * len(sp))], sp[len(sp) // 2], sp[int(.9 * len(sp))]))
print("  -> weeks differ by this much; the original test never removed it.")

tot, per_ev = defaultdict(lambda: [0.0, 0]), defaultdict(lambda: [0.0, 0])
for (t, p, r), v in rate.items():
    tot[p][0] += v
    tot[p][1] += 1
    per_ev[(p, t)][0] += v
    per_ev[(p, t)][1] += 1


def build(remove_event):
    out = {}
    for (t, p, r), v in rate.items():
        s, n = tot[p]
        es, en = per_ev[(p, t)]
        s, n = s - es, n - en
        if n < 4:
            continue
        exp = (s / n) * rfac.get((t, r), 1.0) * (efac[t] if remove_event else 1.0)
        out[(t, p, r)] = v - exp
    return out


def corr(pairs):
    if len(pairs) < 12:
        return None
    xs, ys = [a for a, _ in pairs], [b for _, b in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((a - mx) * (b - my) for a, b in pairs) / (dx * dy) if dx and dy else None


def carry(resid):
    pairs, evs = [], []
    for (t, p, r), v in resid.items():
        nxt = resid.get((t, p, r + 1))
        if nxt is not None:
            pairs.append((v, nxt))
            evs.append(t)
    return pairs, evs


def within_event_null(pairs, evs):
    """Shuffle the feature WITHIN each event: player identity dies, the event survives."""
    rng = random.Random(17)
    byg = defaultdict(list)
    for i, e in enumerate(evs):
        byg[e].append(i)
    sh = list(pairs)
    for _e, idxs in byg.items():
        vals = [pairs[i][0] for i in idxs]
        rng.shuffle(vals)
        for i, v in zip(idxs, vals):
            sh[i] = (v, pairs[i][1])
    return corr(sh)


print("\n  %-42s %8s %9s %11s" % ("de-conditioning", "n", "carry r", "within-ev null"))
for lab, rm in (("ROUND level only (what H-P1 used)", False),
                ("ROUND + EVENT level (correct)", True)):
    resid = build(rm)
    pairs, evs = carry(resid)
    r = corr(pairs)
    nl = within_event_null(pairs, evs)
    print("  %-42s %8d %+9.3f %+11.3f" % (lab, len(pairs), r or 0, nl or 0))
    if rm:
        sd = st.pstdev([b for _, b in pairs])
        print("      -> true player-form effect: r=%+.3f, worth %.3f birdies per 18"
              % (r or 0, abs(r or 0) * sd * 18))

print("\n  READ: if the round-only row shows a null nearly equal to its r, that correlation was the")
print("  WEEK, not the player. The round+event row is the honest number.")
