"""Stamp each flag's OWN deadline instead of the event's R1 first tee. Idempotent, ast-checked.

THE BUG. `_first_tee` was resolved once per event with `WHERE tid=? AND rnd=1`, then written into
every flag's `first_tee` column regardless of which round the market belonged to. So a Round 3
round-score flag recorded Wednesday's 11:00Z R1 tee as its deadline — two days before the bet
actually died. The Rocket Classic logged 21 Round-2 flags, every one of them stamped with R1's tee.

WHAT THIS DOES *NOT* TOUCH, and why that is the point. `pga_validate.py` was already fixed on
2026-07-31: it resolves each flag's deadline through `pga_tee_gate._player_deadline(event, market)`
and never reads the stored column for the capture test. So this change CANNOT move a single SPRT
number — verified by re-running pga_validate before and after and diffing the output. That is what
makes it safe to land under the v1.3 freeze: the frozen artefact is the model and its constants,
and this rewrites neither. No gate, no constant, no probability changes.

WHAT IT DOES FIX. `pga_check.py` counts integrity as `snapshot_ts < first_tee` — "rows captured
before the tee". With R1's tee in the column that number is wrong in both directions for every
Round 2+ flag: a legitimately pre-tee R3 bet reads as post-tee (its snapshot is Saturday, the
stamp is Wednesday), and a genuinely late R2 bet could read as clean. The ledger is the evidence
base for the whole validation; a column that means something different per row makes it unreadable
later, when nobody remembers the caveat.

THE GATE IS DELIBERATELY LEFT ALONE. `is_open()` still decides whether to log, exactly as before,
with identical semantics — deadline() is called only to record what that gate already implied. Two
calls where one would do, on purpose: rewriting the gate to reuse a resolved deadline would change
control flow in the one place that decides whether a bet exists at all, for a cosmetic saving.
`_load()` memoises the tee sheet, so the second call is a dict lookup.
"""
import ast
import io
import shutil

P = "pga_e3.py"
s = io.open(P, encoding="utf-8").read()

if "_tee_stamp" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── 1. the log line stops claiming the R1 tee is the capture boundary ────────────────────────────
OLD_LOG = '''    print(f"  capture: snapshot {snap_ts} | first R1 tee {_first_tee or 'UNKNOWN'}")'''
NEW_LOG = '''    # R1's tee is printed for orientation only. It is NOT the capture boundary for anything but
    # a field-wide outright — each flag below stamps its own deadline from the shared tee gate.
    print(f"  capture: snapshot {snap_ts} | R1 first tee {_first_tee or 'UNKNOWN'} "
          f"(per-flag deadlines from pga_tee_gate)")'''
assert OLD_LOG in s, "log anchor"
s = s.replace(OLD_LOG, NEW_LOG, 1)

# ── 2. resolve THIS market's deadline at the point the gate already ran ──────────────────────────
OLD_GATE = '''            if not _TEEGATE.is_open(evn, pv["market"]):
                _n_teed += 1
                continue'''
NEW_GATE = '''            if not _TEEGATE.is_open(evn, pv["market"]):
                _n_teed += 1
                continue
            # THIS market's own deadline — a player tee for a single-player market, the earlier of
            # the two for a matchbet, the R1 first tee for a field outright. Previously every flag
            # was stamped with the event's R1 tee, so a Round 3 bet recorded a Wednesday deadline.
            # is_open() already returned True, so a deadline exists; the guard is for the case
            # where the tee sheet is reloaded between the two calls.
            _dl, _ = _TEEGATE.deadline(evn, pv["market"])
            _tee_stamp = (_dl.replace(microsecond=0).isoformat() if _dl else None)'''
assert OLD_GATE in s, "gate anchor"
s = s.replace(OLD_GATE, NEW_GATE, 1)

# ── 3. write the per-flag stamp, not the event-level one ─────────────────────────────────────────
OLD_INS = '''                 snap_ts, _first_tee,'''
NEW_INS = '''                 snap_ts, _tee_stamp,'''
assert s.count(OLD_INS) == 1, "insert anchor not unique"
s = s.replace(OLD_INS, NEW_INS, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_e3.prestamp.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + first_tee now holds each flag's OWN deadline (player tee / earlier-of-two / R1 outright)")
