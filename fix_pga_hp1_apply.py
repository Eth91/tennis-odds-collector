"""Apply H-P1: shift each player's birdie rate by the form they have shown THIS tournament.

MEASURED (pga_form_test.py, 42,557 player-rounds / 114 events): after removing round-level
conditions and using leave-one-event-out baselines, a player's residual carries to their next round
at r = +0.152 — R1→R2 +0.150, R2→R3 +0.156, R3→R4 +0.156, against a cross-event null of -0.005.

WHY IT CANNOT JUST BE "ADD THIS WEEK'S ROUNDS TO THE POOL". rates() recency-weights with a 120-day
half-life over a player's whole history, so one fresh round lands at roughly 4% weight against ~30
prior rounds. The measurement says the correct weight is ~15%. Pooling would therefore apply about
a quarter of the effect that was actually measured. So the shift is explicit.

    field_now   = the field's actual rate over this event's completed rounds  (absorbs conditions:
                  wind, pins, setup — the same de-conditioning the test used)
    expected(p) = player's multiplier * field_now                            (what we'd have said)
    residual(p) = actual(p) - expected(p)
    shift(p)    = FORM_R * residual(p)                                        added to every par rate

BASELINE EXCLUDES THIS EVENT. rates() now takes live_tid and drops that tid from the historical
aggregation, so the current tournament never informs its own expectation — otherwise the residual
would be computed against a baseline that already contains it and would shrink toward zero.

⚠ ADOPTED AGAINST THE STANDING RULE, and recorded as such. H-P1 was registered as needing a paired
SPRT over >=100 prospective bets. It is being adopted on retrospective evidence at the user's
direction. The mitigating facts: it is not a threshold fitted to our betting record but an
information source measured on 27,756 independent round-pairs with a clean null, and the model had
ZERO scored bets, so no outcome could have informed it. It is still a departure and the manifest
says so.

EXPECT FEWER FLAGS, NOT FATTER ONES. The book already prices R1 form; this mostly stops us
disagreeing with it for a bad reason. If flag count rises sharply, something is wrong.
"""
import ast
import io
import shutil

P = "pga_birdies.py"
s = io.open(P, encoding="utf-8").read()

if "FORM_R" in s:
    print("  = H-P1 already applied")
    raise SystemExit(0)

# ── constants ────────────────────────────────────────────────────────────────
anchor_c = "def rates("
assert anchor_c in s, "rates() missing"
CONST = '''# ── H-P1: within-tournament form (2026-07-31) ───────────────────────────────────────────────
# A player's residual in one round carries to the next at r=+0.152, measured on 42,557
# player-rounds / 114 events after removing round-level conditions, with leave-one-event-out
# baselines and a cross-event null of -0.005 (R1->R2 +0.150, R2->R3 +0.156, R3->R4 +0.156).
# Residual sd is 1.79 birdies per 18, so this moves a projection ~0.27 birdies.
FORM_R = 0.152          # weight on the current event's residual; 0.0 disables H-P1 entirely
FORM_MIN_HOLES = 15     # need a real completed round before trusting a residual


def live_rounds(tid, tname, cache={}):
    """This event's COMPLETED rounds, fetched live — the weekly harvest does not have them.

    Returns {player: (holes, birdies)} aggregated over every completed round so far. Cached per
    tid+round-count so a */30 cron does not re-pull 148 scorecards every pass. Any failure returns
    {} and H-P1 simply does not fire: a missing fetch must never change a price silently.
    """
    key = str(tid)
    if key in cache:
        return cache[key]
    out = {}
    try:
        for pid, pname in players_of(tid):
            try:
                for row in scorecard_rows(tid, tname, pid, pname):
                    _, _, pn, _rnd, p3h, p3b, p4h, p4b, p5h, p5b = row
                    h, b = out.get(pn, (0, 0))
                    out[pn] = (h + p3h + p4h + p5h, b + p3b + p4b + p5b)
            except Exception:                                       # noqa: BLE001
                continue
    except Exception:                                               # noqa: BLE001
        out = {}
    cache[key] = out
    return out


'''
s = s.replace(anchor_c, CONST + anchor_c, 1)

# ── rates() takes live_tid and excludes it from the baseline ─────────────────
old_sig = "def rates(course_factor=1.0, wind_kmh=None, half_life_d=120.0, course_name=None):"
new_sig = ("def rates(course_factor=1.0, wind_kmh=None, half_life_d=120.0, course_name=None,\n"
           "          live_tid=None, live_tname=None):")
assert old_sig in s, "rates signature anchor missing"
s = s.replace(old_sig, new_sig, 1)

old_agg = """    for tid, pl, p3h, p3b, p4h, p4b, p5h, p5b in con.execute(
            "SELECT tid, player, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
            "FROM birdie_rounds GROUP BY tid, player"):"""
new_agg = """    for tid, pl, p3h, p3b, p4h, p4b, p5h, p5b in con.execute(
            "SELECT tid, player, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
            "FROM birdie_rounds GROUP BY tid, player"):
        # H-P1: the current event must never inform its own baseline, or the residual is measured
        # against a number that already contains it and shrinks toward zero (the same
        # leave-one-event-out discipline the measurement used).
        if live_tid and str(tid) == str(live_tid):
            continue"""
assert old_agg in s, "aggregation anchor missing"
s = s.replace(old_agg, new_agg, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_birdies.prehp1.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + FORM_R / live_rounds() added; rates() accepts live_tid and excludes it from the baseline")
