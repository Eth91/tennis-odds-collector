"""29 projections have sat ungraded forever because the player never took the floor.

`grade()` resolves a row by finding the player's box score for that slate. A player who was
projected and then DID NOT PLAY produces no box score, so `cand` is empty, the loop hits `continue`,
and the row is rescanned every cycle for the rest of time. All 29 stragglers are this — verified,
every one has NO game-log entry for its slate date at all (0 were opponent-string mismatches, so
there is no join bug hiding underneath).

It is the same defect as the PGA round-scoped flags that stayed pending after a withdrawal: "no data
for this player" is the SAME OBSERVATION for "they didn't play" and "the game hasn't happened yet",
and resolving the second would destroy live rows.

TWO GUARDS, BOTH REQUIRED, because one is not enough:

  1. AGE. The slate must be at least DNP_MIN_AGE_DAYS old. A game in progress or just finished is
     never touched.
  2. THE PLAYER'S FEED MUST BE DEMONSTRABLY CURRENT PAST THAT SLATE — they must have a LATER game
     in their log. This is the guard that matters. Age alone cannot tell "she was a healthy scratch"
     apart from "our game-log feed for this player is broken/stale", and those need opposite
     handling. A player with a later game proves the feed advanced past the slate, so her absence
     from it is real. A player with no later game (season-ending injury, or a broken feed) stays
     PENDING — visible and unresolved, never guessed.

`graded=2` = "resolved: did not play". Checked against every consumer of that column first:
`grade()` scans `graded=0` so these stop being retried; `analyze()` filters `graded=1 AND
actual_min>0` so the minutes-bias read is completely unaffected; no other module filters on it.

⚠️ `actual_min` STAYS NULL. Writing 0 would be a fabricated observation that flows straight into any
future analysis as a real zero-minute game — the silent-zero failure this codebase keeps relearning.
We know she did not play; we do NOT know a stat line for a game she wasn't in.
"""
import ast
import io
import shutil

P = "wnba_proj_log.py"
s = io.open(P, encoding="utf-8").read()

if "DNP_MIN_AGE_DAYS" in s:
    print("  = already applied")
    raise SystemExit(0)

CONST = '''DNP_MIN_AGE_DAYS = 2     # a slate younger than this may still be in progress; never resolve it

'''
anchor0 = "\ndef _con():"
assert anchor0 in s, "const anchor"
s = s.replace(anchor0, "\n" + CONST + "\ndef _con():", 1)

OLD = '''        if not cand:
            continue'''
NEW = '''        if not cand:
            # DID NOT PLAY, or the game has not happened yet — the SAME observation. Resolving the
            # second would destroy live rows, so this only fires with both guards satisfied:
            # the slate is old enough to be over, AND this player's own feed is demonstrably
            # current past it (she has a later game). Without the second guard a stale or broken
            # game-log feed would be silently recorded as "she was a scratch".
            if _dnp_resolvable(date, cache[pid]):
                con.execute("UPDATE projections SET graded=2 WHERE rowid=?", (rid,))
                dnp += 1
            continue'''
assert OLD in s, "cand anchor"
s = s.replace(OLD, NEW, 1)

OLD2 = '''    cache, graded = {}, 0'''
NEW2 = '''    cache, graded, dnp = {}, 0, 0'''
assert OLD2 in s, "counter anchor"
s = s.replace(OLD2, NEW2, 1)

OLD3 = '''    con.commit()
    con.close()
    return graded'''
NEW3 = '''    con.commit()
    con.close()
    if dnp:
        print("proj grade: %d row(s) resolved as DID-NOT-PLAY (graded=2, actual_min left NULL)" % dnp)
    return graded'''
assert OLD3 in s, "return anchor"
s = s.replace(OLD3, NEW3, 1)

HELPER = '''

def _dnp_resolvable(date, log):
    """May a projection with no box score be settled as DID-NOT-PLAY? Both guards must hold.

    Returns False whenever we cannot TELL, which leaves the row pending and visible rather than
    silently recording a scratch that may just be a broken feed.
    """
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat(str(date)[:10])
    except (TypeError, ValueError):
        return False
    if (_dt.date.today() - d).days < DNP_MIN_AGE_DAYS:
        return False                       # slate may still be in progress
    # The player's own feed must have moved PAST this slate. A later game proves the log is current,
    # so her absence from this one is a real scratch and not a gap in our data.
    return any(str(g.get("date"))[:10] > str(date)[:10] for g in (log or []))

'''
anchor2 = "\ndef grade():"
assert anchor2 in s, "grade anchor"
s = s.replace(anchor2, HELPER + "\ndef grade():", 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_proj_log.predpn.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + grade() settles DID-NOT-PLAY rows as graded=2 once the slate is over AND the feed")
print("    is proven current past it; actual_min stays NULL, analyze() is untouched")
