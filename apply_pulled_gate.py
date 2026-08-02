"""A play whose SUBJECT is ruled out stays on the board forever. So does a vetoed one.

TWO FAILURES, ONE CAUSE. The board and the slip do not share a gate.

  * `wnba_slip.current_selection()` drops vetoed plays — that is the path the RECORD uses.
  * `dashboard._load()` renders `SELECT * FROM predictions WHERE pred_date>=? AND result IS NULL`
    and consults nothing at all — that is the path the BOARD uses.

So today's manual veto on Allemand freed her TOP-2 slot and swapped in the next play, exactly as
intended, while the board kept showing her. And Marina Mabrey, ruled OUT (Neck) by all three
sources — Underdog X, the official report, and RotoWire — is still sitting on the board at
pts_ast 22.5/23.5, because there is no retraction path for a subject who is later ruled out. The
flagger is CORRECT and would not re-flag her (verified live: `injuries()` = Out,
`confirmed_playing` = False, `genuinely_out` = True, so she is in `out_names` and screened at
wnba_alert.py:191 and :276). The bet was written before the news landed, and nothing ever revisits
a row once written.

This is the standing ping/board coherence rule failing in a new direction: the alert and the record
share one gate, but the BOARD was never wired to it.

THE FIX IS ONE PREDICATE, USED BY BOTH. `_suppressed()` answers "would we still put this in front
of a human right now?" and both call sites use it. Two independent reasons:
  1. a manual veto (unchanged behaviour, now also honoured by the board), and
  2. the subject is firm-out — read from `wnba_injuries_board.json`, which the alert pipeline
     already writes every cycle from the same `injuries()` the flagger uses. Reading the published
     artefact rather than re-querying keeps a network call out of the renderer AND guarantees the
     board suppresses on exactly the data the flagger gated on.

⚠️ THE LEDGER ROW IS NOT TOUCHED, and this is not negotiable. v1.2 is a frozen prospective test; a
test you can retroactively withdraw entries from measures nothing. The row stays, still grades, and
if she does play it grades normally — so a wrong suppression is self-correcting and visible in the
record rather than hidden. Suppression is a DISPLAY and SELECTION decision, never a deletion.

⚠️ NO SILENT ZERO. If `wnba_injuries_board.json` is missing, unparseable or stale, `_out_marks()`
returns None — NOT an empty set. An empty set would read as "nobody is out" and silently restore the
exact bug this fixes; every outage in this stack has been an unreadable input reported as a real
zero. None means "unknown", the board suppresses nothing on that basis, and the caller can say so.
"""
import ast
import io
import shutil

# ---------------------------------------------------------------- wnba_slip: the shared predicate
P = "wnba_slip.py"
s = io.open(P, encoding="utf-8").read()

if "_out_marks" in s:
    print("  = slip already applied")
