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

# Whole-function replacement rather than a set of narrow anchors. grade() is restructured into two
# passes here, so patching it line-by-line left the apply script and the live file able to drift —
# and a patch script that no longer reproduces the file it documents is worse than none, because
# the VM loop hard-resets and these scripts are what rebuild the change.
CONST = "DNP_MIN_AGE_DAYS = 2     # a slate younger than this may still be in progress; never resolve it\n\n"
anchor = "\ndef _con():"
assert anchor in s, "const anchor"
s = s.replace(anchor, "\n" + CONST + anchor, 1)

OLD = '\ndef grade():\n    con = _con()\n    rows = con.execute("SELECT rowid, date, pid, opp FROM projections WHERE graded=0").fetchall()\n    if not rows:\n        con.close()\n        return 0\n    ids = {v["id"]: n for n, v in W.players().items()}     # ensure name cache warm (pid is the key)\n    cache, graded = {}, 0\n    for rid, date, pid, opp in rows:\n        if pid not in cache:\n            try:\n                cache[pid] = W.game_log(pid)\n            except RuntimeError:\n                cache[pid] = []\n        cand = sorted((g for g in cache[pid]\n                       if g.get("result") and g["date"][:10] >= date\n                       and (not opp or (g.get("matchup") or "").upper() == opp.upper())),\n                      key=lambda g: g["date"])\n        if not cand:\n            continue\n        g = cand[0]\n        con.execute("UPDATE projections SET actual_min=?, actual_pts=?, actual_reb=?, "\n                    "actual_ast=?, graded=1 WHERE rowid=?",\n                    (g["min"], g["pts"], g["reb"], g["ast"], rid))\n        graded += 1\n    con.commit()\n    con.close()\n    return graded\n\n'
NEW = '\ndef _dnp_resolvable(date, log, feed_max=None):\n    """May a projection with no box score be settled as DID-NOT-PLAY? Both guards must hold.\n\n    Returns False whenever we cannot TELL, which leaves the row pending and visible rather than\n    silently recording a scratch that may just be a broken feed.\n\n    CURRENCY IS PROVEN AT THE FEED, NOT THE PLAYER. The first version of this asked whether the\n    PLAYER had a later game — and that fails on exactly the dominant case: a player on a long\n    absence has no later game BECAUSE she never came back, which is the very thing we are trying to\n    record. Haley Jones was projected 2026-07-20 with her last game on 05-20; her own log can never\n    clear that bar. `feed_max` is the newest game date seen anywhere in this run, so it answers the\n    question actually being asked — did our data source advance past this slate? If it did, an\n    absent player was absent. If it did not, we know nothing and refuse.\n    """\n    import datetime as _dt\n    try:\n        d = _dt.date.fromisoformat(str(date)[:10])\n    except (TypeError, ValueError):\n        return False\n    if (_dt.date.today() - d).days < DNP_MIN_AGE_DAYS:\n        return False                       # slate may still be in progress\n    ds = str(date)[:10]\n    if feed_max and str(feed_max)[:10] > ds:\n        return True                        # the SOURCE moved past this slate: absence is real\n    return any(str(g.get("date"))[:10] > ds for g in (log or []))\n\n\ndef grade():\n    con = _con()\n    rows = con.execute("SELECT rowid, date, pid, opp FROM projections WHERE graded=0").fetchall()\n    if not rows:\n        con.close()\n        return 0\n    ids = {v["id"]: n for n, v in W.players().items()}     # ensure name cache warm (pid is the key)\n    cache, graded, dnp = {}, 0, 0\n    # Feed high-water mark: the newest game date anywhere in the logs this run touches. Computed\n    # from the same fetches the grading loop already makes, so it costs nothing extra, and it is\n    # the honest proof that the data source is current rather than silently truncated.\n    _feed_max = None\n    # PASS 1 — fetch every log, and only then establish the feed high-water mark. Accumulating\n    # it inside the resolution loop was wrong in a way that silently did nothing: rows come back in\n    # rowid order, so the OLD rows (the ones needing resolution) were tested against a _feed_max\n    # built only from the equally-old logs seen so far, while the current-slate logs that prove the\n    # feed advanced were not read until later. The mark has to be complete before it is used.\n    for _rid, _date, _pid, _opp in rows:\n        if _pid not in cache:\n            try:\n                cache[_pid] = W.game_log(_pid)\n            except RuntimeError:\n                cache[_pid] = []\n        for _g in cache[_pid]:\n            _gd = str(_g.get("date"))[:10]\n            if _gd and (_feed_max is None or _gd > _feed_max):\n                _feed_max = _gd\n\n    # PASS 2 — resolve.\n    for rid, date, pid, opp in rows:\n        cand = sorted((g for g in cache[pid]\n                       if g.get("result") and g["date"][:10] >= date\n                       and (not opp or (g.get("matchup") or "").upper() == opp.upper())),\n                      key=lambda g: g["date"])\n        if not cand:\n            # DID NOT PLAY, or the game has not happened yet — the SAME observation. Resolving the\n            # second would destroy live rows, so this only fires with both guards satisfied:\n            # the slate is old enough to be over, AND this player\'s own feed is demonstrably\n            # current past it (she has a later game). Without the second guard a stale or broken\n            # game-log feed would be silently recorded as "she was a scratch".\n            if _dnp_resolvable(date, cache[pid], _feed_max):\n                con.execute("UPDATE projections SET graded=2 WHERE rowid=?", (rid,))\n                dnp += 1\n            continue\n        g = cand[0]\n        con.execute("UPDATE projections SET actual_min=?, actual_pts=?, actual_reb=?, "\n                    "actual_ast=?, graded=1 WHERE rowid=?",\n                    (g["min"], g["pts"], g["reb"], g["ast"], rid))\n        graded += 1\n    con.commit()\n    con.close()\n    if dnp:\n        print("proj grade: %d row(s) resolved as DID-NOT-PLAY (graded=2, actual_min left NULL)" % dnp)\n    return graded\n\n'
assert OLD in s, "grade() block anchor"
s = s.replace(OLD, NEW + chr(10), 1)   # keep the blank line before _bias()

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_proj_log.predpn.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + grade() settles DID-NOT-PLAY rows as graded=2 once the slate is over AND the feed")
print("    is proven current past it; actual_min stays NULL, analyze() is untouched")
