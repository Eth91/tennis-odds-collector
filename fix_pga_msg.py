"""The report blamed missing instrumentation for rows the CAPTURE RULE excluded.

All 7 settled rows carry p_bet and p_fair — they are perfectly scorable. They are out because every
one was flagged after that player had already teed off. Saying "logged before instrumentation"
sends anyone reading it to fix the wrong thing, and hides the finding that matters: we were pricing
Round 1 markets nine hours into Round 1.
"""
import ast, io, shutil
P="pga_validate.py"; s=io.open(P,encoding="utf-8").read()
old = '              + ("" if graded == 0 else " (logged before instrumentation — ROI only, unscorable)"),'
new = ('              + ("" if graded == 0 else _why_unscored(graded)),')
if "_why_unscored" in s:
    print("  = message already accurate"); raise SystemExit(0)
assert old in s, "message anchor missing"
s = s.replace(old, new, 1)

HELP = '''
def _why_unscored(graded):
    """Say WHY settled rows are not scored, distinguishing the two very different causes: missing
    probabilities (an instrumentation gap) versus the capture rule refusing them (a timing fact
    about when we priced). Blaming the wrong one sends the reader to fix the wrong thing."""
    import sqlite3
    try:
        c = sqlite3.connect(str(LEDGER))
        both = c.execute("SELECT COUNT(*) FROM flags WHERE result IN ('W','L') "
                         "AND p_bet IS NOT NULL AND p_fair IS NOT NULL").fetchone()[0]
        c.close()
    except Exception:                                              # noqa: BLE001
        return " (unscorable)"
    if both == 0:
        return " (logged before instrumentation — ROI only, unscorable)"
    if both < graded:
        return (" (%d carry both probabilities; the rest predate instrumentation. None captured "
                "before their player teed off)" % both)
    return (" — all %d carry both probabilities and are scorable in principle, but every one was "
            "flagged AFTER that player had teed off, so the capture rule excludes them" % both)


'''
anchor = "def report("
assert anchor in s, "report anchor missing"
s = s.replace(anchor, HELP.lstrip("\n") + anchor, 1)
ast.parse(s)
shutil.copyfile(P, "/tmp/pga_validate.premsg.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + report now states the real reason rows are unscored")