else:
    FN = '''

INJ_BOARD = HERE / "wnba_injuries_board.json"   # written every cycle by the alert pipeline
OUT_MAX_AGE_H = 6.0                             # older than this and the feed is not evidence


def _out_marks():
    """{surname_lower} for players firm-OUT tonight, or None when that cannot be established.

    Source is `wnba_injuries_board.json` — the artefact the alert pipeline already publishes from
    the same `wnba_tonight.injuries()` the flagger gates on. Reading the published file instead of
    re-querying keeps a network call out of the renderer and guarantees the board suppresses on
    exactly the data the flag was screened against, rather than a second opinion that can drift.

    RETURNS None, NEVER AN EMPTY SET, when the file is missing, unparseable or stale. An empty set
    would mean "nobody is out" and would silently reinstate the bug this exists to fix. Every
    outage in this stack has been an unreadable input reported as a confident zero.
    """
    import datetime as _dt
    import json as _json
    try:
        d = _json.loads(INJ_BOARD.read_text())
        ts = _dt.datetime.fromisoformat(str(d["ts"]).replace("Z", "+00:00"))
        age = (_dt.datetime.now(_dt.timezone.utc) - ts).total_seconds() / 3600.0
        if age > OUT_MAX_AGE_H:
            return None                                  # stale: refuse, do not guess
        rows = d.get("rows")
        if not isinstance(rows, list):
            return None
        return {str(r.get("player") or "").split()[-1].lower()
                for r in rows if str(r.get("status")) in ("Out", "Doubtful")
                and str(r.get("player") or "").strip()}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _is_pulled(r, outs):
    """Is this bet's own SUBJECT ruled out? `outs` of None means unknown -> never suppress."""
    if not outs:
        return False
    try:
        return str(r.get("player") or "").split()[-1].lower() in outs
    except (AttributeError, IndexError):
        return False


_UNSET = object()      # distinct from None, which legitimately MEANS "out-status unknown"


def suppressed(rows, vetoes=_UNSET, outs=_UNSET):
    """Split `rows` into (keep, dropped) on the ONE gate the board and the slip must share.

    A play is suppressed when a human vetoed it, or when its subject is firm-out. Both are display
    and selection decisions: the ledger row is untouched, still grades, and grades normally if the
    player turns out to play — so a wrong call surfaces in the record instead of hiding there.
    """
    # `None` is a REAL value here — _out_marks() returns it for "unknown", and a caller passing
    # it must get that meaning, not a silent re-lookup. Hence a separate not-supplied sentinel.
    vetoes = _veto_marks() if vetoes is _UNSET else vetoes
    outs = _out_marks() if outs is _UNSET else outs
    keep, drop = [], []
    for r in rows:
        why = ("vetoed" if (vetoes and _is_vetoed(r, vetoes))
               else "subject ruled out" if _is_pulled(r, outs) else None)
        (drop if why else keep).append(r if not why else dict(r, _suppressed=why))
    return keep, drop

'''
    anchor = "\n\ndef _played_marks():"
    assert anchor in s, "played_marks anchor"
    s = s.replace(anchor, FN + "\ndef _played_marks():", 1)

    # current_selection must drop BOTH reasons in the same place the veto already fires, so the
    # freed TOP-2 slot is filled by the next-best play rather than left as a hole.
    OLD = '''    _vetoes = _veto_marks()
    if _vetoes:
        overs = [r for r in overs if not _is_vetoed(r, _vetoes)]'''
    NEW = '''    # SUPPRESS BEFORE THE TOP-2 GATES, both reasons together. A human veto and a subject who has
    # since been ruled out are the same thing to the selection: a play we would not put up now.
    # Filtering here (not at the end) is what promotes the next-best play into the freed slot.
    overs, _dropped = suppressed(overs)
    if _dropped:
        for _d in _dropped:
            print("  suppressed (%s): %s %s %s" % (_d.get("_suppressed"), _d.get("player"),
                                                   _d.get("stat"), _d.get("line")))'''
    assert OLD in s, "veto block anchor"
    s = s.replace(OLD, NEW, 1)

    ast.parse(s)
    shutil.copyfile(P, "/tmp/wnba_slip.prepulled.py")
    io.open(P, "w", encoding="utf-8").write(s)
    print("  + wnba_slip.suppressed(): one gate for veto + subject-ruled-out")

# ---------------------------------------------------------------- dashboard: wire the board to it
P2 = "dashboard.py"
s2 = io.open(P2, encoding="utf-8").read()

if "_suppressed" in s2:
    print("  = dashboard already applied")
    raise SystemExit(0)

OLD2 = '''    rows = [dict(r) for r in con.execute(
        "SELECT * FROM predictions WHERE pred_date>=? AND result IS NULL "
        "ORDER BY pred_date ASC, ev DESC",
        (mt_date,))]'''
NEW2 = '''    rows = [dict(r) for r in con.execute(
        "SELECT * FROM predictions WHERE pred_date>=? AND result IS NULL "
        "ORDER BY pred_date ASC, ev DESC",
        (mt_date,))]
    # THE BOARD MUST USE THE SAME GATE AS THE SLIP (2026-08-02). This query used to render every
    # un-settled row and consult nothing, so a manual veto freed the slip's TOP-2 slot while the
    # board kept showing the play, and a subject ruled out after flag time never came off at all
    # (Marina Mabrey, OUT with a neck injury, still showing pts_ast 22.5/23.5). The ledger row is
    # untouched and still grades — this only decides what a human is shown right now.
    try:
        import wnba_slip as _WSUP
        rows, _sup = _WSUP.suppressed(rows)
        for _d in _sup:
            print("board: suppressed (%s) %s %s %s" % (_d.get("_suppressed"), _d.get("player"),
                                                       _d.get("stat"), _d.get("line")))
    except Exception as _se:                                         # noqa: BLE001
        print("board: suppression gate unavailable (%s) — showing every open row" % str(_se)[:60])'''
assert OLD2 in s2, "board query anchor"
s2 = s2.replace(OLD2, NEW2, 1)

ast.parse(s2)
shutil.copyfile(P2, "/tmp/dashboard.prepulled.py")
io.open(P2, "w", encoding="utf-8").write(s2)
print("  + dashboard board query now runs through the same gate")
