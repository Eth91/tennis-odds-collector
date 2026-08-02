"""The premise sweep voided 4 real bets because a player who WAS out stopped being listed as out.

WHAT THE SWEEP IS FOR. A bet is priced off named players being absent. If one of them flips back to
playing before tip, the premise is broken and the bet must void rather than be graded as if the
model got it right. That is correct and should stay.

THE DEFECT. It decides "she is playing again" with:

    if names and any(_inj.get(nm) not in ("Out", "Doubtful") for nm in names)

`injuries()` is an injury REPORT — it lists players who are hurt, not the whole league. So a player
disappears from it for two completely different reasons: she recovered, or the report rolled over to
the next slate and dropped yesterday's entries. `.get()` returns None either way, `None not in
(...)` is True, and the bet voids. **A missing key is being read as positive evidence that she is
active.** That is the same silent-zero shape as the empty-view outage the guard above already
covers; the guard refuses only when the view is TOTALLY empty, so a partial or rolled-over view
walks straight through it.

MEASURED COST — 4 of the 16 voids in the ledger are wrong, and in every one the out-basis player
genuinely did not play:
    2026-07-19 Diamond Miller       pts o8.5   off Morrow (DNP)   -> actual 6,  would be a LOSS
    2026-07-19 Olivia Nelson-Ododa  pts o11.5  off Morrow (DNP)   -> actual 12, would be a WIN
    2026-07-28 Breanna Stewart      RA  o12.5  off Fiebich+Johannes+Sabally (all absent) -> 11, LOSS
    2026-07-28 Olivia Nelson-Ododa  reb o6.5   off Griner (DNP)   -> actual 6,  would be a LOSS
Three losses and one win erased. The record reads better than it earned: 34-17 +13.86u where the
truth is 34-18 +12.86u.

THE FIX IS TO PREFER GROUND TRUTH OVER THE FEED. Once a slate has been played, whether someone
suited up is not a matter of opinion — the box score says so. So before voiding, check whether the
out-basis player actually appears in the game log for that date:

  * she has a game-log row for the slate  -> she really did play, the premise really did break, VOID
  * she has none, and the feed is current past that date -> she did NOT play, the premise HELD,
    so do NOT void; let it grade normally
  * cannot establish either -> leave the row alone; an ungraded row is visible, a wrongly voided
    one is silently gone

For a slate that has not been played yet there is no box score, so the sweep keeps its existing
pre-tip behaviour — that is the case it was built for and it is unchanged.
"""
import ast
import io
import shutil

P = "wnba_ledger.py"
s = io.open(P, encoding="utf-8").read()

if "_premise_really_broke" in s:
    print("  = already applied")
    raise SystemExit(0)

HELPER = '''

def _premise_really_broke(names, slate):
    """Did an out-basis player ACTUALLY play on `slate`? Ground truth beats the injury feed.

    Returns True only on positive evidence that someone the bet assumed absent did take the floor.
    Returns False when the box score shows they did not — the premise held and the bet must grade,
    not void. Returns None when it cannot be established, and the caller then leaves the row alone.

    This exists because `injuries()` is a REPORT, not a roster: a player vanishes from it both when
    she recovers and when the report rolls to the next slate. The feed cannot tell those apart. The
    box score can.
    """
    try:
        import wnba_wowy as _W
        pl = _W.players()
    except Exception:                                                # noqa: BLE001
        return None
    feed_max, played = None, False
    for nm in names:
        p = pl.get(nm)
        if not p:
            return None                                  # unknown player -> cannot establish
        try:
            lg = _W.game_log(p["id"])
        except Exception:                                            # noqa: BLE001
            return None
        for g in lg or []:
            gd = str(g.get("date"))[:10]
            if gd and (feed_max is None or gd > feed_max):
                feed_max = gd
            if gd == str(slate)[:10]:
                played = True
    if played:
        return True                                      # she suited up: the premise really broke
    if feed_max and feed_max > str(slate)[:10]:
        return False                                     # feed is past the slate and she is absent
    return None                                          # feed not current: refuse to conclude

'''

anchor = "\ndef log_predictions("
assert anchor in s, "helper anchor"
s = s.replace(anchor, HELPER + "\ndef log_predictions(", 1)

OLD = '''            if names and any(_inj.get(nm) not in ("Out", "Doubtful") for nm in names):
                con.execute("UPDATE predictions SET result='void', graded=1 "
                            "WHERE rowid=? AND graded=0", (rowid,))
                swept += 1'''
NEW = '''            # A MISSING KEY IS NOT EVIDENCE SHE IS BACK. injuries() is an injury report, not a
            # roster, so a player drops out of it both when she recovers AND when the report rolls
            # to the next slate. `.get()` returning None was treated as "playing" and voided 4 real
            # bets whose out-basis player genuinely never took the floor.
            if not (names and any(_inj.get(nm) not in ("Out", "Doubtful") for nm in names)):
                continue
            # The feed says the premise broke. If the slate has been played, the BOX SCORE decides.
            _truth = _premise_really_broke(names, pd_)
            if _truth is False:
                continue                                 # she did not play: premise held, grade it
            if _truth is None and pd_ < _today_et:
                continue                                 # past slate we cannot verify: never guess
            con.execute("UPDATE predictions SET result='void', graded=1 "
                        "WHERE rowid=? AND graded=0", (rowid,))
            swept += 1'''
assert OLD in s, "sweep anchor"
s = s.replace(OLD, NEW, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/wnba_ledger.prevoidtruth.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + premise sweep checks the box score before voiding; a missing injury-feed key")
print("    is no longer read as 'she is playing'")
