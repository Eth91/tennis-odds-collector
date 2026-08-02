"""A durable manual VETO for a single play. Mirrors wnba_played.txt exactly.

WHAT THIS IS FOR. Sometimes a human knows something the model does not. Tonight's case: the model
flagged Julie Allemand over 5.5 assists off 11 elevated games, 9 of which also had Kiki Rice out —
and Rice is back, two games into a 56-day absence, still 8.5 minutes under her norm and climbing.
peer_regime_scan saw it and said so (2/11 sample match, 6.0 borrowed minutes); it just has no
authority to act, and the retrospective evidence (8-7, +2.2% ROI vs 27-10, +49.7%) is not yet
significant enough to give it any.

WHAT IT DELIBERATELY DOES NOT DO: remove the flag from the record. The ledger row stays and still
grades. That matters more than it looks — WNBA v1.2 is a FROZEN PROSPECTIVE TEST, and a test you
can retroactively withdraw entries from measures nothing. If discretionary skips deleted flags, the
model's record would improve every time a human overrode it and the SPRT would be scoring a
different, flattering model. The flag was made; it is scored; the veto only records that the human
declined to BET it.

So a veto affects exactly three things, all of them downstream of the model:
    - the play is not SELECTED (so it leaves the board's bet list)
    - it cannot be a PARLAY leg
    - it does not consume a TOP-2 slot, so the next-best play on that team-game is promoted
and it changes nothing about flagging, pricing, the projection, or the graded record.

Plain text for the same reason wnba_played.txt is plain text: it merges cleanly across the VM /
Actions / Mac writers where a sqlite blob would not, and it survives a DB reset.
"""
import ast
import io
import shutil

P = "wnba_slip.py"
s = io.open(P, encoding="utf-8").read()

if "_veto_marks" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── the marks file + reader, right beside the played-marks pair it mirrors ───────────────────────
OLD = 'PLAYED_MARKS = HERE / "wnba_played.txt"      # durable "I actually placed this" marks'
NEW = '''PLAYED_MARKS = HERE / "wnba_played.txt"      # durable "I actually placed this" marks
VETO_MARKS = HERE / "wnba_vetoed.txt"        # durable "I looked at this and passed" marks


def _veto_marks():
    """{(date, surname, stat, line)} from wnba_vetoed.txt — the human override of a flag.

    Same format and same surname matching as _played_marks, for the same reasons: the file is
    hand-edited and the ledger spells names in full. Format, '#' comments allowed:

        2026-08-02|Allemand|assists|5.5|Rice back+ramping, 9/11 elevated games had her out

    A vetoed play is NOT removed from the ledger and still grades. v1.2 is a frozen prospective
    test; letting a human delete entries from it would measure a model nobody is running.
    """
    out = set()
    try:
        for ln in VETO_MARKS.read_text().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            p = [x.strip() for x in ln.split("|")]
            if len(p) < 4:
                continue
            try:
                out.add((p[0], p[1].split()[-1].lower(), p[2].lower(), float(p[3])))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def _is_vetoed(r, marks):
    try:
        return (str(r.get("pred_date"))[:10],
                str(r.get("player") or "").split()[-1].lower(),
                str(r.get("stat") or "").lower(),
                float(r.get("line"))) in marks
    except (ValueError, TypeError, IndexError):
        return False'''
assert OLD in s, "played-marks anchor"
s = s.replace(OLD, NEW, 1)

# ── drop vetoed rows BEFORE the gates, so the slot they would have taken is freed ────────────────
OLD2 = """    _marks = _played_marks()
    forced = [r for r in overs if _is_played(r, _marks)] if _marks else []"""
NEW2 = """    # VETO FIRST. Removing it here (rather than filtering the final selection) is what lets the
    # next-best play on that team-game be promoted into the freed TOP-2 slot — filtering at the
    # end would leave a hole instead of a swap. A vetoed play keeps its ledger row and its grade.
    _vetoes = _veto_marks()
    if _vetoes:
        overs = [r for r in overs if not _is_vetoed(r, _vetoes)]

    _marks = _played_marks()
    forced = [r for r in overs if _is_played(r, _marks)] if _marks else []"""
assert OLD2 in s, "selection anchor"
s = s.replace(OLD2, NEW2, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_slip.preveto.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + wnba_slip: _veto_marks / _is_vetoed, applied before the TOP-2 gates")
