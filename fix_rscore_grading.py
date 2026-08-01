"""Add the missing E3-rscore grading branch.

THE GAP. grade_one() dispatches on stream and has branches for birdies, match, top10/20 and cut —
but none for E3-rscore. Those flags fell straight through to `return None`, so all 11 round-score
bets sat unsettled forever. Not a timing problem: the branch simply did not exist.

WHAT IS *NOT* BROKEN, and is deliberately left alone:
    E3-match (72 hole)  requires len(scores) >= 4  -> settles only when the event finishes
    E3-top10 / E3-top20 require ctx["final"]       -> ditto
Those are ungraded right now because the Rocket Classic is mid-tournament, which is correct. A
72-hole matchup or a top-10 finish has no result until the tournament has one, and forcing them
earlier would invent outcomes. They will settle on their own at event completion.

ROUND SCORE IS ROUND-SCOPED, so it settles the moment that round's score exists — same timing as
birdies. Market reads "<Player> Round N Score", runner "<Player> over|under <line>". Golf scores
are integers and the lines are half-strokes (66.5), so no push is possible; the guard is kept
anyway rather than assuming the book never posts a whole number.
"""
import ast
import io
import shutil

P = "pga_grade_e3.py"
s = io.open(P, encoding="utf-8").read()

if "E3-rscore" in s:
    print("  = rscore branch already present")
    raise SystemExit(0)

anchor = '''    if stream.startswith("E3-match"):'''
NEW = '''    if stream.startswith("E3-rscore"):
        # ROUND-SCOPED: settles as soon as that round's score exists, exactly like birdies.
        # There was no branch here at all, so every round-score flag fell through to None and
        # never settled — 11 of them on the Rocket Classic alone.
        m = re.search(r"^(.*?)\\s+(over|under)\\s+([\\d.]+)$", runner.strip(), re.I)
        rm = re.search(r"Round\\s+(\\d)", market or "")
        if not m or not rm:
            return None
        who, side, line = _norm(m.group(1)), m.group(2).lower(), float(m.group(3))
        k = int(rm.group(1))
        rs = scores.get(who)
        if rs is None or len(rs) < k:
            return None                                # that round not in the book yet
        sc = rs[k - 1]
        if sc == line:
            return ("P", 0.0)                          # lines are half-strokes, but never assume
        won = (sc > line) if side == "over" else (sc < line)
        return ("W", odds - 1.0) if won else ("L", -1.0)

    if stream.startswith("E3-match"):'''
assert anchor in s, "match anchor missing"
s = s.replace(anchor, NEW, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_grade_e3.prerscore.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + E3-rscore branch added (round-scoped, settles with the round)")
