"""Void round-specific flags on players who never teed off, so they leave the board.

THE PROBLEM. A round-scoped flag (birdies / round score) settles the moment that round's score
exists. If the player WITHDRAWS, that score never exists — so the flag stays PENDING forever, and
the board renders open flags with `WHERE result IS NULL`. Seamus Power has two Round 2 birdie flags
from 2026-07-31 and zero rounds anywhere in the 2026 results: he never played. Those two rows would
have sat on the board indefinitely, long after the tournament ended.

A DNP IS A VOID, NOT A LOSS. The bet was never live — books refund it — so scoring it as a loss
would understate the model by a full unit per withdrawal, and leaving it pending overstates how much
is still running. Void is the only honest settlement, and it counts as a push in the record
(pga_e1's tally buckets anything that is not W/L into "p").

THE GUARD IS THE WHOLE POINT: DO NOT VOID A ROUND THAT SIMPLY HAS NOT FINISHED. "No score for this
player" is the same observation for a withdrawal and for a round still in progress, and voiding the
second would destroy live bets. So a flag is only voided when the round is demonstrably COMPLETE for
the field — at least VOID_FIELD_MIN other players already have a score for that round — AND this
player has none. Today's Round 4 flags are therefore untouched while R4 is being played, and become
voidable only if their player never posts a score once the field has.
"""
import ast
import io
import shutil

P = "pga_grade_e3.py"
s = io.open(P, encoding="utf-8").read()

if "VOID_FIELD_MIN" in s:
    print("  = already applied")
    raise SystemExit(0)

FN = '''

VOID_FIELD_MIN = 20      # players who must already have a score for round k before "no score for
                         # THIS player" can mean withdrawal rather than "the round is still running"


def void_dnps(con, scores):
    """Settle round-scoped flags whose player never teed off. Returns how many were voided.

    A withdrawal produces the same observation as an unfinished round — no score — so this only
    fires once the FIELD has demonstrably completed that round. Without that guard it would void
    live bets mid-round, which is far worse than a stale row on the board.
    """
    import re as _re
    done = {}
    for _p, _rs in (scores or {}).items():
        for k in range(1, 5):
            if len(_rs) >= k:
                done[k] = done.get(k, 0) + 1
    n = 0
    for key, market, runner, stream in con.execute(
            "SELECT key, market, runner, stream FROM flags WHERE result IS NULL").fetchall():
        rm = _re.search(r"Round\\s+(\\d)", market or "")
        if not rm:
            continue                                  # 72-hole markets settle at event end
        k = int(rm.group(1))
        if done.get(k, 0) < VOID_FIELD_MIN:
            continue                                  # round not finished for the field — leave it
        m = _re.search(r"^(.*?)\\s+(over|under)\\s+[\\d.]+$", (runner or "").strip(), _re.I)
        who = _norm(m.group(1)) if m else None
        if who is None:
            continue
        rs = scores.get(who)
        if rs is not None and len(rs) >= k:
            continue                                  # they DID play it; the normal grader owns it
        con.execute("UPDATE flags SET result='V', pnl=0.0, graded_at=? WHERE key=?",
                    (__import__("datetime").datetime.utcnow().replace(microsecond=0).isoformat(), key))
        n += 1
    return n
'''

anchor = "\ndef grade_one("
assert anchor in s, "grade_one anchor"
s = s.replace(anchor, FN + "\ndef grade_one(", 1)

# call it after the normal grading pass, wherever the connection is committed
import re
m = re.search(r"\n(\s*)con\.commit\(\)", s)
assert m, "commit anchor"
ind = m.group(1)
call = (f"\n{ind}# settle withdrawals so round-scoped flags cannot sit on the board forever\n"
        f"{ind}try:\n"
        f"{ind}    _nv = void_dnps(con, scores)\n"
        f"{ind}    if _nv:\n"
        f"{ind}        print('pga_grade_e3: voided %d flag(s) whose player never teed off' % _nv)\n"
        f"{ind}except Exception as _ve:\n"
        f"{ind}    print('void sweep skipped: %s' % str(_ve)[:70])\n"
        f"{ind}con.commit()")
s = s[:m.start()] + call + s[m.end():]

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_grade_e3.prevoid.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + void_dnps(): round-scoped flags on withdrawn players settle as V once the field finishes")
